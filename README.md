# Zhishu

Zhishu is a self-hosted learning workspace for branching a discussion from an exact selection, preserving reference snapshots, and keeping each workspace on the server rather than in browser storage.

[中文文档](README.zh-CN.md)

## Learning Workflow

- **Start and organize discussions:** create a topic, search titles or tags, and use its “More” menu to rename, favorite or remove it. Removal has an independent ten-minute server receipt; unrelated drafts and answers do not invalidate recovery. Deleting an entire session's mainline requires a separate, irreversible confirmation.
- **Explore a passage:** select text in a message to show the nearby “Expand discussion” and “Copy” toolbar. Preview the passage, choose background up to the selection endpoint, and enter a question. Whole-message branching uses the same preview before creating a discussion.
- **Connect and return:** explicitly choose messages or ranges from another topic to add reference snapshots, then return to the original passage whenever needed. Topic and message lists are loaded in pages rather than as a full workspace.

## Quick Start

### Native constellation implementation status

The default React workspace renders native branch IDs with SVG relationships and an HTML conversation capsule. It provides Focus/Peek/Overview controls, a stable editor, blank-space pan, long-hold lasso, connector/title-hold linking, explicit position editing, and right-stroke removal preview followed by server-backed recovery. Text selection and provider settings use the existing components. Contacts never enter AI context; reference edges derive from existing reference entries.

`/api/graph` is bounded to 200 objects, 400 edges and 256 KiB. Alembic `0005_constellation` adds layout metadata, contacts and independent removal receipts to the existing database. Current history exports do not include graph positions, contacts or receipts; NDJSON replacement clears these graph-specific records.

**QA-010 is not yet fully delivered:** the initial layout is an insertion-order grid, not a hierarchical constellation layout. Full subtree expansion, collision aggregation, continuous active-node shell morphing, camera/navigation history and native WebView2/Windows scaling verification remain open. Browser evidence is in `test-results/graph-*.png` and `graph-measurements.json`; headless RAF samples are not a measured desktop 60fps claim. The latest portable ZIP is generated under `desktop/dist/`; an Inno Setup installer is produced only when Inno Setup is available.

Requires Node.js 22.12+ (or 24 LTS), npm, and Python 3.12+. SQLite is embedded; Docker and an external database are not required.

Run the commands below from the repository root. They use the Windows Python launcher `py`; on macOS/Linux, substitute your Python 3.12+ interpreter, usually `python3`.

```sh
npm install
py -m pip install -e "backend[test]"
```

Create the local environment file.

Windows CMD:

```cmd
copy .env.example .env
```

macOS, Linux, or another POSIX shell:

```sh
cp .env.example .env
```

Initialize the database and start FastAPI in the first terminal:

```sh
py -m alembic -c backend/alembic.ini upgrade head
py -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Keep it running and start Vite in a second terminal:

```sh
npm run dev:web
```

Open `http://127.0.0.1:5173`. FastAPI listens on port `8000`; Vite proxies API requests to it.

For a self-hosted production process, build the web client, migrate, then serve FastAPI:

```sh
npm run build
py -m alembic -c backend/alembic.ini upgrade head
py -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Set `APP_ENV=production`, a persistent `DATABASE_URL`, and `DATA_ENCRYPTION_KEY` before exposing the service.

## Configure a Model

Set `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`, `AI_PROVIDER` (`openai`, `anthropic`, or `gemini`), and optionally `AI_TIMEOUT_MS` in `.env`, or configure the protocol, output token limit and temperature in the Settings & Data panel. All three text protocols support incremental SSE. DeepSeek, Qwen and OpenRouter are OpenAI-compatible URL presets, not separately verified integrations. Tests use protocol-specific local fixtures; no real provider account has been verified. Session keys are submitted only to the same-origin API and excluded from read APIs and exports.

In Settings & Data, select a provider preset or enter a custom endpoint, then fill in the model name and API key. Preset model names are examples, not a live availability list. **Save and test** saves the current form before making a short model request and distinguishes save failures from connection failures. Changing the protocol or endpoint requires a key for that connection. Unsaved edits are protected when closing the panel; clearing personal configuration requires confirmation and restores the server fallback if one exists.

Settings also offers disk-staged NDJSON history import and streaming download (1 MiB per record, 2 GiB file limit). Compatibility JSON requests are limited to 8 MiB. Startup applies Alembic upgrades automatically; old workspace JSON is retained as a migration-time backup. Read [architecture and current scaling limits](docs/architecture.md) before migrating a large workspace. Private model hosts require the explicit server setting `AI_ALLOW_PRIVATE_HOSTS=true`; production still requires HTTPS.

For production session credentials, set `DATA_ENCRYPTION_KEY` to a base64-encoded 32-byte key. Generate one with `npm run keys:generate`. In development, an unset key causes the API to generate an ephemeral process key; saved session credentials deliberately cannot be read after a restart. `AI_ALLOWED_HOSTS` optionally restricts user-configured provider hostnames.

## Windows Desktop

On Windows, `desktop\build.ps1` builds the portable package and, with Inno Setup 6.3+ available, the installer. Successful outputs are in `desktop\dist\`:

- **`Zhishu-Setup-windows-x64.exe`** (recommended) — users double-click to install; the WebView2 Runtime and shortcuts are handled automatically, and it installs per user without administrator rights
- **`Zhishu-windows-x64.zip`** — portable; unzip and run `Zhishu\Zhishu.exe`, keeping the whole `_internal` folder alongside it

Both bundle Python and every dependency, so users need not install Python or Node.js, or start a server themselves. Data always lives in `%LOCALAPPDATA%\Zhishu`, and uninstalling does not remove it. Both require x64 Windows 10/11; the installer installs the Microsoft Edge WebView2 Runtime automatically when it is missing (if the runtime was not bundled at build time, the installer prompts the user to install it manually instead). Build details and known limitations (not yet code-signed, wizard language) are in the [desktop host documentation](desktop/README.md).

## Test

```sh
npm test
npm run typecheck
npm run build
npm run test:browser
```

The browser smoke test builds the client, starts FastAPI with a temporary SQLite database, and uses Chrome through the installed `playwright-core`. Install Chrome, or set `CHROME_PATH` to a Chrome/Chromium executable. It writes `test-results/browser-smoke.png`.

The browser suite also covers settings failure recovery, unsaved edits, topic operations, mouse/keyboard selection and narrow layouts; UX screenshots are saved as `test-results/ux-*.png`. Narrow-browser checks do not replace physical mobile-device testing. The npm test wrappers use `py`; where it is unavailable, run `python3 -m pytest backend/tests -q` and `python3 backend/tests/browser_smoke.py` directly.

## Documentation

- [Chinese standards](docs/standards/README.md)
- [Architecture](docs/architecture.md)
- [Python backend](backend/README.md)
- [Web client](apps/web/README.md)
- [Windows desktop host](desktop/README.md)
