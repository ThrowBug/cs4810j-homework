"""One-time setup (Windows, macOS, Linux): Chromium for Playwright, the .env file, and a check
that Docker is available. Run it with:  uv run install.py   (uv installs the Python packages first)
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

print('==> Installing Chromium for Playwright')
subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], check=True)

if not (HERE / '.env').exists():
	shutil.copy(HERE / '.env.example', HERE / '.env')
	print('==> Created .env from .env.example: put your API key in it')

print('==> Checking Docker')
try:
	subprocess.run(['docker', 'compose', 'version'], check=True, capture_output=True)
	subprocess.run(['docker', 'info'], check=True, capture_output=True)
	print('Docker is ready.')
except (OSError, subprocess.CalledProcessError):
	print('Docker is not available or not running. Install Docker Desktop (Windows, macOS) or Docker Engine (Linux) and start it.')
	sys.exit(1)

print('\nSetup complete. Put your API key in .env, then run: uv run pytest -k search')
