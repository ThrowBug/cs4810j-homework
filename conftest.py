"""pytest setup for the homework: options, one report folder per run, and the HTML test report.

Each run writes reports/<agent>-<timestamp>/:
  report.html            the test report (open in a browser)
  results.json           per-test verdict, time and tokens; read by metrics.py
  <test>/trace.zip       Playwright trace of the agent's browser session
  <test>/...             whatever the agent saved (the baseline: conversation, history, GIF)
"""

import importlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pytest_html import extras

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')

from harness import app, metrics, tasks  # noqa: E402

VARIANTS = ('clean', 'bug')


def pytest_addoption(parser):
	group = parser.getgroup('homework')
	group.addoption('--agent', default='baseline', help='agent module in agents/ (default: baseline)')
	group.addoption('--task-set', default='dev', help='task set in tasks/, or a folder of *.yaml (default: dev)')
	group.addoption('--headed', action='store_true', help='show the browser window')
	group.addoption('--agent-timeout', type=float, default=600, help='seconds per test before the agent counts as ERROR')


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
	config.hw_runs = []
	config.hw_run_dir = None
	if config.option.collectonly or config.option.help:
		return
	stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
	config.hw_run_dir = ROOT / 'reports' / f'{config.getoption("agent")}-{stamp}'
	config.hw_run_dir.mkdir(parents=True, exist_ok=True)
	if not config.getoption('htmlpath'):
		config.option.htmlpath = str(config.hw_run_dir / 'report.html')
		config.option.self_contained_html = True


def pytest_generate_tests(metafunc):
	if 'case' in metafunc.fixturenames:
		cases = [(tf, v) for tf in tasks.load(metafunc.config.getoption('task_set')) for v in VARIANTS]
		metafunc.parametrize('case', cases, ids=[f'{tf.task.id}-{v}' for tf, v in cases])


@pytest.fixture(scope='session')
def agent(pytestconfig):
	name = pytestconfig.getoption('agent')
	try:
		return importlib.import_module(f'agents.{name}')
	except ModuleNotFoundError as e:
		pytest.exit(f'No agent module agents/{name}.py ({e})', returncode=2)


@pytest.fixture(scope='session')
def bookstack():
	"""Start BookStack once per session (docker compose)."""
	app.start()


@pytest.fixture
def run_dir(pytestconfig):
	return pytestconfig.hw_run_dir


@pytest.fixture
def memory_dir(pytestconfig):
	path = ROOT / 'memory' / pytestconfig.getoption('agent')
	path.mkdir(parents=True, exist_ok=True)
	return path


# ---------- HTML report ----------

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
	outcome = yield
	report = outcome.get_result()
	record = getattr(item, 'hw_record', None)
	if report.when != 'call' or record is None:
		return
	report.hw_record = record
	folder = f'{record["task"]}-{record["variant"]}'
	links = [extras.url(f'{folder}/trace.zip', name='Playwright trace')]
	if (item.config.hw_run_dir / folder / 'agent.gif').exists():
		links.append(extras.url(f'{folder}/agent.gif', name='Agent GIF'))
	note = record['error'] or record['reason'] or ''
	links.append(extras.text(f'Expected {record["expected"]}, agent said {record["verdict"]}\n\n{note}', name='Agent verdict'))
	report.extras = getattr(report, 'extras', []) + links


def pytest_html_report_title(report):
	report.title = 'GUI testing agent: test report'


def pytest_html_results_table_header(cells):
	cells.insert(2, '<th>Verdict</th>')
	cells.insert(3, '<th>Agent seconds</th>')
	cells.insert(4, '<th>Tokens</th>')


def pytest_html_results_table_row(report, cells):
	record = getattr(report, 'hw_record', None)
	if record:
		cells.insert(2, f'<td>{record["verdict"]} (expected {record["expected"]})</td>')
		cells.insert(3, f'<td>{record["seconds"]:.1f}</td>')
		cells.insert(4, f'<td>{record["total_tokens"]:,}</td>')
	else:
		cells[2:2] = ['<td></td>'] * 3


# ---------- results.json and the end-of-run summary ----------

def pytest_sessionfinish(session):
	config = session.config
	if not config.hw_run_dir or not config.hw_runs:
		return
	data = {'agent': config.getoption('agent'), 'model': os.environ.get('LLM_MODEL'), 'task_set': config.getoption('task_set'),
	        'finished': datetime.now().isoformat(timespec='seconds'), 'runs': config.hw_runs}
	(config.hw_run_dir / 'results.json').write_text(json.dumps(data, indent=2), encoding='utf-8')


def pytest_terminal_summary(terminalreporter, config):
	if not config.hw_run_dir or not config.hw_runs:
		return
	sys.stdout.flush()
	metrics.print_runs(metrics.load(config.hw_run_dir))
	metrics.print_summary([config.hw_run_dir])
	rel = config.hw_run_dir.relative_to(ROOT)
	print(f'\nTest report: {rel / "report.html"}')
	print(f'Metrics again, or compared with another run: uv run metrics.py {rel}')
