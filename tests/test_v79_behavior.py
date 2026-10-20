"""Runs the end-to-end V79 scenarios (real HTTP requests + PDF page-count checks + real
headless-browser render of the overflow warning, fresh database) in a separate process."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v79_end_to_end_scenarios():
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "v79_scenarios.py")], capture_output=True, text=True, timeout=1800)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
