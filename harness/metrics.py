"""Compute and print the homework metrics from a test report's results.json."""

import json
from pathlib import Path

REPORTS = Path(__file__).resolve().parent.parent / 'reports'


def load(report_dir: Path) -> dict:
	"""results.json of a report: {'agent', 'model', 'started', 'runs': [record, ...]}."""
	path = Path(report_dir) / 'results.json'
	if not path.exists():
		raise SystemExit(f'No results.json in {report_dir}: is this a test report folder?')
	return json.loads(path.read_text(encoding='utf-8'))


def resolve(ref: str) -> Path:
	"""A report folder, or an agent name meaning that agent's latest report."""
	if Path(ref).is_dir():
		return Path(ref)
	runs = sorted(REPORTS.glob(f'{ref}-*/results.json'), key=lambda p: p.stat().st_mtime)
	if not runs:
		raise SystemExit(f'"{ref}" is neither a report folder nor an agent with a report in {REPORTS}')
	return runs[-1].parent


def latest(n: int = 1) -> list[Path]:
	runs = sorted((p for p in REPORTS.glob('*') if (p / 'results.json').exists()), key=lambda p: p.stat().st_mtime)
	if len(runs) < n:
		raise SystemExit(f'Need {n} test report(s) in {REPORTS}, found {len(runs)}. Run pytest first.')
	return runs[-n:]


def summarize(runs: list[dict]) -> dict:
	n = len(runs)
	bug = [r for r in runs if r['variant'] == 'bug']
	clean = [r for r in runs if r['variant'] == 'clean']
	ratio = lambda a, b: a / b if b else None  # noqa: E731
	return {
		'runs': n,
		'accuracy': ratio(sum(r['correct'] for r in runs), n),
		'bug_recall': ratio(sum(r['verdict'] == 'FAIL' for r in bug), len(bug)),
		'false_alarm_rate': ratio(sum(r['verdict'] == 'FAIL' for r in clean), len(clean)),
		'errors': sum(r['verdict'] == 'ERROR' for r in runs),
		'mean_seconds': ratio(sum(r['seconds'] for r in runs), n),
		'mean_tokens': ratio(sum(r['total_tokens'] for r in runs), n),
		'mean_llm_calls': ratio(sum(r['llm_calls'] for r in runs), n),
		'total_seconds': sum(r['seconds'] for r in runs),
		'total_tokens': sum(r['total_tokens'] for r in runs),
	}


# (key, label, format, higher_is_better)
ROWS = [
	('accuracy', 'Accuracy', '{:.2f}', True),
	('bug_recall', 'Bug recall', '{:.2f}', True),
	('false_alarm_rate', 'False alarm rate', '{:.2f}', False),
	('errors', 'Errors', '{:d}', False),
	('mean_seconds', 'Seconds per test', '{:.1f}', False),
	('mean_tokens', 'Tokens per test', '{:,.0f}', False),
	('mean_llm_calls', 'LLM calls per test', '{:.1f}', False),
	('total_seconds', 'Total seconds', '{:.0f}', False),
	('total_tokens', 'Total tokens', '{:,.0f}', False),
]


def _fmt(fmt: str, v) -> str:
	return '-' if v is None else fmt.format(v)


def print_runs(report: dict) -> None:
	print(f'\n{"test":42} {"verdict":8} {"correct":8} {"seconds":>8} {"tokens":>9} {"calls":>6}')
	for r in report['runs']:
		name = f'{r["task"]}[{r["variant"]}]'
		print(f'{name:42} {r["verdict"]:8} {"yes" if r["correct"] else "NO":8} {r["seconds"]:8.1f} {r["total_tokens"]:9,} {r["llm_calls"]:6}')


def print_summary(report_dirs: list[Path]) -> None:
	reports = [load(d) for d in report_dirs]
	sums = [summarize(r['runs']) for r in reports]
	titles = [f'{r["agent"]} ({Path(d).name})' for r, d in zip(reports, report_dirs)]
	width = max(26, *(len(t) + 2 for t in titles))
	header = f'\n{"metric":20}' + ''.join(f'{t:>{width}}' for t in titles) + ('     change' if len(reports) == 2 else '')
	print(header)
	print('-' * (len(header) - 1))
	for key, label, fmt, higher_better in ROWS:
		cells = ''.join(f'{_fmt(fmt, s[key]):>{width}}' for s in sums)
		change = ''
		if len(sums) == 2 and sums[0][key] is not None and sums[1][key] is not None:
			old, new = sums[0][key], sums[1][key]
			if old == new:
				change = '     same'
			else:
				better = (new > old) == higher_better
				pct = f' ({(new - old) / old * 100:+.0f}%)' if old else ''
				change = f'     {"better" if better else "worse"}{pct}'
		print(f'{label:20}{cells}{change}')
	if len(reports) == 2 and _tests(reports[0]) != _tests(reports[1]):
		print('\nNote: the two reports ran different tests, so the comparison is not like for like.')


def _tests(report: dict) -> set[str]:
	return {f'{r["task"]}[{r["variant"]}]' for r in report['runs']}
