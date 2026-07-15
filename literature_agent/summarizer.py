from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from typing import Any, Dict, List

from .models import ItemSummary, LiteratureItem


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _relevance_label(score: int) -> str:
    if score >= 20:
        return "high"
    if score >= 12:
        return "medium"
    return "watch"


KEYWORD_CN = {
    "machine learning potential": "机器学习势",
    "machine-learned potential": "机器学习势",
    "machine learning force field": "机器学习力场",
    "neural network potential": "神经网络势",
    "interatomic potential": "原子间势",
    "active learning": "主动学习",
    "density functional theory": "DFT/密度泛函理论",
    "DFT": "DFT/密度泛函理论",
    "ab initio molecular dynamics": "从头算分子动力学",
    "AIMD": "AIMD",
    "molecular dynamics": "分子动力学",
    "grand canonical Monte Carlo": "巨正则蒙特卡洛",
    "GCMC": "GCMC",
    "kinetic Monte Carlo": "动力学蒙特卡洛",
    "KMC": "KMC",
    "oxidation": "氧化",
    "surface oxidation": "表面氧化",
    "oxygen adsorption": "氧吸附",
    "oxygen dissociation": "氧解离",
    "oxide formation": "氧化物形成",
    "oxide growth": "氧化物生长",
    "oxide nucleation": "氧化物成核",
    "metal oxidation": "金属氧化",
    "copper oxidation": "铜氧化",
    "Cu oxidation": "铜氧化",
    "oxygen vacancy": "氧空位",
    "surface": "表面",
    "facet": "晶面",
    "crystal facet": "晶面",
    "stepped surface": "台阶表面",
    "step edge": "台阶边",
    "terrace": "平台区",
    "grain boundary": "晶界",
    "dislocation": "位错",
    "defect": "缺陷",
    "vacancy": "空位",
    "interface": "界面",
    "nanoparticle": "纳米颗粒",
    "low-index surface": "低指数晶面",
    "high-index surface": "高指数晶面",
    "copper": "铜",
    "Cu": "铜",
    "platinum": "铂",
    "Pt": "铂",
    "transition metal": "过渡金属",
    "metal surface": "金属表面",
    "alloy surface": "合金表面",
    "Cu alloy": "铜合金",
    "Pt surface": "铂表面",
    "in situ": "原位表征",
    "operando": "工况/原位表征",
    "environmental TEM": "环境透射电镜",
    "ETEM": "环境透射电镜",
    "ambient pressure XPS": "常压/近常压 XPS",
    "AP-XPS": "常压/近常压 XPS",
    "near ambient pressure XPS": "近常压 XPS",
    "NAP-XPS": "近常压 XPS",
    "in situ TEM": "原位 TEM",
}


def _cn_hits(item: LiteratureItem, group: str, limit: int = 3) -> List[str]:
    hits = []
    for keyword in item.matched_groups.get(group, []):
        hits.append(KEYWORD_CN.get(keyword, keyword))
    unique = []
    for hit in hits:
        if hit and hit not in unique:
            unique.append(hit)
    return unique[:limit]


def _extract_material_tokens(item: LiteratureItem) -> List[str]:
    text = f"{item.title} {item.abstract}"
    candidates = ["Cu", "Cu2O", "CuO", "Pt", "NiTi", "Ag", "Bi", "MnO2", "Fe", "Ti", "Ni", "AlCuFe"]
    found = []
    for token in candidates:
        if token in text and token not in found:
            found.append(token)
    return found[:4]


def _fallback_summary(item: LiteratureItem) -> ItemSummary:
    methods = _cn_hits(item, "method")
    oxidation = _cn_hits(item, "oxidation")
    surface = _cn_hits(item, "surface_defect")
    systems = _cn_hits(item, "metal_system")
    materials = _extract_material_tokens(item)

    system_desc = "、".join(materials or systems) or "金属/氧化物体系"
    oxidation_desc = "、".join(oxidation) or "氧化相关过程"
    surface_desc = "、".join(surface) or "表面结构"
    method_desc = "、".join(methods)

    text = f"这篇文章主要关注 {system_desc} 中的 {oxidation_desc}，重点放在 {surface_desc} 对反应或结构演化的影响。"
    if method_desc:
        text += f" 方法上涉及 {method_desc}，适合用来了解不同表面条件下氧吸附、氧化物形成或氧化动力学的机制。"
    else:
        text += " 它更偏向实验或材料现象报道，可作为理解表面氧化行为的背景参考。"
    return ItemSummary(item=item, summary_text=text, relevance=_relevance_label(item.score))


def _call_openai_compatible(item: LiteratureItem, config: Dict[str, Any]) -> str:
    llm_config = config.get("llm", {})
    api_key = os.environ.get(llm_config.get("api_key_env", "LLM_API_KEY"), "")
    base_url = os.environ.get(llm_config.get("base_url_env", "LLM_BASE_URL"), "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get(llm_config.get("model_env", "LLM_MODEL"), "gpt-4.1-mini")
    if not api_key:
        raise RuntimeError("LLM API key is not configured")

    prompt = f"""
请用中文为下面这篇文献写一个简短但有判断力的摘要。研究背景是：
用户关注机器学习势、DFT、分子动力学、GCMC，用于研究金属/铜/铂等表面氧化、氧吸附、氧化物成核、生长机制，以及晶面、台阶、位错、缺陷对氧化路径的影响。

请只输出一段中文“核心思路”，不要分点，不要输出“相关线索”，不要输出“对你的方向”。
重点说明：这篇文章研究了什么问题，用了什么方法/体系，得到的主要机制或启发是什么。

标题：{item.title}
来源：{item.venue or item.source}
摘要：{item.abstract[:4000]}
命中关键词：{", ".join(item.matched_keywords[:12])}
""".strip()

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "你是一个严谨的材料计算与表面科学文献助理。\n\n" + prompt,
                },
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")

    if os.name == "nt":
        return _call_openai_compatible_via_powershell(body, api_key, base_url)

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"].strip()


def _call_openai_compatible_via_powershell(body: bytes, api_key: str, base_url: str) -> str:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("powershell is not available on this system")

    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".json") as tmp:
        tmp.write(body)
        payload_path = tmp.name

    try:
        script = f"""
$ErrorActionPreference = 'Stop'
$headers = @{{ Authorization = 'Bearer {api_key}'; 'Content-Type' = 'application/json' }}
$body = Get-Content -Raw -Path '{payload_path}'
$response = Invoke-RestMethod -Method Post -Uri '{base_url}/chat/completions' -Headers $headers -Body $body
$response | ConvertTo-Json -Depth 20 -Compress
"""
        encoded = script.encode("utf-16le")
        encoded_command = __import__("base64").b64encode(encoded).decode("ascii")
        completed = subprocess.run(
            [powershell, "-NoProfile", "-EncodedCommand", encoded_command],
            capture_output=True,
            text=False,
            timeout=120,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            stdout = (completed.stdout or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(stderr or stdout or f"PowerShell request failed with code {completed.returncode}")
        stdout = (completed.stdout or b"").decode("utf-8", errors="replace").strip()
        payload = json.loads(stdout)
        return payload["choices"][0]["message"]["content"].strip()
    finally:
        try:
            os.remove(payload_path)
        except OSError:
            pass


def summarize_items(items: List[LiteratureItem], config: Dict[str, Any]) -> List[ItemSummary]:
    use_llm = bool(config.get("llm", {}).get("enabled", False))
    summaries: List[ItemSummary] = []
    for item in items:
        if use_llm:
            try:
                text = _call_openai_compatible(item, config)
                summaries.append(ItemSummary(item=item, summary_text=text, relevance=_relevance_label(item.score)))
                continue
            except Exception as exc:
                print(f"[warn] LLM summary failed for '{item.title[:60]}': {exc}; using fallback.")
        summaries.append(_fallback_summary(item))
    return summaries
