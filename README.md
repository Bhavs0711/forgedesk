# ForgeDesk

A local workbench that plans a software project into features and lets a Claude agent implement them one at a time,
with dependency-aware scheduling, real test gating, approvals for risky commands, and live monitoring.

**Stack:** FastAPI · SQLAlchemy/SQLite (Alembic) · WebSockets · Claude Agent SDK (v0.2+) · React · TypeScript · Vite · Tailwind · TanStack Query · Recharts

---

## Quick start

### Requirements

| Tool | Version |
|------|---------|
| Python | 3.11 or later |
| Node.js | 18 or later |
| npm | 8 or later |
| git | any recent version |

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Configure (copy from the repo root, then edit)
cp ../.env.example .env
# Set ANTHROPIC_API_KEY and FORGEDESK_WORKSPACE_ROOTS in .env

uvicorn forgedesk.main:app --port 8000   # runs migrations automatically on startup
```

### Frontend — development (proxies /api and /ws to :8000)

```bash
cd frontend
npm ci
npm run dev      # → http://localhost:5173
```

### Frontend — production build (served by the backend)

```bash
cd frontend
npm ci && npm run build          # output goes to frontend/dist/
# The backend serves frontend/dist/ at http://localhost:8000
```

---

## Configuration

Copy `.env.example` to `backend/.env` and set:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | **Yes, for agent runs** | Anthropic API key. Only API-key auth is supported — Claude subscription credentials are not used. Without it, every endpoint works except starting an agent session. |
| `FORGEDESK_WORKSPACE_ROOTS` | **Yes** | JSON list of directories projects may live under, e.g. `["/home/you/forgedesk-projects"]`. Everything outside is rejected. |
| `FORGEDESK_DATABASE_URL` | No | Defaults to `sqlite:///./forgedesk.db` (file created next to `uvicorn`'s cwd). |
| `FORGEDESK_MODEL` | No | Claude model name. Default `claude-sonnet-4-5`. |
| `FORGEDESK_USE_DOCKER` | No | `true` runs the project's *test command* in a container with networking disabled. See Security model below. |

See `.env.example` for the full list of optional settings.

---

## How it works

1. **Create or import a project** — the directory must be under a workspace root. Write a specification and a test command.
2. **Start the agent.** With no features yet, an initializer session calls the Claude API to plan them (titles, acceptance criteria, priorities, dependencies). Duplicate titles are dropped; dependency cycles are rejected.
3. Each coding session **claims one eligible feature** (all dependencies completed) with an atomic compare-and-swap, implements it, and calls `run_tests`. `feature_complete` is **rejected unless the latest test run in that session passed**. Completed features are committed to git when `auto_commit` is on. Failures retry up to 3 times, then become `failed` and block their dependents; consecutive failures trigger exponential backoff and finally stop the run.
4. **Pause, resume, stop** apply at message boundaries. Stop releases the claimed feature. A database index enforces at most one live session per project, even across processes. On startup, sessions left running by a crash are marked `interrupted`, their features are released, and the next run resumes the SDK session when one was recorded.
5. When no eligible features remain, the full test command runs once more as a **regression check**. It can also be triggered on demand from the Test results tab.

---

## Tests

```bash
# Backend (from backend/)
source .venv/bin/activate
pytest -v
ruff check .

# Frontend (from frontend/)
npm run typecheck
npm test
npm run build

# End-to-end (from frontend/ — builds a production bundle and starts a throwaway backend)
npx playwright install chromium   # one-time
npm run e2e
```

---

## Security model (read this)

- **Authentication:** `ANTHROPIC_API_KEY` only, read from the server environment. It is redacted from logs and events and is never sent to the browser. Claude subscription credentials are not used.
- **Path confinement:** File tool calls and shell commands that reference paths outside the project directory are denied. Symlinks are resolved before the check, so a link pointing outside the project is rejected.
- **Command classification:** Shell commands are classified before execution. Hard-denied commands (`sudo`, `ssh`, `iptables`, etc.) are blocked outright. Destructive or unrecognised commands (`rm -rf`, `git push`, `curl`, unknown binaries) require explicit human approval in the UI. Approvals time out to "denied" after a configurable interval.
- **This is a policy layer, not a sandbox.** Agent shell commands run on the host under your user account. `FORGEDESK_USE_DOCKER=true` runs the project's *test command* in a container with networking disabled; it does not sandbox the agent's own Bash tool.
- **API security:** The API has no authentication. Run it on `localhost` only. The `CORS_ORIGINS` setting defaults to `["http://localhost:5173"]`.
- **Git safety:** Auto-commit only stages and commits inside the project directory. Destructive git operations (`push`, `reset --hard`, `clean`, etc.) require approval.

---

## GitHub — initialise and push

```bash
# From the repo root
git init
git add .
git commit -m "feat: initial ForgeDesk release"

# Create a new repo on GitHub first (no README, no .gitignore), then:
git remote add origin https://github.com/<you>/forgedesk.git
git branch -M main
git push -u origin main
```

---

## Provenance and licences

ForgeDesk is an independent implementation. The reference repository named in the brief
(`Shivfun99/autoforge-ai-main`) is a Flask/Node no-code ML tool with no LICENSE file; it contains no agent platform and
no code was copied from it. Choose a licence for this repository before publishing.
Dependencies are open source; the Claude Agent SDK is governed by Anthropic's Terms of Service.
