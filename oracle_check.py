"""Instructor sanity check (no LLM): replay each scenario's reference solution, then its
assertion_check. On the clean app the assertion must pass; with the bug injected it must fail.
This verifies the environment, the seed data and the bug injection before grading agents.

Usage (from the repository root):  uv run oracle_check.py [--tasks dev] [--only search]
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

import yaml
from playwright.sync_api import expect, sync_playwright

HOMEWORK = Path(__file__).resolve().parent
sys.path.insert(0, str(HOMEWORK))

from harness import app, tasks  # noqa: E402
from harness.browser import _bug_script  # noqa: E402


def login(page) -> None:
	page.goto(f'{app.APP_URL}/login', wait_until='domcontentloaded')
	page.get_by_role('textbox', name='Email').fill('admin@admin.com')
	page.get_by_role('textbox', name='Password').fill('password')
	page.get_by_role('button', name='Log In').click()
	page.wait_for_function("() => !window.location.pathname.includes('/login')")


def replay(p, tf: tasks.TaskFiles, data: dict, inject: bool) -> str:
	"""Return 'pass' or 'fail' for the task's assertion_check after replaying its solution."""
	app.reset()
	with tempfile.TemporaryDirectory() as profile:
		context = p.chromium.launch_persistent_context(profile, headless=True, viewport={'width': 1280, 'height': 720}, chromium_sandbox=False)
		try:
			if inject:
				context.add_init_script(_bug_script(tf.bug_script.read_text(encoding='utf-8')))
			page = context.pages[0]
			login(page)
			if inject:
				page.evaluate("sessionStorage.setItem('__flash_ui_active__', 'true')")
				page.reload(wait_until='domcontentloaded')
			page.wait_for_load_state('networkidle')
			for step in data['steps']:
				exec(step['solution'], {'page': page, 'expect': expect, 're': re})
				page.wait_for_load_state('networkidle')
			page.wait_for_timeout(800)  # let a just-applied bug settle (injector applies it within 500 ms)
			try:
				exec(data['assertion_check'], {'page': page, 'expect': expect, 're': re})
				return 'pass'
			except AssertionError:
				return 'fail'
		finally:
			context.close()


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument('--tasks', default='dev')
	parser.add_argument('--only', nargs='*')
	args = parser.parse_args()
	expect.set_options(timeout=5_000)
	app.start()
	ok = True
	with sync_playwright() as p:
		for tf in tasks.load(args.tasks):
			if args.only and tf.task.id not in args.only:
				continue
			src = Path(args.tasks) if Path(args.tasks).is_dir() else tasks.TASKS_DIR / args.tasks
			data = yaml.safe_load((src / f'{tf.task.id}.yaml').read_text(encoding='utf-8'))
			clean = replay(p, tf, data, inject=False)
			bug = replay(p, tf, data, inject=True) if tf.bug_script else 'n/a'
			good = clean == 'pass' and bug in ('fail', 'n/a')
			ok &= good
			print(f'{tf.task.id:32} clean: {clean:4}  bug: {bug:4}  {"OK" if good else "PROBLEM"}')
	sys.exit(0 if ok else 1)


if __name__ == '__main__':
	main()
