# How to practise "coding with AI"

The interviewer isn't checking whether you can get the AI to produce code. They're
checking whether **you** stay in control: you understand the system, you decide
what matters, you verify everything, and you can explain your choices.
"Paste the repo and say *find all the bugs*" fails every one of those checks,
even when the output happens to be right.

## The loop (60 minutes)

| Phase | Time | You | AI |
|---|---|---|---|
| 1. Orient | 0–10 | Read the brief. Run the tests. Start the app and call every endpoint once. Read **every** file yourself and write the map in `NOTES.md`. | Only for "what does this library call do?" questions. |
| 2. Hypothesise | 10–15 | Write down suspected bugs in your own words, including weak hunches. | Optional: "Here's my list. What categories am I missing?" Don't ask it to list bugs for you. |
| 3. Confirm → fix | 15–35 | For each bug, **write a failing test or curl first**, then fix it and commit. One bug per commit. | Write the test or fix from *your* description. Read every line of the diff before accepting. |
| 4. Production readiness | 35–55 | Brainstorm candidates and rank them by *risk × effort*. Pick 2–3 and finish them properly. | Good for boilerplate (validation schemas, index migrations, logging setup) once you've decided what to build. |
| 5. Write-up | 55–60 | Fill in "left alone on purpose" and the walkthrough script. | Can tighten your wording. The content must be yours. |

## Prompting: narrow beats broad

| ❌ Throwing it over the wall | ✅ Driving |
|---|---|
| "Find the bugs in this repo." | "In `ledger.py:split_evenly`, what happens with amount=100 across 3 people? Do the shares sum to the amount?" |
| "Make this production ready." | "I want request validation on POST /expenses: amount must be a positive number with at most 2 decimals, and paid_by must be a group member. Return 400 with a message. Don't touch other endpoints." |
| "Fix it." | "This test fails because X. Change only `balances()`, keep the function signature, and explain the change in one sentence." |
| Accepting a 200-line diff | "Before writing code: what's your plan, and which files would you touch?" |

Rule of thumb: **if you can't predict roughly what the AI will produce, your prompt is too broad.**

## Verifying AI output (the part interviewers actually watch)

- Read the diff. Every line. If you can't explain a line, ask about it or delete it.
- Run the tests after every change, not at the end.
- Ask "what could break because of this change?" and check its answer yourself.
- Watch for scope creep: renamed variables, reformatted files, "while I was here" refactors. Revert them. They make your diff harder to review.
- Be suspicious of confident claims about libraries. Check the docs or try it in a REPL.

## Production readiness: how to rank

Ask about each candidate: *if this ships to 10,000 users tomorrow, what breaks first, and how bad is it?*

1. **Data correctness / money / security**: wrong numbers, lost writes, injection. Always first.
2. **Failure handling**: what happens when a dependency is slow or fails? Partial writes? Retries creating duplicates?
3. **Input validation**: bad input should get a 400, not a 500 or silent garbage.
4. **Concurrency & performance**: shared state, missing indexes, blocking I/O in the request path, unbounded queries.
5. **Operability**: structured logs, config from env, health check, debug mode off.

Saying "I saw X, it matters, here's why I left it for later" counts nearly as much as doing X.

## After each session

Commit your work, then ask Claude (in a new chat) to review your branch against the
answer key at `~/ai-coding-practice-answer-keys/<project>.md`. Compare what you found
with what you missed, and record what you missed in `LEARNINGS.md` at the repo root
so the next session targets it.
