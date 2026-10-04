# AI Coding Agent Tool Proxy

A FastAPI authz proxy that sits in front of the MCP tools (`list_users`, `export_users`, `disable_user`). It decides whether a call is allowed, records it, and returns a stub result.

## Requirements

- Python 3.10+

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Seed the database

Creates `proxy.db` (SQLite) and seeds tenants, users, tools, agents and access rows. Re-running drops and recreates all tables.

```bash
python -m scripts.seed
```

The script prints one agent credential per tenant (`<prefix>.<secret>`). They are shown once and change on every run.

## Run the server

Admin APIs verify HS256 JWTs signed with a shared secret read from `JWT_SECRET`.

```bash
JWT_SECRET=<shared secret> uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs

## Project layout

```
app/
  main.py          # FastAPI app
  db.py            # SQLAlchemy engine, session, Base
  models.py        # ORM models
  controllers/     # HTTP layer
  services/        # business logic
scripts/
  seed.py          # database seed
```
