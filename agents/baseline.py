"""Baseline GUI testing agent: one browser-use agent, one strong VLM, every step from scratch.

Copy this file to agents/<your_name>.py and make it cheaper and faster without
losing accuracy. The harness calls run_test() once per scenario run.
"""

import re

from browser_use import Agent, BrowserSession, Tools
from browser_use.llm.messages import UserMessage

from harness.context import Context, Verdict
from harness.tasks import Task


def build_prompt(task: Task) -> str:
	steps = '\n'.join(
		f'{i}. ACTION: {s.action}\n   EXPECTED: {s.expectation}' for i, s in enumerate(task.steps, start=1)
	)
	return f"""You are a QA tester running a GUI test case on a BookStack web app.
The browser is already logged in and open on the start page. Do not navigate to any URL yourself;
use the app's own links and buttons.

Test case: {task.name}
{steps}

Rules:
- Perform the steps in order, through the UI only.
- After each action, check its EXPECTED result on the page before moving on.
- Some expectations compare against something you saw earlier ("consistent with", "before and after",
  "equal to the previous list"). Note the relevant details (names, counts, order) when you see them.
- If an expectation does not hold, stop: the test has failed. Do not retry or work around the app.
- Finish with the done action. Its text must say which step failed and why (or that all passed),
  and end with exactly one line: "VERDICT: PASS" if every expectation held, otherwise "VERDICT: FAIL"."""


# Tools the test never needs: web search and typed URLs would bypass the app's UI, and
# search_page/find_elements are newer tools that weaker models often call with wrong arguments.
EXCLUDED_TOOLS = ['search', 'navigate', 'search_page', 'find_elements', 'save_as_pdf', 'upload_file']


async def run_test(task: Task, ctx: Context) -> Verdict:
	browser = BrowserSession(cdp_url=ctx.cdp_url)
	agent = Agent(
		task=build_prompt(task),
		llm=ctx.llm(),
		browser_session=browser,
		tools=Tools(exclude_actions=EXCLUDED_TOOLS),
		use_vision=True,
		use_judge=False,  # the VERDICT line is the oracle; a judge call would add cost
		directly_open_url=False,  # the harness already opened the start page
		max_failures=3,
		final_response_after_failure=False,  # a crashed run must not produce a guessed verdict
		save_conversation_path=ctx.out_dir / 'conversation',
		generate_gif=str(ctx.out_dir / 'agent.gif'),
	)
	history = await agent.run(max_steps=10 + 3 * len(task.steps))
	history.save_to_file(ctx.out_dir / 'history.json')
	if not history.is_done():
		raise RuntimeError(f'Agent stopped without finishing: {[e for e in history.errors() if e][-1:]}')
	final = history.final_result() or ''
	return Verdict(passed=await read_verdict(final, ctx) == 'PASS', reason=final)


async def read_verdict(report: str, ctx: Context) -> str:
	"""Take PASS/FAIL from the report's VERDICT line; models sometimes leave it out, so then ask."""
	match = re.search(r'VERDICT\s*:\s*(PASS|FAIL)', report, re.IGNORECASE)
	if match:
		return match.group(1).upper()
	question = ('Here is a QA tester\'s report on a GUI test case. Did every expectation hold? '
	            f'Answer with exactly one word, PASS or FAIL.\n\n{report}')
	answer = (await ctx.llm().ainvoke([UserMessage(content=question)])).completion.strip().upper()
	if answer.startswith(('PASS', 'FAIL')):
		return answer[:4]
	raise RuntimeError(f'No verdict in report: {report[:300]!r}')
