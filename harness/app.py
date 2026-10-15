"""The BookStack app under test: start it, and reset its database before every run."""

import subprocess
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ENV_DIR = Path(__file__).resolve().parent.parent / 'env'
APP_URL = 'http://localhost:8080'


def _compose(*args: str, stdin: bytes | None = None) -> None:
	subprocess.run(['docker', 'compose', *args], cwd=ENV_DIR, input=stdin, check=True, capture_output=True)


def start() -> None:
	"""Start the containers (idempotent) and wait until BookStack answers."""
	_compose('up', '-d', '--wait')


def is_up() -> bool:
	try:
		with urllib.request.urlopen(f'{APP_URL}/login', timeout=5) as res:
			return res.status == 200
	except OSError:
		return False


def reset() -> None:
	"""Recreate the database from the benchmark's baseline and seed (about one second)."""
	_compose('exec', '-T', 'db', 'mysql', '-uroot', '-proot', '-e', 'DROP DATABASE IF EXISTS bookstack; CREATE DATABASE bookstack;')
	_compose('exec', '-T', 'db', 'mysql', '-uadmin', '-padmin', 'bookstack', stdin=(ENV_DIR / 'baseline.sql').read_bytes())
	# Same substitution as the benchmark's seed-loader.sh: seeded timestamps are "yesterday".
	yesterday = (date.today() - timedelta(days=1)).isoformat()
	seed = (ENV_DIR / 'seed.sql').read_text(encoding='utf-8').replace('YYYY-MM-DD', yesterday)
	_compose('exec', '-T', 'db', 'mysql', '-uadmin', '-padmin', 'bookstack', stdin=seed.encode('utf-8'))
