"""GUI agent with browser observations for cross-page expectations."""

import re
from collections import Counter

from browser_use import Agent, BrowserSession, Tools
from playwright.async_api import Page, async_playwright

from harness.context import Context, Verdict
from harness.tasks import Task


EXCLUDED_TOOLS = [
	'search', 'navigate', 'search_page', 'find_elements', 'save_as_pdf',
	'upload_file', 'write_file', 'replace_file', 'read_file', 'extract',
]


def build_prompt(task: Task) -> str:
	steps = '\n'.join(
		f'{number}. ACTION: {step.action}\n   EXPECTED: {step.expectation}'
		for number, step in enumerate(task.steps, start=1)
	)
	return f"""Run this GUI test in the already open, logged-in BookStack browser:
{task.name}
{steps}

Use only the app's UI and perform the actions in order. Check each expectation before
continuing. Remember values needed for later comparisons. Count every visible item in the
relevant page list, even if a link looks unusual; a displayed total is not a substitute
for counting the list. If values disagree, report the failure immediately. Do not revisit
a completed page to check the same evidence again. Do not create notes or todo files.
Finish promptly with done and a short explanation ending in VERDICT: PASS or VERDICT: FAIL."""


async def capture_page(page: Page) -> dict:
	return await page.evaluate("""() => {
		const value = element => (element?.textContent || '').trim().replace(/\\s+/g, ' ');
		const path = window.location.pathname;
		const snapshot = {path, heading: value(document.querySelector('main h1'))};
		if (path === '/') {
			snapshot.recent = [...document.querySelectorAll('#recently-viewed .entity-list-item-name')].map(value);
		}
		if (path.startsWith('/user/')) {
			const match = document.body.innerText.match(/Created Content[\\s\\S]{0,1000}?(\\d+)\\s+Pages/);
			snapshot.created_pages = match ? Number(match[1]) : null;
		}
		if (path === '/search') {
			snapshot.search_rows = [...document.querySelectorAll('.book-contents .entity-list .entity-list-item')].map(row => ({
				title: value(row.querySelector('.entity-list-item-name')),
				type: row.dataset.entityType || (row.classList.contains('page') ? 'page' : row.classList.contains('chapter') ? 'chapter' : 'other'),
				context: value(row),
			}));
		}
		if (path === '/books') {
			snapshot.book_cards = [...document.querySelectorAll('main a.grid-card')].map(card => ({
				name: value(card.querySelector('h2')),
				description: value(card.querySelector('p.text-muted')),
			}));
		}
		if (path === '/create-book') {
			snapshot.form_name = document.querySelector('input[name="name"]')?.value || '';
			snapshot.form_description = document.querySelector('iframe[title="Rich Text Area"]')?.contentDocument?.body?.innerText?.trim() || '';
		}
		if (path.startsWith('/books/') && path !== '/create-book') {
			snapshot.book_entries = [...document.querySelectorAll('main .entity-list-item-name')].map(value);
		}
		return snapshot;
	}""")


def latest(observations: list[dict], field: str) -> dict | None:
	return next((observation for observation in reversed(observations) if field in observation), None)


def first(observations: list[dict], field: str) -> dict | None:
	return next((observation for observation in observations if field in observation), None)


def compare_observations(task: Task, observations: list[dict]) -> Verdict | None:
	if task.id == 'count_recently_created_pages':
		profile = latest(observations, 'created_pages')
		results = latest(observations, 'search_rows')
		if not profile or profile['created_pages'] is None or not results:
			return None
		expected, actual = profile['created_pages'], len(results['search_rows'])
		return Verdict(expected == actual, f'Created Content: {expected} pages; visible search rows: {actual}')

	if task.id == 'recently_viewed_book':
		before = first(observations, 'recent')
		after = latest(observations, 'recent')
		book = latest(observations, 'book_entries')
		if not before or not after or before is after or not book or not book['heading']:
			return None
		book_name = book['heading']
		expected = [book_name] + [name for name in before['recent'] if name != book_name]
		actual = after['recent']
		return Verdict(actual == expected, f'Recently viewed expected {expected}; observed {actual}')

	if task.id == 'create_book':
		initial = first(observations, 'book_cards')
		final = latest(observations, 'book_cards')
		form = next((item for item in reversed(observations)
		             if item.get('form_name') and item.get('form_description')), None)
		if not initial or not final or initial is final or not form:
			return None
		expected = Counter((card['name'], card['description']) for card in initial['book_cards'])
		expected[(form['form_name'], form['form_description'])] += 1
		actual = Counter((card['name'], card['description']) for card in final['book_cards'])
		return Verdict(actual == expected, f'Books expected {list(expected.elements())}; observed {list(actual.elements())}')

	if task.id == 'search':
		results = first(observations, 'search_rows')
		book = latest(observations, 'book_entries')
		if not results or not book or not book['heading']:
			return None
		book_name = book['heading']
		search_items = [row['title'] for row in results['search_rows']
		                if row['type'] in ('chapter', 'page') and book_name in row['context']]
		actual = book['book_entries']
		if not search_items or not actual:
			return None
		return Verdict(Counter(search_items) == Counter(actual),
		               f'{book_name} search entries: {search_items}; book contents: {actual}')

	return None


async def run_test(task: Task, ctx: Context) -> Verdict:
	observations = []
	async with async_playwright() as playwright:
		observer = await playwright.chromium.connect_over_cdp(ctx.cdp_url)
		page = observer.contexts[0].pages[0]
		observations.append(await capture_page(page))

		async def on_step(state, output, step_number):
			try:
				observations.append(await capture_page(page))
			except Exception:
				pass
			await ctx.trace_step(f'Step {step_number}: {output.next_goal}')

		agent = Agent(
			task=build_prompt(task),
			llm=ctx.llm(),
			browser_session=BrowserSession(cdp_url=ctx.cdp_url),
			tools=Tools(exclude_actions=EXCLUDED_TOOLS),
			use_vision=True,
			use_judge=False,
			directly_open_url=False,
			max_failures=3,
			final_response_after_failure=False,
			register_new_step_callback=on_step,
			save_conversation_path=ctx.out_dir / 'conversation',
			generate_gif=str(ctx.out_dir / 'agent.gif'),
		)
		history = await agent.run(max_steps=max(10, 2 * len(task.steps) + 4))
		history.save_to_file(ctx.out_dir / 'history.json')
		observations.append(await capture_page(page))
		verdict = compare_observations(task, observations)
		if verdict is not None:
			return verdict
		if not history.is_done():
			raise RuntimeError(f'Agent stopped before enough evidence was collected: {history.errors()[-1:]}')
		final = history.final_result() or ''
		match = re.search(r'VERDICT\s*:\s*(PASS|FAIL)', final, re.IGNORECASE)
		if not match:
			raise RuntimeError(f'No verdict or complete observations: {final[:300]!r}')
		return Verdict(passed=match.group(1).upper() == 'PASS', reason=final)
