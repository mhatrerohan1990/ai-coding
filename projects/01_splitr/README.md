# splitr

splitr is a small Splitwise-style service for sharing expenses. A group of friends
creates a group, people log what they paid, and the app works out who owes whom.
When an expense is added, everyone sharing it gets an email notification.
Members can record a settlement when they pay each other back.

It's been running in low-traffic production for a few months and all the tests
pass. That doesn't mean it's correct, and it definitely doesn't mean it's ready
for real load.

## Your task

You have two jobs.

**Find and fix the bugs.** There are a handful of real bugs in here. The
existing tests pass, so they won't point you at them. Read the code carefully,
exercise the endpoints, and fix what actually matters. Be ready to explain what
you found, what you fixed, and anything you chose to leave alone.

**Push it toward production readiness.** Right now it's a prototype that happens
to run. You won't make it fully production-ready in an hour, and we don't expect
you to. Think about what it would take to put this in front of real users at
real volume, decide what matters most, and get as far as you can on the things
you pick. What "production ready" means here is yours to define. Be ready to
walk through your plan and defend why you tackled what you did first.

Out of scope: deployment. Skip Dockerfiles, CI and infrastructure, and focus on
the code itself.

We care more about your judgment on what to tackle first than about a long list
of half-finished changes.

## Time

Aim for **60 minutes**. Write your start time in `NOTES.md` before you begin.

## API

| Method | Path | Body / query | Purpose |
|---|---|---|---|
| POST | `/users` | `{"name", "email"?}` | create a user (returns a UUID `id`) |
| GET | `/users/<id>` | | fetch a user |
| PATCH | `/users/<id>` | `{"name"?, "email"?}` | rename / change email (history is unaffected) |
| POST | `/groups` | `{"name", "members": [<user_id>, ...]}` | create a group from existing users |
| POST | `/groups/<id>/expenses` | `{"paid_by", "amount", "description"?, "split_among"?}` | log an expense (split evenly among `split_among`, or the whole group if omitted); `paid_by` / `split_among` are user ids |
| GET | `/groups/<id>/expenses` | `?page=1&limit=20&sort=created_at` | list expenses (`limit` max 100; `sort` one of id, amount, description, created_at) |
| GET | `/groups/<id>/balances` | | net balance per member, keyed by user id (positive = owed money) |
| POST | `/groups/<id>/settlements` | `{"from", "to", "amount"}` | record that user `from` paid user `to` back |

## Architecture

```
splitr/
  app.py           create_app(): wires the layers together
  controllers/     HTTP only: Flask blueprints parse requests, call services, shape JSON
  services/        business rules, validation, transaction boundaries (no Flask, no SQL)
  repositories/    all SQL; returns model objects, never commits
  models/          plain frozen dataclasses: User, Group, Expense, Share, Settlement, Balance
  db.py            per-thread connections, db.transaction(), db.read_snapshot()
  notifier.py      email adapter + background queue
  errors.py        ValidationError (400), NotFound (404)
  validation.py    shared input validators
```

Dependencies point one way: controllers -> services -> repositories -> db, and models import
nothing from the app. `tests/test_app.py` enforces this (e.g. no SQL in services or controllers,
no Flask in services).

## Running it

From this folder, with the root venv activated (`source ../../.venv/bin/activate`):

```bash
python -m pytest          # run the tests
python run.py             # start the app at http://127.0.0.1:8080  (python run.py 8081 for another port)
SPLITR_DEBUG=1 python run.py   # local development only: auto-reload + interactive debugger
```

Debug mode is off by default: Flask's debugger lets anyone who can reach the port run code on the
server, so never enable it anywhere reachable. `run.py` also uses Flask's development server; use a
WSGI server (e.g. gunicorn) for real traffic.

Example:

```bash
H='content-type: application/json'
A=$(curl -s -XPOST localhost:8080/users -H "$H" -d '{"name":"alice","email":"alice@example.com"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
B=$(curl -s -XPOST localhost:8080/users -H "$H" -d '{"name":"bob","email":"bob@example.com"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -XPOST localhost:8080/groups -H "$H" -d "{\"name\":\"trip\",\"members\":[\"$A\",\"$B\"]}"
curl -s -XPOST localhost:8080/groups/1/expenses -H "$H" -d "{\"paid_by\":\"$A\",\"amount\":40,\"description\":\"dinner\"}"
curl -s localhost:8080/groups/1/balances
```

If you have a `splitr.db` from an older version, delete it: the schema changed (users, group_members)
and the app refuses to open an old-layout database.
