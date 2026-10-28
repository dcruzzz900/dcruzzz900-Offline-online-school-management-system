"""Runs the end-to-end V87 scenarios (School Settings, Branding and Cumulative Results fixes:
relocated auto-comment explanation, school address on result sheets/broadsheets, accent-color
save bug, sitewide cumulative-results breakdown across all 16 templates, and a visible warning
when the PDF-rendering engine is unavailable) in a separate process."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v87_end_to_end_scenarios():
    proc = subprocess.run([sys.executable, str(ROOT / "tests" / "v87_scenarios.py")], capture_output=True, text=True, timeout=1800)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
