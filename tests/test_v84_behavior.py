"""Runs the end-to-end V84 scenarios (final security/regression confirmation pass -- timing-safety
fix, CSRF enforcement, security headers, rate limiting, tenant isolation, password storage, real
HTTP requests, fresh database) in a separate process."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v84_end_to_end_scenarios():
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "v84_scenarios.py")], capture_output=True, text=True, timeout=1800)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
