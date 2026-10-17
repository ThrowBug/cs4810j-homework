"""Print the metrics of a test report, or compare two (before -> after).

  uv run metrics.py                                  # the latest report
  uv run metrics.py baseline my_agent                # each agent's latest report, compared
  uv run metrics.py reports/<before> reports/<after> # two report folders, compared
  uv run metrics.py --last 2                         # the two latest reports, compared
"""

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import metrics  # noqa: E402


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument('reports', nargs='*', help='one or two report folders or agent names (default: the latest report)')
	parser.add_argument('--last', type=int, choices=(1, 2), help='use the latest one or two reports')
	args = parser.parse_args()
	if len(args.reports) > 2:
		parser.error('give one report, or two to compare')
	dirs = [metrics.resolve(r) for r in args.reports] or metrics.latest(args.last or 1)
	if len(dirs) == 1:
		metrics.print_runs(metrics.load(dirs[0]))
	metrics.print_summary(dirs)


if __name__ == '__main__':
	main()
