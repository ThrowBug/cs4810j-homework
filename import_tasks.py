"""Instructor tool: build a task set from a WebTestPilot-benchmark checkout.

  git clone https://github.com/code-philia/WebTestPilot-benchmark.git
  uv run import_tasks.py path/to/WebTestPilot-benchmark          # writes tasks/holdout/

By default it imports every BookStack scenario that is not in the dev set and has a bug
script. Check the new set with:  uv run oracle_check.py --tasks holdout
Then grade with:  uv run evaluate.py --agent <student> --tasks holdout
"""

import argparse
import shutil
from pathlib import Path

HOMEWORK = Path(__file__).resolve().parent
DEV = HOMEWORK / 'tasks' / 'dev'


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('benchmark', type=Path, help='path to a WebTestPilot-benchmark checkout')
	parser.add_argument('--to', type=Path, default=HOMEWORK / 'tasks' / 'holdout')
	parser.add_argument('--only', nargs='*', help='import only these task ids')
	args = parser.parse_args()

	src = args.benchmark / 'bookstack'
	dev_ids = {p.stem for p in DEV.glob('*.yaml')}
	(args.to / 'bugs').mkdir(parents=True, exist_ok=True)
	imported = []
	for case in sorted((src / 'test_cases').glob('*.yaml')):
		bug = src / 'bugs' / f'{case.stem}.js'
		if case.stem in dev_ids or not bug.exists() or (args.only and case.stem not in args.only):
			continue
		shutil.copy(case, args.to / case.name)
		shutil.copy(bug, args.to / 'bugs' / bug.name)
		imported.append(case.stem)
	print(f'Imported {len(imported)} scenarios into {args.to}:\n  ' + '\n  '.join(imported))


if __name__ == '__main__':
	main()
