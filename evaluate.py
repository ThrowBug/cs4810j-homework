"""Evaluate a GUI testing agent on BookStack scenarios, each run on the clean app and with its bug.

Usage (from the repository root):
  uv run evaluate.py --agent baseline
  uv run evaluate.py --agent my_agent --only search create_book --variants bug
"""

import argparse
import asyncio
import importlib
import json
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

HOMEWORK = Path(__file__).resolve().parent
sys.path.insert(0, str(HOMEWORK))
load_dotenv(HOMEWORK / '.env')
# Windows consoles default to a legacy code page; browser-use logs emoji.
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.stderr.reconfigure(encoding='utf-8')

from harness import app, tasks  # noqa: E402
from harness.browser import prepared_browser  # noqa: E402
from harness.context import Context, Meter  # noqa: E402

VARIANTS = ('clean', 'bug')


async def run_one(agent, tf: tasks.TaskFiles, variant: str, out_dir: Path, memory_dir: Path, headless: bool, timeout: float) -> dict:
	out_dir.mkdir(parents=True, exist_ok=True)
	app.reset()
	meter = Meter()
	record = {'task': tf.task.id, 'variant': variant, 'expected': 'PASS' if variant == 'clean' else 'FAIL'}
	async with prepared_browser(tf.setup_function, tf.bug_script if variant == 'bug' else None, headless) as cdp_url:
		ctx = Context(cdp_url=cdp_url, app_url=app.APP_URL, out_dir=out_dir, memory_dir=memory_dir, meter=meter)
		start = time.perf_counter()
		try:
			verdict = await asyncio.wait_for(agent.run_test(tf.task, ctx), timeout)
			record |= {'verdict': 'PASS' if verdict.passed else 'FAIL', 'reason': verdict.reason, 'error': None}
		except Exception as e:  # a crash or timeout is a run without a verdict
			record |= {'verdict': 'ERROR', 'reason': '', 'error': f'{type(e).__name__}: {e}'}
			(out_dir / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
		record['seconds'] = round(time.perf_counter() - start, 2)
	record |= {'correct': record['verdict'] == record['expected'], 'llm_calls': meter.calls,
	           'prompt_tokens': meter.prompt_tokens, 'completion_tokens': meter.completion_tokens,
	           'total_tokens': meter.total_tokens, 'tokens_by_model': meter.by_model}
	(out_dir / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
	return record


def summarize(records: list[dict]) -> dict:
	n = len(records)
	bug = [r for r in records if r['variant'] == 'bug']
	clean = [r for r in records if r['variant'] == 'clean']
	reported_fail = [r for r in records if r['verdict'] == 'FAIL']
	ratio = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
	return {
		'runs': n,
		'errors': sum(r['verdict'] == 'ERROR' for r in records),
		'accuracy': ratio(sum(r['correct'] for r in records), n),
		'bug_recall': ratio(sum(r['verdict'] == 'FAIL' for r in bug), len(bug)),  # bugs caught
		'false_alarm_rate': ratio(sum(r['verdict'] == 'FAIL' for r in clean), len(clean)),  # clean apps failed
		'fail_precision': ratio(sum(r['variant'] == 'bug' for r in reported_fail), len(reported_fail)),
		'mean_seconds': round(sum(r['seconds'] for r in records) / n, 1),
		'mean_tokens': round(sum(r['total_tokens'] for r in records) / n),
		'mean_llm_calls': round(sum(r['llm_calls'] for r in records) / n, 1),
	}


def print_report(agent_name: str, records: list[dict], summary: dict) -> None:
	print(f'\n{"task":32} {"variant":7} {"expect":6} {"got":6} {"ok":3} {"sec":>7} {"tokens":>8} {"calls":>5}')
	for r in records:
		ok = 'yes' if r['correct'] else 'NO'
		print(f'{r["task"]:32} {r["variant"]:7} {r["expected"]:6} {r["verdict"]:6} {ok:3} {r["seconds"]:7.1f} {r["total_tokens"]:8} {r["llm_calls"]:5}')
	print(f'\n{agent_name}: accuracy {summary["accuracy"]}, bug recall {summary["bug_recall"]}, '
	      f'false alarms {summary["false_alarm_rate"]}, errors {summary["errors"]}/{summary["runs"]}')
	print(f'cost per run: {summary["mean_seconds"]} s, {summary["mean_tokens"]} tokens, {summary["mean_llm_calls"]} LLM calls')


async def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('--agent', default='baseline', help='module in homework/agents/ (default: baseline)')
	parser.add_argument('--tasks', default='dev', help='task set under homework/tasks/, or a folder of *.yaml (default: dev)')
	parser.add_argument('--only', nargs='*', help='run only these task ids')
	parser.add_argument('--variants', nargs='*', default=list(VARIANTS), choices=VARIANTS)
	parser.add_argument('--timeout', type=float, default=600, help='seconds per run before it counts as an ERROR')
	parser.add_argument('--headed', action='store_true', help='show the browser window')
	args = parser.parse_args()

	agent = importlib.import_module(f'agents.{args.agent}')
	selected = [tf for tf in tasks.load(args.tasks) if not args.only or tf.task.id in args.only]
	if not selected:
		raise SystemExit(f'No tasks match --only {args.only}')

	print('Starting BookStack (docker compose)...')
	app.start()
	stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
	run_dir = HOMEWORK / 'results' / args.agent / stamp
	memory_dir = HOMEWORK / 'memory' / args.agent
	memory_dir.mkdir(parents=True, exist_ok=True)

	records = []
	for tf in selected:
		for variant in args.variants:
			print(f'\n=== {tf.task.id} [{variant}]')
			r = await run_one(agent, tf, variant, run_dir / f'{tf.task.id}-{variant}', memory_dir, not args.headed, args.timeout)
			print(f'=== {tf.task.id} [{variant}]: expected {r["expected"]}, got {r["verdict"]} in {r["seconds"]} s, {r["total_tokens"]} tokens')
			records.append(r)
			with open(run_dir / 'runs.jsonl', 'a', encoding='utf-8') as f:
				f.write(json.dumps(r) + '\n')

	summary = {'agent': args.agent, 'tasks': args.tasks, 'model_default': __import__('os').environ.get('LLM_MODEL')} | summarize(records)
	(run_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
	print_report(args.agent, records, summary)
	print(f'\nResults: {run_dir}')


if __name__ == '__main__':
	asyncio.run(main())
