# AI coding interview practice

A set of small "buggy prototype" services for practising the *coding with AI*
interview round: find the real bugs, then push the service toward production
readiness in about 60 minutes, while you drive and the AI assists.

Read **[PRACTICE_GUIDE.md](PRACTICE_GUIDE.md)** before your first session.

## Setup (once)

```bash
uv venv .venv && uv pip install -p .venv -r requirements.txt
# or: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate
```

## Projects

| # | Project | Domain | Status |
|---|---|---|---|
| 01 | [splitr](projects/01_splitr) | Splitwise-style expense splitting (Flask + SQLite) · find bugs, 60 min | done, reviewed |
| 02 | [quota_gate](projects/02_quota_gate) | Multi-tenant rate limiter with JWT auth (Okta-style) · build from spec, 3 h + live change | not started |
| 03 | [tenant_invites](projects/03_tenant_invites) | Single-use tenant invite links with JWT authn/authz (FastAPI + SQLite) · build from spec, pair-programmed | done |
| 04 | [api_key_vault](projects/04_api_key_vault) | Multi-tenant API key vault: create, revoke, rotate, introspect (FastAPI + SQLite) · build from spec, pair-programmed | in progress |
| 05 | [tool_proxy](projects/05_tool_proxy) | Multi-tenant authz proxy in front of MCP tools, confused-deputy safe (FastAPI + SQLite) · build from spec, pair-programmed | in progress |

## Running a session

```bash
git checkout -b practice/01_splitr     # keep main pristine so you can redo it
cd projects/01_splitr
python -m pytest
python run.py
```

Each project has its own `README.md` (the brief) and `NOTES.md` (your working notes).
Answer keys live **outside** this repo (`~/ai-coding-practice-answer-keys/`) so the AI
assistant you practise with can't read them.

## Adding a project

`projects/NN_name/` containing:
- `name/`: the app package
- `tests/`: tests that pass but miss the planted bugs
- `run.py`, `pytest.ini` (`pythonpath = .`), `README.md`, `NOTES.md`
