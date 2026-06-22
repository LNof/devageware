# Devageware — Firmware Generation Agent
> Last updated: June 9, 2026

---

## Update 2026-06-09 — canonical naming + Nexus summary fix

- **Canonical naming:** `FirmwareProject` gained `slug` (canonical, e.g. `PIP_Controller`) and a
  `path_name` property (slug, else display name with whitespace→underscores). `parse_firmware_json`
  (`codegen.py`) now overrides the LLM-chosen `name`/`slug` from pipeline state (`project_name`/
  `project_slug`) when present, so all systems agree. `path_name` is used for the Nexus path
  (`nexus.py`), on-disk dir (`save_project_to_disk`) and Git branch (`git.py`). Handoff writes
  `project_slug`. Standalone runs (no state) keep the LLM-derived name. Convention: display name →
  README/docs titles; slug → paths/branch.
- **Nexus summary fix (`nexus.py upload_all_artifacts`):** sets `nexus_artifact_url` from the `.hex`
  when there's no `.bin` (AVR/Arduino), so the firmware-complete summary stops falsely reporting
  "Nexus: Not uploaded" — the `.hex` was always uploading (`upload_hex`), it just wasn't recorded.
- **Git push:** branch = `project.path_name` within the single configured `GITHUB_REPO`
  (one-repo-many-branches). 2026-06-09 a push transiently failed (`get_github_repo` → None before
  `git init`, token+repo verified fine); recovered by calling `init_and_push()` against the on-disk
  build. Candidate: a resumable `devageware-publish` stage (push + Nexus + docs, skip codegen/compile).

## Overview

Devageware is an AI-powered firmware generation agent that:
1. Reads device requirements from Notion (or accepts them via conversation)
2. Consults with the engineer to determine platform, toolchain and architecture
3. Generates complete, compilable firmware source code
4. Compiles the firmware using the appropriate toolchain
5. Pushes source code to GitHub
6. Uploads build artifacts to Nexus
7. Generates documentation and publishes to Notion

---

## Full Pipeline

```
Notion (requirements) OR direct conversation
        ↓
Agent consults engineer on platform/toolchain
        ↓
LLM generates firmware source code
        ↓
Save files to disk
        ↓
Compile with appropriate toolchain
        ↓
        ├── Push source → GitHub (project branch)
        ├── Upload .hex/.bin → Nexus
        └── Generate docs → Notion
```

---

## Project Location

```
~/Documents/projects/devageware/
```

---

## Project Structure

```
devageware/
├── .env
├── .gitignore
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── agent.py              # main orchestrator + conversation loop
│   ├── prompts.py            # system prompts
│   ├── models.py             # data structures
│   └── tools/
│       ├── __init__.py
│       ├── notion.py         # read requirements + write docs
│       ├── codegen.py        # parse LLM JSON, save files, generate docs
│       ├── compiler.py       # compile firmware (NCS/PlatformIO/MCUXpresso)
│       ├── git.py            # push source to GitHub
│       └── nexus.py          # upload artifacts to Nexus
└── main.py
```

---

## Supported Platforms

| Platform | Toolchain | Board IDs | Status |
|---|---|---|---|
| Arduino Nano Every | PlatformIO / atmelmegaavr | `nano_every` | ✅ Working |
| Arduino Nano (classic) | PlatformIO / atmelavr | `nanoatmega328` | ✅ Working |
| Arduino Uno | PlatformIO / atmelavr | `uno` | ✅ Working |
| Arduino Mega | PlatformIO / atmelavr | `megaatmega2560` | ✅ Working |
| ESP32 | PlatformIO / espressif32 | `esp32dev` | ✅ Configured |
| Nordic nRF54L15 | NCS v3.2.4 / west | `nrf54l15dk` | ⚠️ Toolchain path issues |
| NXP i.MRT1062 | MCUXpresso | TBD | 🔲 TODO |

---

## Data Models (`src/models.py`)

### `Platform`
- `name`, `vendor`, `mcu`, `toolchain`, `language`, `board`
- `sdk_path`, `toolchain_path`

### `FirmwareModule`
- `name`, `filename`, `description`, `code`

### `FirmwareProject`
- Project info: `name`, `version`, `description`, `created_at`
- Platform: `Platform`
- Source files: `cmakelists`, `prj_conf`, `platformio_ini`, `main_c`
- Modules: `list[FirmwareModule]`
- Build outputs: `bin_path`, `hex_path`, `build_log`, `build_success`
- Remote: `git_repo_url`, `nexus_artifact_url`, `notion_doc_url`

### `RequirementsDoc`
- Read from Notion: `title`, `device_name`, `device_description`, `target_users`
- Categorised requirements: `functional`, `hardware`, `electronics`, `software_firmware`, `performance`, `constraints`

---

## Key Configuration (`.env`)

```
GROQ_API_KEY=gsk_...
NOTION_TOKEN=ntn_...
NOTION_PAGE_ID=...
NEXUS_URL=http://10.0.0.221:8081
NEXUS_USER=firmware-agent
NEXUS_PASSWORD=...
NEXUS_RAW_REPO=firmware-artifacts
NEXUS_DOCKER_REGISTRY=10.0.0.221:8082
GITHUB_TOKEN=ghp_...
GITHUB_REPO=LNof/pip-agentic
NCS_TOOLCHAIN_PATH=/home/LoayN/ncs/toolchains/2ac5840438
NCS_SDK_PATH=/home/LoayN/ncs/v3.2.4
NCS_WORKSPACE=/home/LoayN/ncs-workspaces
```

---

## Prompts (`src/prompts.py`)

### `SYSTEM_PROMPT`
Expert embedded firmware engineer persona. Key rules:
- Supports Nordic NCS/Zephyr, NXP MCUXpresso, Arduino/PlatformIO
- Always use exact PlatformIO board IDs (never generic names)
- Always include `framework = arduino` in platformio.ini
- Never output JSON during consultation — only when engineer confirms ready
- Generate complete files — never truncate

### PlatformIO Board ID Reference (in prompt)
```
Arduino Nano (classic) → nanoatmega328, platform = atmelavr
Arduino Nano Every     → nano_every, platform = atmelmegaavr
Arduino Uno            → uno, platform = atmelavr
Arduino Mega           → megaatmega2560, platform = atmelavr
ESP32                  → esp32dev, platform = espressif32
```

### `COMPLETION_PROMPT`
Triggers JSON code generation. Output format:
```json
{
  "platform": { "name", "vendor", "mcu", "toolchain", "language", "board" },
  "project": { "name", "version", "description" },
  "files": {
    "platformio.ini": "...",
    "src/main.cpp": "..."
  },
  "modules": [{ "name", "filename", "description", "code" }]
}
```

---

## Known Issues & Fixes

### `.c` vs `.cpp` extension
**Problem:** LLM returns `language: "c"` for Arduino projects
**Fix in `src/tools/codegen.py` `parse_firmware_json()`:**
```python
if toolchain == "platformio":
    language = "cpp"
else:
    language = platform_data.get("language", "c")
```

### `framework = arduino` missing
**Problem:** LLM omits `framework = arduino` causing `Arduino.h not found`
**Fix:** Added to `SYSTEM_PROMPT` as critical rule

### Version showing as `vv1.0.0`
**Fix in `parse_firmware_json()`:**
```python
version = project_data.get("version", "0.1.0").lstrip("v")
```

### Stale files from previous runs
**Fix in `save_project_to_disk()`:**
```python
if os.path.exists(project_dir):
    shutil.rmtree(project_dir)
```

### PlatformIO path with spaces
**Fix in `build_platformio_project()`:**
```python
project_dir = os.path.abspath(project_dir)
```

### Toolchain normalisation
**Fix:** `arduino` and `arduino/platformio` → normalised to `platformio`

---

## GitHub Integration

- Repo: `LNof/pip-agentic`
- Each project gets its own branch (e.g. `pip-controller`)
- Uses force push to update existing branches
- Token format: `ghp_...` (classic token with `repo` scope)

---

## Nexus Integration

- URL: `http://10.0.0.221:8081`
- Raw repo: `firmware-artifacts`
- Artifact path structure: `vendor/mcu/project-name/version/filename`
- Example: `arduino/atmega4809/PIP_Controller/1.0.0/firmware.hex`
- Uploads: `.hex`, `.bin` (if exists), `build.log`

---

## Notion Integration

- Reads requirements from existing pages
- Creates new firmware documentation pages
- Output includes: platform table, build instructions, project structure, artifact locations

---

## Trigger Phrase

Agent generates firmware when user types:
```
generate the firmware
generate firmware
generate the code
generate code
start generating
ready to generate
```

---

## Working Example — PIP Controller

**Device:** Arduino Nano Every (ATmega4809)
**Relay connections:** D5 (Relay 1), D6 (Relay 2), D7 (Relay 3), D8 (Relay 4)
**Commands:** `relay 1 on/off`, `relay 2 on/off` etc., `firmware` → version
**Baud rate:** 57600
**Error response:** `Invalid command`

**GitHub:** `https://github.com/LNof/pip-agentic/tree/pip-controller`
**Notion docs:** Generated per run

---

## Next Steps

- [ ] Remove debug print statements once stable
- [ ] Fix NCS toolchain path resolution for Nordic builds
- [ ] Add NXP MCUXpresso support
- [ ] Implement token budget control
- [ ] Add human approval step before flashing
- [ ] Migrate to LangGraph for better state management
- [ ] Add `.bin` detection for Arduino (currently only `.hex`)
- [ ] Test full pipeline with Nexus upload working
