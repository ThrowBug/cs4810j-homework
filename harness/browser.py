"""Prepare the browser an agent receives, following WebTestPilot-benchmark runtime/init.py:
launch Chromium, run the task's login, optionally inject the task's bug, reload, and only
then hand the browser to the agent over CDP. While the agent runs, Playwright records a trace
(screenshots, DOM snapshots, network) that opens in trace.playwright.dev.

The Playwright connection stays open while the agent runs, because the injected bug is a
Playwright init script that must keep firing on every navigation.
"""

import re
import socket
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, NamedTuple

from playwright.async_api import Page, async_playwright

from .app import APP_URL

INJECTOR = Path(__file__).resolve().parent / 'bug_injector.js'


async def _login_to_bookstack(page: Page) -> None:
	await page.goto(f'{APP_URL}/login', wait_until='domcontentloaded', timeout=30_000)
	await page.get_by_role('textbox', name='Email').fill('admin@admin.com')
	await page.get_by_role('textbox', name='Password').fill('password')
	await page.get_by_role('button', name='Log In').click()
	await page.wait_for_load_state('domcontentloaded')
	await page.wait_for_function("() => !window.location.pathname.includes('/login')", timeout=30_000)


SETUP_FUNCTIONS = {'login_to_bookstack': _login_to_bookstack}


def _bug_script(bug_js: str) -> str:
	"""Merge one bug definition into the injector template (benchmark: prepare_bug_script)."""
	is_cond = re.findall(r'// BEGIN isConditionMet\s*(.*?)\s*// END isConditionMet', bug_js, re.DOTALL)
	on_cond = re.findall(r'// BEGIN onConditionMet\s*(.*?)\s*// END onConditionMet', bug_js, re.DOTALL)
	script = INJECTOR.read_text(encoding='utf-8')
	script = script.replace('const isConditionMet = () => {};', is_cond[-1])
	script = script.replace('const onConditionMet = () => {};', on_cond[-1])
	return script.replace('{{INJECTOR_KIND}}', 'bug')


def _free_port() -> int:
	with socket.socket() as s:
		s.bind(('127.0.0.1', 0))
		return s.getsockname()[1]


class Handover(NamedTuple):
	cdp_url: str  # where the agent attaches
	mark: Callable[[str], Awaitable[None]]  # add a named step, with a page snapshot, to the trace


@asynccontextmanager
async def prepared_browser(setup_function: str | None, bug_script: Path | None, headless: bool, trace_path: Path | None = None) -> AsyncIterator[Handover]:
	"""Yield a Handover for a logged-in browser on the start page, with the bug active if given."""
	port = _free_port()
	async with async_playwright() as p:
		with tempfile.TemporaryDirectory(prefix='gui-agent-') as profile:
			# A persistent context is the browser's default context, so an agent that
			# attaches over CDP shares its tab, cookies and sessionStorage.
			context = await p.chromium.launch_persistent_context(
				profile,
				headless=headless,
				viewport={'width': 1280, 'height': 720},
				args=[f'--remote-debugging-port={port}', '--no-first-run', '--no-default-browser-check'],
				chromium_sandbox=False,
			)
			try:
				if bug_script:
					await context.add_init_script(_bug_script(bug_script.read_text(encoding='utf-8')))
				page = context.pages[0] if context.pages else await context.new_page()
				if setup_function:
					await SETUP_FUNCTIONS[setup_function](page)
				else:
					await page.goto(APP_URL, wait_until='domcontentloaded')
				if bug_script:
					# The injector stays dormant until this flag is set, so login is never affected.
					await page.evaluate("sessionStorage.setItem('__flash_ui_active__', 'true')")
					await page.reload(wait_until='domcontentloaded')
				try:
					await page.wait_for_load_state('networkidle', timeout=30_000)
				except Exception:
					pass
				if trace_path:
					await context.tracing.start(screenshots=True, snapshots=True)

				async def mark(title: str) -> None:
					# The agent acts over CDP, so Playwright sees no actions of its own. A group with
					# one cheap page call gives the trace viewer a named step with a DOM snapshot.
					if not trace_path or not context.pages:
						return
					await context.tracing.group(title)
					try:
						await context.pages[-1].evaluate('() => document.title')
					except Exception:
						pass  # the page may be navigating; the step name is still recorded
					finally:
						await context.tracing.group_end()

				yield Handover(f'http://127.0.0.1:{port}', mark)
			finally:
				if trace_path:
					try:
						await context.tracing.stop(path=trace_path)
					except Exception:
						pass  # tracing never started, e.g. login failed
				await context.close()
