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
| POST | `/groups` | `{"name", "members": [{"name", "email"}]}` | create a group |
| POST | `/groups/<id>/expenses` | `{"paid_by", "amount", "description"?, "split_among"?}` | log an expense (split evenly among `split_among`, or the whole group if omitted) |
| GET | `/groups/<id>/expenses` | `?page=1&limit=20&sort=created_at` | list expenses |
| GET | `/groups/<id>/balances` | | net balance per member (positive = owed money) |
| POST | `/groups/<id>/settlements` | `{"from", "to", "amount"}` | record that `from` paid `to` back |

## Running it

From this folder, with the root venv activated (`source ../../.venv/bin/activate`):

```bash
python -m pytest          # run the tests
python run.py             # start the app at http://127.0.0.1:8080  (python run.py 8081 for another port)
```

Example:

```bash
curl -s -XPOST localhost:8080/groups -H 'content-type: application/json' \
  -d '{"name":"trip","members":[{"name":"alice","email":"alice@example.com"},{"name":"bob","email":"bob@example.com"}]}'
curl -s -XPOST localhost:8080/groups/1/expenses -H 'content-type: application/json' \
  -d '{"paid_by":"alice","amount":40,"description":"dinner"}'
curl -s localhost:8080/groups/1/balances
```
