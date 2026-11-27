"""Runs the end-to-end V86 scenarios (sitewide collapsible Highlights & Instructions: hiding
highlights, tips, and guidance text by default behind a consistent Help control on every
screen, across every role) in a separate process."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v86_end_to_end_scenarios():
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "v86_scenarios.py")], capture_output=True, text=True, timeout=1800)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
