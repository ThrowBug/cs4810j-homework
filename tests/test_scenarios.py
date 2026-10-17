"""One test per scenario and variant, e.g. test_scenario[search-bug].

A test passes when the agent's verdict is correct: PASS on the clean app, FAIL with the bug.
Select tests with pytest's -k, for example:  -k search   -k "bug"   -k "create_book and clean"
"""

import asyncio

import pytest

from harness.runner import run_case


def test_scenario(case, agent, bookstack, run_dir, memory_dir, request):
	tf, variant = case
	config = request.config
	record = asyncio.run(run_case(agent, tf, variant, run_dir / f'{tf.task.id}-{variant}', memory_dir,
	                              headless=not config.getoption('headed'), timeout=config.getoption('agent_timeout')))
	request.node.hw_record = record
	config.hw_runs.append(record)
	if record['verdict'] == 'ERROR':
		pytest.fail(f'The agent did not reach a verdict: {record["error"]}')
	assert record['correct'], f'Expected {record["expected"]}, the agent said {record["verdict"]}: {record["reason"][:500]}'
