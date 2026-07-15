# Literature Agent

Literature Agent is a lightweight Python workflow for monitoring recent papers, filtering them by research interests, summarizing abstracts with an OpenAI-compatible LLM, and sending the report to Feishu or email.

The default example configuration focuses on surface oxidation, density functional theory, machine-learning interatomic potentials, and metal surfaces. The keyword sets can be adapted to other research topics.

## Features

- Fetch recent papers from arXiv and Crossref
- Filter papers with positive and negative keyword groups
- Deduplicate pushed papers with a local SQLite database
- Generate Chinese summaries with an OpenAI-compatible chat-completion API
- Send reports to Feishu custom bots
- Optionally send reports by email through SMTP
- Run manually or on a schedule with Windows Task Scheduler

## Project Layout

```text
literature_agent/
  fetchers.py        # arXiv, Crossref, and RSS fetchers
  filtering.py       # keyword scoring and negative-keyword filtering
  summarizer.py      # LLM-based and fallback summary generation
  report.py          # Markdown report rendering
  feishu_sender.py   # Feishu webhook sender
  email_sender.py    # SMTP email sender
  storage.py         # SQLite deduplication store
  main.py            # CLI entry point

config.json          # public configuration: sources, keywords, sender switches
.env.example         # environment variable template
scripts/             # Windows scheduling helper
```

Runtime files such as `.env`, `data/`, `reports/`, and `logs/` are excluded by `.gitignore`.

## Requirements

- Python 3.10+
- Network access to the selected metadata sources
- Optional: Feishu custom bot webhook
- Optional: SMTP account for email delivery
- Optional: OpenAI-compatible LLM API

The current MVP uses only the Python standard library.

## Configuration

### GUI setup

For Windows users, the easiest way to configure the project is the setup GUI:

```powershell
.\run_setup_gui.ps1
```

Users with Python available in `PATH` can also double-click:

```text
start_setup_gui.bat
```

The GUI can:

- Save LLM, Feishu, and SMTP settings
- Enable or disable Feishu and email delivery
- Test LLM connectivity
- Send a Feishu test message
- Send an email test message
- Run a real literature test
- Install or update the Windows scheduled task

Required fields are marked with a red `*`. Email delivery is optional; when it is disabled, email fields do not need to be filled. For common email providers, the GUI only requires the provider, email address, and SMTP authorization code. Advanced SMTP fields are available when custom server settings are needed.

### Manual setup

Create a private environment file from the template:

```powershell
Copy-Item .env.example .env
notepad .env
```

Configure the values needed by the notification channel and LLM provider:

```text
LLM_API_KEY=sk-your-api-key
LLM_BASE_URL=https://your-api-provider.example.com/v1
LLM_MODEL=gpt-4o-mini

FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=your_email@example.com
SMTP_PASSWORD=your_smtp_authorization_code
SMTP_USE_SSL=true
SMTP_USE_TLS=false
```

Notification channels are controlled in `config.json`:

```json
"email": {
  "enabled": false,
  "sender": "your_email@example.com",
  "recipients": ["your_email@example.com"]
},
"feishu": {
  "enabled": true
}
```

Set `email.enabled` and `feishu.enabled` according to the deployment target. Both can be enabled at the same time.

## Run Manually

Open the setup GUI:

```powershell
.\run_setup_gui.ps1
```

Generate a report and send it to the enabled channels:

```powershell
python -m literature_agent.main --config config.json
```

Send explicitly to Feishu:

```powershell
python -m literature_agent.main --config config.json --send-feishu
```

Send explicitly by email:

```powershell
python -m literature_agent.main --config config.json --send-email
```

Generate a report without sending:

```powershell
python -m literature_agent.main --config config.json --dry-run
```

Regenerate and resend the current results while ignoring the deduplication database:

```powershell
python -m literature_agent.main --config config.json --ignore-seen --send-feishu
```

## Schedule On Windows

Edit `scripts/install_windows_task.ps1` if a different Python path, project path, or schedule is needed. Then run PowerShell as administrator:

```powershell
cd D:\agent_Crawling_Literature
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_windows_task.ps1
```

By default, the task runs daily at 10:00 and sends the report to Feishu.

## Build A Windows App

For lab users who should not interact with PowerShell or Python directly, build a Windows application bundle:

```powershell
.\scripts\build_windows_app.ps1
```

The build output is:

```text
dist/LiteratureAgent/
  LiteratureAgentSetup.exe
  config.json
  .env.example
  QUICK_START.md
  ...
```

Share the whole `dist/LiteratureAgent` folder as a zip package. Users can double-click `LiteratureAgentSetup.exe`, fill in the required credentials, run the tests, and install the daily scheduled task from the GUI.

## Keyword Strategy

The default configuration uses broad retrieval and stricter filtering.

Positive keyword groups include:

- Machine-learning potentials, neural-network potentials, interatomic potentials, active learning
- DFT, first-principles calculations, AIMD, molecular dynamics, GCMC, KMC, NEB
- Surface oxidation, copper oxidation, oxygen adsorption, oxygen dissociation, oxide nucleation, oxide growth, subsurface oxygen
- Stepped surfaces, facets, defects, dislocations, grain boundaries, surface reconstruction, low-coordinated sites
- Cu, Pt, Ni, Ti, Ag, NiTi, transition metals, alloy surfaces
- In situ TEM, environmental TEM, AP-XPS, operando characterization

Negative keywords reduce false positives from unrelated domains such as biological oxidation, wastewater treatment, machining, surface roughness prediction, antibacterial coatings, and bioinformatics.

## Security

Store API keys, webhooks, and SMTP credentials in `.env` for local use or in repository secrets for automated deployments. Runtime outputs are ignored by default.

## Roadmap

- GitHub Actions workflow for scheduled cloud execution
- Feishu interactive card reports
- RSSHub and journal-specific RSS integrations
- PDF, introduction, and conclusion deep-scan summaries
- Weekly digest and trend-review mode
- Topic-specific configuration presets
