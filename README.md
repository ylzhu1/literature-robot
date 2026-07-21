# Literature Agent

Literature Agent is a lightweight Python workflow for monitoring recent papers, filtering them by research interests, summarizing abstracts with an OpenAI-compatible LLM, and sending the report to Feishu or email.

The default example configuration focuses on surface oxidation, density functional theory, machine-learning interatomic potentials, and metal surfaces. The keyword sets can be adapted to other research topics.

## Features

- Fetch recent papers from arXiv and Crossref
- Filter papers with positive and negative keyword groups
- Deduplicate pushed papers with a local SQLite database
- When the current window has too few matches, automatically backfill previous time windows and record the combined search range in the report
- Generate Chinese summaries with an OpenAI-compatible chat-completion API
- Send reports to Feishu custom bots
- Optionally send reports by email through SMTP
- Run manually or on a schedule with Windows Task Scheduler
- Run the daily Feishu brief in GitHub Actions without keeping a local computer on

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

The scheduled workflow and command-line runner use the Python standard library. The setup GUI uses CustomTkinter, which is listed in `requirements.txt` and bundled into the Windows release package.

## Configuration

### Windows app setup

For normal Windows users, download `LiteratureAgent-Windows.zip` from the repository's GitHub Releases page. Do not use the green `Code` button ZIP for the app, because that only downloads source code.

After downloading:

1. Extract `LiteratureAgent-Windows.zip` to a normal local folder, for example `Documents\LiteratureAgent`.
2. Open `quickstart.html` for the step-by-step first-time user guide.
3. Double-click `LiteratureAgentSetup.exe`.
4. Work through the left-side setup pages in order.
5. Click `Save Configuration`.
6. Use `Run a Test` to send one real test brief.
7. Optional: use `Schedule` to install the daily Windows task.

The app writes private credentials to `.env` and runtime outputs to `data/` and `reports/` in the extracted app folder. Keep those files private and do not re-zip a folder after it has been configured or used.

The app has five setup pages:

- `Model API`: enter an OpenAI-compatible API key, base URL, and model name, then test the LLM connection.
- `Topics & Filter`: edit keyword groups, strong keywords, excluded keywords, report size, look-back window, and matching strictness.
- `Notifications`: enable Feishu and/or email, then send channel-specific test messages.
- `Run a Test`: fetch papers, filter them, summarize matches, and send one real brief to enabled channels.
- `Schedule`: register or update the local Windows scheduled task.

In `Topics & Filter`, each keyword group is user-editable. A paper scores higher when it matches more groups. The `must appear` checkbox marks a required concept: if several groups are checked, a paper must match every checked group before it can be included. Use excluded keywords to reduce unrelated matches.

When topics are saved in the GUI, the app also regenerates arXiv, Crossref, and OpenAlex search queries from the same keyword groups and strong keywords. RSS feeds are not regenerated because they are fixed journal feeds rather than keyword searches.

### Source setup

For developers running from source, install dependencies first:

```powershell
python -m pip install -r requirements.txt
```

Then open the setup app:

```powershell
.\run_setup_gui.ps1
```

Users with Python available in `PATH` can also double-click:

```text
start_setup_gui.bat
```

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

Open the setup app:

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

The GUI `Schedule` page is the recommended way to install or update the daily task. It keeps only one Windows task and replaces the old time when you click `Install / Update Windows Task` again.

For source-code use, you can also run the helper script from the repository root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_windows_task.ps1
```

By default, the helper script runs daily at 09:00 and sends the report to the enabled channels.

## Schedule With GitHub Actions

The repository includes a GitHub Actions workflow at `.github/workflows/daily-literature-brief.yml`. It runs at 09:00 Asia/Shanghai time (01:00 UTC), fetches the literature brief in GitHub's cloud runner, and sends it to Feishu. A local computer does not need to stay on.

Before enabling it, add these repository secrets in GitHub under `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`:

```text
LLM_API_KEY
LLM_BASE_URL
LLM_MODEL
FEISHU_WEBHOOK
```

Use the corresponding values from the private `.env` file. Do not put credentials in `config.json`, the workflow file, or a Git commit. The workflow restores and saves the SQLite seen-paper database through GitHub Actions cache so previously sent papers are not repeated during the lookback window.

After the secrets are saved, open the repository's `Actions` tab, select `Daily Literature Brief`, and use `Run workflow` once to test it. Enable `resend_seen` only when manually previewing a changed report format; the normal scheduled run keeps deduplication enabled. GitHub scheduled runs can occasionally start a few minutes late; use a server-based scheduler when an exact-to-the-minute delivery guarantee is required.

## Build A Windows App

For lab users who should not interact with PowerShell or Python directly, download `LiteratureAgent-Windows.zip` from the repository's GitHub Releases page. The source-code ZIP from the green `Code` button does not contain the application.

To create a new Windows release package from source, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_app.ps1
```

The build output is:

```text
dist/LiteratureAgent-Windows.zip
```

Upload that ZIP as a GitHub Release asset. It is built from a clean folder and contains the application, public configuration, and quick-start guide, but no `.env`, reports, or local database. Do not manually zip a folder after it has been configured or used.

After extracting the release ZIP, users can double-click `LiteratureAgentSetup.exe`, fill in the required credentials, run the tests, and install the local daily scheduled task from the GUI. Windows may show an unknown-publisher warning because the executable is not code-signed; distribute it only through the repository's official GitHub Release page.

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

### Scoring Rules

Each fetched paper is scored against its title, abstract, and venue name. The scoring is intentionally generic, so users can rename or replace the keyword groups for other research areas.

- Each matched keyword group adds `2 + min(number_of_hits_in_that_group, 4)` points.
- Each matched strong keyword adds `4` points.
- Each matched excluded keyword subtracts `5` points.
- Papers that match multiple groups receive a cross-group bonus: `cross_group_bonus * (matched_group_count - 1)`. If `cross_group_bonus` is not set, the default is `3`.

A paper is kept only when all of these conditions are satisfied:

- Its score is at least `min_score`.
- It matches at least `group_min_matches` keyword groups.
- If any group is marked as required, it must match every required group.

The default configuration uses:

```json
{
  "min_score": 12,
  "group_min_matches": 3,
  "require_any_groups": ["oxidation"]
}
```

This means a default report must mention oxidation and also favors papers that connect it with methods, material systems, surfaces, defects, or in situ characterization, rather than papers that only contain one isolated keyword.

### Writing Keywords

Use keyword groups as separate concepts, not as one long list. For example, a surface oxidation project might use separate groups for `method`, `oxidation`, `surface_defect`, and `metal_system`. A strong paper should hit several of these groups at once.

For battery carbon-anode topics, keep the required groups broad enough to avoid empty reports. A practical setup is:

- `carbon_material` as required: `hard carbon`, `soft carbon`, `disordered carbon`, `non-graphitizable carbon`
- `battery_context` as required: `sodium-ion battery`, `lithium-ion battery`, `carbon anode`, `negative electrode`, `sodium storage`
- `mechanical_property` as a normal scoring group: `mechanical properties`, `Young's modulus`, `nanoindentation`, `fracture`, `stress`, `strain`, `cracking`
- Excluded keywords for common false positives: `diamond-like carbon`, `DLC`, `steel`, `tribology`, `friction`, `wear`, `coating`, `lubrication`

If you require `carbon_material`, `battery_context`, and `mechanical_property` at the same time, the report becomes much stricter and may return fewer papers. Use that only when mechanical behavior is mandatory.

Good keyword groups are broad enough to retrieve variants but specific enough to describe one concept. Put especially important phrases in strong keywords, and put recurring false-positive domains in excluded keywords.

For short abbreviations such as `DFT`, `Cu`, or `Pt`, the matcher uses whole-word matching. Longer phrases such as `oxygen adsorption` or `machine learning potential` are matched as phrases inside the title, abstract, or venue.

## Security

Store API keys, webhooks, and SMTP credentials in `.env` for local use or in repository secrets for automated deployments. Runtime outputs are ignored by default.

## Roadmap

- Feishu interactive card reports
- RSSHub and journal-specific RSS integrations
- PDF, introduction, and conclusion deep-scan summaries
- Weekly digest and trend-review mode
- Topic-specific configuration presets
