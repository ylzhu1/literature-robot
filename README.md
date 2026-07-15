# Literature Agent

一个用于自动抓取、筛选、总结并推送文献动态的小工具。当前版本面向“机器学习势 / DFT / 金属表面氧化机理”方向，默认推送到飞书群机器人。

## 功能

- 从 arXiv 和 Crossref 抓取最新论文元数据
- 按关键词和负面关键词筛选相关文献
- 通过 DOI / URL 去重，避免重复推送
- 调用 OpenAI-compatible 大模型生成中文核心思路
- 推送到飞书自定义机器人
- 支持 Windows 任务计划程序每天定时运行

## 项目结构

```text
literature_agent/
  fetchers.py        # 抓取 arXiv / Crossref / RSS
  filtering.py       # 关键词评分和负面关键词过滤
  summarizer.py      # 调用大模型生成中文核心思路
  report.py          # 生成 Markdown 日报
  feishu_sender.py   # 飞书机器人推送
  storage.py         # SQLite 去重数据库
  main.py            # 主入口

config.json          # 公开配置：关键词、来源、推送开关
.env.example         # 私密配置模板
.env                 # 本地私密配置，不要上传 GitHub
scripts/             # Windows 定时任务脚本
```

## 安装

本项目第一版只依赖 Python 标准库，推荐 Python 3.10+。

```powershell
cd D:\agent_Crawling_Literature
D:\work_program\anaconda3\envs\pynep\python.exe -m py_compile .\literature_agent\main.py
```

## 配置私密信息

复制 `.env.example` 为 `.env`，然后填入自己的大模型 API 和飞书 webhook。

```powershell
Copy-Item .env.example .env
notepad .env
```

示例：

```text
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://your-api-provider.example.com/v1
LLM_MODEL=gpt-4o-mini
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id
```

注意：`.env` 含有密钥，已经被 `.gitignore` 排除，不要上传到 GitHub。

## 运行

手动运行并推送到飞书：

```powershell
cd D:\agent_Crawling_Literature
D:\work_program\anaconda3\envs\pynep\python.exe -m literature_agent.main --config config.json --send-feishu
```

忽略去重、重新生成并推送当期结果：

```powershell
D:\work_program\anaconda3\envs\pynep\python.exe -m literature_agent.main --config config.json --ignore-seen --send-feishu
```

只生成报告，不发送：

```powershell
D:\work_program\anaconda3\envs\pynep\python.exe -m literature_agent.main --config config.json --dry-run
```

## 定时运行

在管理员 PowerShell 中运行：

```powershell
cd D:\agent_Crawling_Literature
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_windows_task.ps1
```

该脚本会创建 `LiteratureAgentDailyBrief` 任务，每天 10:00 自动运行并推送到飞书。

## 关键词策略

当前配置采用“宽抓取、严筛选”的方式。

正向关键词关注：

- 机器学习势、神经网络势、原子间势、主动学习
- DFT、第一性原理、AIMD、分子动力学、GCMC、KMC、NEB
- 表面氧化、铜氧化、氧吸附、氧解离、氧化物成核、氧化物生长、次表层氧
- 台阶、晶面、缺陷、位错、晶界、表面重构、低配位位点
- Cu、Pt、Ni、Ti、Ag、NiTi、过渡金属和合金表面
- 原位 TEM、环境 TEM、AP-XPS、operando 表征

负面关键词用于排除：

- 生物氧化、废水处理、光催化降解
- 电池正极、酶、植物、生物信息学、骨骼肌
- 机械加工、表面粗糙度、切削力、刀具磨损
- 抗菌涂层、细胞相容性、感染等跑偏方向

## GitHub 安全提醒

可以上传到 GitHub：

- `literature_agent/`
- `config.json`
- `.env.example`
- `.gitignore`
- `README.md`
- `scripts/`

不要上传：

- `.env`
- `data/`
- `reports/`
- `logs/`

如果使用 GitHub Actions，API key 和飞书 webhook 应放在 GitHub repository secrets 中。
