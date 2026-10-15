# Homework: improve a GUI testing agent

You get a working GUI testing agent built on [browser-use](https://github.com/browser-use/browser-use) and a vision-language model (VLM). It runs natural-language test cases against a real web app (BookStack) and decides whether the app behaves as expected. It is slow, expensive, and misses many bugs.

**Your job:** build an improved agent that does better on the metrics below: **more accurate, cheaper and faster per test**. It must stay general: it is graded on test cases you have not seen.

## How the agent is evaluated

Each scenario is a test case from [WebTestPilot-benchmark](https://github.com/code-philia/WebTestPilot-benchmark): a list of steps, each with an `action` and an `expectation`. The evaluator runs every scenario twice:

| Variant | The app | Correct verdict |
| --- | --- | --- |
| `clean` | works as intended | **PASS** |
| `bug` | has a bug injected into the page (an item missing, a wrong value, a duplicate, ...) | **FAIL** |

Before every run, the evaluator resets BookStack's database, opens a browser, logs in, and (for `bug` runs) injects the scenario's bug. It then hands that browser to your agent, which must perform the steps and return a verdict.

### Metrics

| Metric | Meaning | Goal |
| --- | --- | --- |
| `accuracy` | correct verdicts / runs. A crash, timeout or missing verdict (`ERROR`) counts as wrong | **higher**, never below baseline |
| `bug_recall` | share of `bug` runs your agent reported as FAIL | **higher** |
| `false_alarm_rate` | share of `clean` runs your agent reported as FAIL | **lower** |
| `mean_seconds` | wall time per run, measured by the evaluator | **lower** |
| `mean_tokens` | LLM tokens per run (prompt + completion), counted by the evaluator | **lower** |

### Baseline (`agents/baseline.py`, `qwen3.8-flash`)

| Accuracy | Bug recall | False alarms | Errors | Seconds / run | Tokens / run | LLM calls / run |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.62 | 0.25 | 0.00 | 0 / 8 | 92 | 77,356 | 6.5 |

<details><summary>Per run</summary>

| Scenario | Variant | Verdict | Correct | Seconds | Tokens |
| --- | --- | --- | --- | ---: | ---: |
| `count_recently_created_pages` | clean | PASS | yes | 82 | 64,138 |
| `count_recently_created_pages` | bug | PASS | **no** | 76 | 63,676 |
| `create_book` | clean | PASS | yes | 167 | 151,975 |
| `create_book` | bug | PASS | **no** | 123 | 112,296 |
| `recently_viewed_book` | clean | PASS | yes | 64 | 50,603 |
| `recently_viewed_book` | bug | PASS | **no** | 73 | 50,584 |
| `search` | clean | PASS | yes | 66 | 62,235 |
| `search` | bug | FAIL | yes | 85 | 63,339 |

</details>

It passed every clean run but caught only 1 of 4 bugs. In one miss it even noted that a new book showed "Bad Description" and still reported PASS.

Your numbers will vary from run to run: LLM agents are not deterministic. Report the mean of **3 evaluations**.

## Setup

Clone this repository; everything you need is in it. Commands are the same on Windows, macOS and Linux. You need:

- [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs Python and the packages for you;
- **Docker**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows and macOS, Docker Engine on Linux;
- an API key for an OpenAI-compatible endpoint whose model accepts images.

```bash
git clone https://github.com/code-philia/cs4810j-homework.git
cd cs4810j-homework
uv run install.py                         # one time: packages, Chromium, .env, Docker check
# put your API key in .env, then:
uv run evaluate.py --agent baseline --only search
```

The first run downloads the BookStack and MySQL images (about 1 GB) and starts them on http://localhost:8080 (login `admin@admin.com` / `password`). On Apple Silicon the BookStack image runs under emulation, which is slower but works.

The model is set in `.env`. The baseline numbers above use `LLM_MODEL=qwen3.8-flash`, the default.

Useful options:

```bash
uv run evaluate.py --agent baseline                      # all dev scenarios, both variants
uv run evaluate.py --agent my_agent --only search create_book
uv run evaluate.py --agent my_agent --variants bug       # only the buggy app
uv run evaluate.py --agent my_agent --headed             # watch the browser
```

Each evaluation writes `results/<agent>/<timestamp>/`: `summary.json`, `runs.jsonl` (one line per run), and a folder per run with whatever your agent saved there (the baseline saves its LLM conversation, step history and a GIF).

When you are done: `docker compose -f env/docker-compose.yaml down` stops the app.

## Writing your agent

Copy `agents/baseline.py` to `agents/<your_name>.py` and change it. The evaluator calls one function:

```python
async def run_test(task: Task, ctx: Context) -> Verdict:
    ...
```

| You get | What it is |
| --- | --- |
| `task.name`, `task.steps` | the test case; each step has `.action` and `.expectation` |
| `ctx.cdp_url` | the prepared browser. Attach with `BrowserSession(cdp_url=ctx.cdp_url)`. It is already logged in and on the start page |
| `ctx.llm(model=None)` | an LLM on the course endpoint. `model` defaults to `LLM_MODEL`; pass another name to mix models |
| `ctx.out_dir` | this run's folder for logs and screenshots |
| `ctx.memory_dir` | a folder that persists across runs, for memory, caches or a RAG index |

Return `Verdict(passed=True)` if every expectation held, `Verdict(passed=False, reason=...)` otherwise. Raise an exception if your agent could not reach a verdict; that counts as `ERROR`.

## Rules

1. **Use only LLMs from `ctx.llm()`.** That is how tokens are counted. Calling a model any other way is not allowed.
2. **Drive the app through the browser you are given.** No direct HTTP requests, database access or `docker` commands, and do not open URLs the steps don't lead to.
3. **Stay general.** Do not hard-code anything about specific scenarios (names, ids, selectors, verdicts). You are graded on **held-out scenarios** from the same app that are not in `tasks/dev/`.
4. **Memory is allowed, verdict memory is not.** `ctx.memory_dir` may hold knowledge about the app (pages, navigation, how to do things). It must not hold answers: what the result of a scenario was.
5. **Do not read `tasks/dev/bugs/` or the ground-truth fields** (`solution`, `action_check`, `url`, `assertion_check`) in your agent. They are there so the evaluator and instructors can check the setup.

## What to submit

1. `agents/<your_name>.py`, plus any other files it needs.
2. A short report (1–2 pages):
   - your results next to the baseline's: the metrics table, mean of 3 evaluations each;
   - what you changed and why, and which change saved the most;
   - one failure of your agent you investigated, with evidence from its run folder.

## Grading

Your agent runs on held-out BookStack scenarios, under the same evaluator and model as the baseline. Accuracy comes first: an agent less accurate than the baseline scores low however cheap it is. Beyond that, both higher accuracy and lower time and tokens per run raise your score. The report counts too.

## Where to start

Read a baseline run folder first: where do the time and tokens go, and why did it miss the bugs it missed? Then some directions (combine them; they are not a checklist):

- **Judge carefully:** the baseline trusted a "6 results" label instead of counting the list, and passed a test after noticing a wrong value. Check expectations against what is actually listed, and do not change the page you are judging.
- **Memory:** save what worked last time (how to reach a page, which control is which) and reuse it, calling the model only when the page no longer matches.
- **RAG:** retrieve notes about the app (its pages, navigation labels, past runs) into the prompt so the agent plans fewer steps.
- **System 1 / System 2:** a fast path (a cheap model, or a remembered action) for routine steps, and the strong VLM only when stuck and for judging expectations.
- **Fewer, bigger steps:** several actions per LLM call. See browser-use's `max_actions_per_step` and `flash_mode`.
- **See less:** screenshots are a large share of tokens. Try `use_vision="auto"` or a lower `vision_detail_level`, and measure what judging expectations really needs.
- **Leaner prompts and tools:** the baseline uses browser-use's default system prompt and file tools. What does each step actually need?

## Files

```
cs4810j-homework/
├── install.py           # one-time setup
├── evaluate.py          # run an agent on a task set and report the metrics
├── agents/baseline.py   # the agent to beat
├── harness/             # database reset, browser handover, bug injection, token metering
├── tasks/dev/           # the 4 public scenarios (+ bugs/ with their injected bugs)
├── env/                 # BookStack + MySQL (docker compose), baseline and seed data
├── oracle_check.py      # instructors: replay reference solutions to check the setup
├── import_tasks.py      # instructors: build a held-out set from the benchmark
├── pyproject.toml       # Python dependencies (uv)
└── .env.example         # template for .env: API key, endpoint, model
```

## Credits

Scenarios, bug scripts, seed data and the browser handover are from [WebTestPilot-benchmark](https://github.com/code-philia/WebTestPilot-benchmark), derived from [WebTestPilot](https://github.com/code-philia/WebTestPilot) (CC-BY-4.0). Changes: BookStack runs from the stock image on `localhost`; the harness (not a container) does login, bug injection and database resets; `harness/bug_injector.js` includes a `settle` helper the benchmark's adapter normally provides, and applies bugs within 500 ms instead of up to 3 s, so an agent cannot see the page before its bug is applied.
