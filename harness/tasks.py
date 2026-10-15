"""Test scenarios in WebTestPilot-benchmark format.

Agents only ever see `Task`: the name and each step's action and expectation. The
benchmark's ground truth (solution, action_check, url, assertion_check) stays in the
harness, like the benchmark's oracle.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

TASKS_DIR = Path(__file__).resolve().parent.parent / 'tasks'


@dataclass(frozen=True)
class Step:
	action: str
	expectation: str


@dataclass(frozen=True)
class Task:
	id: str  # filename stem, e.g. "create_book"
	name: str
	steps: tuple[Step, ...]


@dataclass(frozen=True)
class TaskFiles:
	task: Task
	setup_function: str | None
	bug_script: Path | None


def load(task_set: str | Path) -> list[TaskFiles]:
	"""Load every *.yaml in tasks/<task_set>/ (or a folder path), with bug scripts from its bugs/."""
	folder = Path(task_set)
	if not folder.is_dir():
		folder = TASKS_DIR / str(task_set)
	files = sorted(folder.glob('*.yaml'))
	if not files:
		raise SystemExit(f'No *.yaml scenarios found in {folder}')
	bugs_dir = folder / 'bugs'
	out = []
	for f in files:
		data = yaml.safe_load(f.read_text(encoding='utf-8'))
		steps = tuple(Step(s['action'].strip(), s['expectation'].strip()) for s in data['steps'])
		bug = bugs_dir / f'{f.stem}.js'
		out.append(TaskFiles(Task(f.stem, data['name'], steps), data.get('setup_function'), bug if bug.exists() else None))
	return out
