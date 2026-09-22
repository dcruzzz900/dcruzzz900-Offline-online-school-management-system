"""Tiny dependency-free test runner (pytest also works if you have it):
    python tests/run.py            # everything
    python tests/run.py conflict   # only files whose name contains 'conflict'
"""
import glob
import importlib
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
pattern = sys.argv[1] if len(sys.argv) > 1 else ""
passed = failed = 0
for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
    name = os.path.basename(path)[:-3]
    if pattern and pattern not in name:
        continue
    mod = importlib.import_module(name)
    for fn_name in sorted(n for n in dir(mod) if n.startswith("test_")):
        try:
            getattr(mod, fn_name)()
            passed += 1
            print(f"PASS  {name}.{fn_name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}.{fn_name}")
            traceback.print_exc()
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
