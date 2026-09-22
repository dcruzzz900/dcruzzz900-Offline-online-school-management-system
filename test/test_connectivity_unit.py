"""Unit tests (fake network + fake clock) for the connectivity monitor."""
import os
import subprocess
from helpers import ROOT


def test_connectivity_monitor_logic():
    out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "connectivity_test.js")], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "connectivity OK" in out.stdout
