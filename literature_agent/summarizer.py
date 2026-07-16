from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .models import ItemSummary, LiteratureItem


GROUP_LABELS = {
    "method": "计算或建模方法",
    "oxidation": "氧化过程",
    "surface_defect": "表面结构或缺陷",
    "metal_system": "金属或合金体系",
    "in_situ": "原位表征",
}


def _relevance_label(score: int) -> str:
    if score >= 20:
        return "high"
    if score >= 12:
        return "medium"
    return "watch"


def _joined_hits(item: LiteratureItem, group: str, limit: int = 4) -> str:
    hits = item.matched_groups.get(group, [])[:limit]
    return "、".join(hits) if hits else "摘要未明确说明"


def _fallback_summary(item: LiteratureItem) -> ItemSummary:
    """Produce a truthful, useful report when the configured LLM is unavailable."""
    matched_topics = "、".join(
        GROUP_LABELS[group]
        for group in item.matched_groups
        if group in GROUP_LABELS
    ) or "材料与表面科学"
    method = _joined_hits(item, "method")
    oxidation = _joined_hits(item, "oxidation")
    system = _joined_hits(item, "metal_system")
    structure = _joined_hits(item, "surface_defect")

    text = "\n".join(
        [
            f"**论文概述**：该论文的标题和摘要与{matched_topics}有关，重点命中了{oxidation}等主题。",
            f"**研究对象与方法**：摘要中涉及的体系包括{system}；可确认的方法线索为{method}。",
            f"**表面与结构线索**：摘要中出现{structure}。具体的反应路径、定量结果和作者结论需要以原文摘要或全文为准。",
            "**信息边界**：模型摘要调用未成功，本条仅根据检索元数据生成，不应视为论文的完整机制解读。",
        ]
    )
    return ItemSummary(item=item, summary_text=text, relevance=_relevance_label(item.score))


def _completion_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _build_prompt(item: LiteratureItem) -> str:
    return f"""
请以严谨的材料计算与表面科学研究者身份，解读下面一篇论文。你的回答会直接发给课题组阅读。

严格约束：
1. 只能使用标题和摘要中明确给出的信息，不得根据常识补充不存在的实验、数值、机理或性能结论。
2. 若摘要没有说明某项内容，直接写“摘要未说明”，不要猜测。
3. 不要输出“相关度”“命中关键词”“对你的方向”“建议阅读”等栏目。
4. 使用简体中文，保留 DFT、MLIP、GCMC、AIMD 等必要英文缩写。
5. 总长度控制在 300 至 500 个汉字左右，信息密度高但不要堆砌术语。

请严格按下面的 Markdown 格式输出，不要添加标题以外的开场白：

**中文概述**：用一段话说明论文研究了什么问题、研究对象是什么、采用什么总体思路。

### 💡 深度解读

1. **研究问题**：说明作者希望解决或解释的科学问题。
2. **方法与体系**：说明研究的材料/表面/结构对象，以及实验、计算或理论方法。
3. **核心创新或机制**：说明论文提出的新方法、新认识或机制；摘要信息不足时明确说明。
4. **关键结论**：概括摘要中可确认的主要发现；没有明确结论时写“摘要未说明”。

论文标题：{item.title}
来源：{item.venue or item.source}
摘要：{item.abstract[:5000]}
""".strip()


def _extract_content(payload: Dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM response does not contain choices[0].message.content") from exc

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        return "".join(text_parts).strip()
    raise RuntimeError("LLM response content is not text")


def _call_openai_compatible(item: LiteratureItem, config: Dict[str, Any]) -> str:
    llm_config = config.get("llm", {})
    api_key = os.environ.get(llm_config.get("api_key_env", "LLM_API_KEY"), "")
    base_url = os.environ.get(
        llm_config.get("base_url_env", "LLM_BASE_URL"),
        "https://api.openai.com/v1",
    )
    model = os.environ.get(llm_config.get("model_env", "LLM_MODEL"), "gpt-4.1-mini")
    if not api_key:
        raise RuntimeError("LLM API key is not configured")

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise scientific literature analyst. Follow the user's output format exactly and never invent facts beyond the supplied title and abstract.",
                },
                {"role": "user", "content": _build_prompt(item)},
            ],
            "temperature": 0.15,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    if os.name == "nt":
        return _call_via_powershell(body, api_key, _completion_url(base_url))
    return _call_via_urllib(body, api_key, _completion_url(base_url))


def _call_via_urllib(body: bytes, api_key: str, url: str) -> str:
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM network request failed: {exc.reason}") from exc
    return _extract_content(payload)


def _call_via_powershell(body: bytes, api_key: str, url: str) -> str:
    """Keep the Windows transport fallback used by the local desktop workflow."""
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell is not available for the Windows LLM request")

    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".json") as temporary:
        temporary.write(body)
        payload_path = temporary.name

    try:
        script = f"""
$ErrorActionPreference = 'Stop'
$headers = @{{ Authorization = 'Bearer {api_key}'; 'Content-Type' = 'application/json' }}
$body = Get-Content -Raw -Path '{payload_path}'
$response = Invoke-RestMethod -Method Post -Uri '{url}' -Headers $headers -Body $body
$response | ConvertTo-Json -Depth 20 -Compress
"""
        encoded_command = base64.b64encode(script.encode("utf-16le")).decode("ascii")
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
        payload = json.loads((completed.stdout or b"").decode("utf-8", errors="replace"))
        return _extract_content(payload)
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
                print(f"[warn] LLM summary failed for '{item.title[:60]}': {exc}; using metadata fallback.")
        summaries.append(_fallback_summary(item))
    return summaries
