# Zhishu

<img width="2848" height="1600" alt="image" src="https://github.com/user-attachments/assets/c165c153-d1f5-47c1-9891-2eaf890101dd" />

Zhishu is a self-hosted learning workspace for branching a discussion from an exact selection, keeping reference snapshots, and storing every workspace on the server instead of in browser storage.

[中文文档](README.zh-CN.md)

## Features

- **Branch from an exact selection.** Select text in a message to show the nearby “Expand discussion” and “Copy” toolbar. Preview the passage, choose background up to the selection endpoint, then ask. Whole-message branching enters the same preview and never creates an empty discussion directly.
- **A quiet transcript.** Each turn keeps a compact action row — copy, select source, branch from here, regenerate while an answer is still pending, and remove the discussion — revealed on hover or keyboard focus. Only your own turn is drawn as a bubble, sized to its text; answers read as plain prose on the page background.
- **Organize and recover topics.** Create, search by title or tag, rename, favorite and remove. Removal uses an independent ten-minute server receipt; unrelated drafts and answers do not invalidate recovery. Deleting a session mainline is a separate, irreversible confirmation.
- **Connect and return.** Add reference snapshots from another topic, then jump back to the original passage at any time. Topics and messages load in pages, never as a full workspace.
- **Read typeset answers.** Replies render Markdown with KaTeX formulas — inline `$...$` or `\(...\)`, display `$$...$$` or `\[...\]` — including while streaming. A message can switch to “Select source” to select a formula as plain text.
- **Two views.** A minimal conversation view, and an on-demand graph view that frames the current topic with its children. A topic that is not opened is a small card showing its title and excerpt; opening it is what expands the reading capsule with its transcript and composer.

## Quick Start

Requires Node.js 22.12+, npm and Python 3.12+. SQLite is embedded; Docker and an external database are not needed.

Run from the repository root. Commands use the Windows Python launcher `py`; on macOS/Linux substitute `python3`.

```sh
npm install
py -m pip install -e "backend[test]"
cp .env.example .env          # Windows CMD: copy .env.example .env
py -m alembic -c backend/alembic.ini upgrade head
py -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Keep that running, then start Vite in a second terminal:

```sh
npm run dev:web
```

Open `http://127.0.0.1:5173`; Vite proxies API requests to FastAPI on port `8000`.

For a self-hosted production process, build the client, migrate, then serve FastAPI:

```sh
npm run build
py -m alembic -c backend/alembic.ini upgrade head
py -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Set `APP_ENV=production`, a persistent `DATABASE_URL` and `DATA_ENCRYPTION_KEY` before exposing the service.

## Configure a Model

Either set `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, `AI_PROVIDER` (`openai`, `anthropic` or `gemini`) and optionally `AI_TIMEOUT_MS` in `.env`, or configure everything in the in-app settings center: pick a provider, then set the endpoint, model name and API key.

Preset model names are examples, not a live availability list. **Save and test** saves the form before making a short request and distinguishes save failures from connection failures. Changing the protocol or endpoint requires a key for that connection. Clearing personal configuration requires confirmation and restores the server fallback if one exists.

DeepSeek, Qwen and OpenRouter are OpenAI-compatible URL presets, not separately verified integrations. Tests use protocol-specific local fixtures; no real provider account has been verified. Keys are submitted only to the same-origin API and excluded from read APIs and exports.

For production session credentials, set `DATA_ENCRYPTION_KEY` to a base64-encoded 32-byte key (`npm run keys:generate`). Without it in development the API generates an ephemeral process key, so saved credentials cannot be read after a restart. `AI_ALLOWED_HOSTS` optionally restricts provider hostnames.

History import/export uses NDJSON (1 MiB per record, 2 GiB per file); legacy JSON requests are limited to 8 MiB. Startup applies Alembic upgrades automatically and keeps the old workspace JSON as a migration-time backup. Read [architecture and current scaling limits](docs/architecture.md) before migrating a large workspace, including private-host and proxy settings such as `AI_ALLOW_PRIVATE_HOSTS` and `AI_FAKE_IP_HOSTS`.

## Windows Desktop

`desktop\build.ps1` builds the portable package and, with Inno Setup 6.3+, the installer. Outputs land in `desktop\dist\`:

- **`Zhishu-Setup-windows-x64.exe`** (recommended) — double-click to install; WebView2 Runtime and shortcuts are handled automatically, per user, no administrator rights
- **`Zhishu-windows-x64.zip`** — portable; unzip and run `Zhishu\Zhishu.exe`, keeping the whole `_internal` folder alongside it

Both bundle Python and every dependency. Data always lives in `%LOCALAPPDATA%\Zhishu` and is not removed on uninstall. Both need x64 Windows 10/11. Details and known limitations (not yet code-signed) are in the [desktop host documentation](desktop/README.md).

## Status

The graph view is functional but not complete: entering the overview frames the current topic and its direct children, but the underlying layout is still an insertion-order grid rather than a hierarchical constellation, and full subtree expansion, collision aggregation, shell morphing, camera history and native WebView2/Windows scaling verification remain open. Browser evidence is in `test-results/`; headless RAF samples are not a measured desktop 60fps claim.

## Test

```sh
npm test              # backend pytest
npm run typecheck
npm run build
npm run test:browser  # builds the client, starts FastAPI with a temp SQLite DB, drives Chrome
```

Install Chrome, or set `CHROME_PATH` to a Chrome/Chromium executable. The browser suite covers the conversation flow, settings failure recovery, unsaved edits, topic operations, mouse/keyboard selection, narrow layouts and the graph view; screenshots are written to `test-results/`. Narrow-browser checks do not replace physical mobile testing. Where `py` is unavailable, run `python3 -m pytest backend/tests -q` and `python3 backend/tests/browser_smoke.py`.

## Documentation

- [Chinese standards](docs/standards/README.md)
- [Architecture](docs/architecture.md)
- [Python backend](backend/README.md)
- [Web client](apps/web/README.md)
- [Windows desktop host](desktop/README.md)
