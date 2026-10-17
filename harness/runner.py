"""Run one scenario in one variant: reset the app, prepare the browser, run the agent, record the result."""

import asyncio
import json
import time
import traceback
from pathlib import Path

from . import app
from .browser import prepared_browser
from .context import Context, Meter
from .tasks import TaskFiles


async def run_case(agent, tf: TaskFiles, variant: str, out_dir: Path, memory_dir: Path, headless: bool, timeout: float) -> dict:
	"""Return the run's record; also written to out_dir/record.json. Artifacts land in out_dir."""
	out_dir.mkdir(parents=True, exist_ok=True)
	app.reset()
	meter = Meter()
	record = {'task': tf.task.id, 'variant': variant, 'expected': 'PASS' if variant == 'clean' else 'FAIL'}
	bug = tf.bug_script if variant == 'bug' else None
	async with prepared_browser(tf.setup_function, bug, headless, trace_path=out_dir / 'trace.zip') as handover:
		ctx = Context(cdp_url=handover.cdp_url, app_url=app.APP_URL, out_dir=out_dir, memory_dir=memory_dir,
		              meter=meter, mark=handover.mark)
		start = time.perf_counter()
		try:
			verdict = await asyncio.wait_for(agent.run_test(tf.task, ctx), timeout)
			await ctx.trace_step(f'Verdict: {"PASS" if verdict.passed else "FAIL"}')
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
