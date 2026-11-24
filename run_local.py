#!/usr/bin/env python3
"""Run My School Hub on ONE computer in the school, with no internet (Local SQLite Installation).

    python run_local.py                 # this computer only:   http://localhost:5050
    python run_local.py --lan           # other devices in the school network can open it too
    python run_local.py --data D:\\school-data --port 8080

Everything is stored in the data folder (default ./school-data): school.db (SQLite), uploaded files and backups/.
A verified backup is taken at start-up and every few hours (see local_backup.py to restore).

Phones/tablets: browsers only allow install-as-app, offline pages and encrypted offline storage on https:// or http://localhost.
On the school computer itself use http://localhost:PORT. For other devices over Wi-Fi, put a local HTTPS certificate in front of it
(for example Caddy or mkcert); without it they still work online against this computer, just without the offline browser features."""
import argparse
import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.environ.get("DATA_DIR") or os.path.join(ROOT, "school-data"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5050")))
    ap.add_argument("--lan", action="store_true", help="listen on the school network, not just this computer")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--backup-hours", type=float, default=6)
    a = ap.parse_args(argv)

    os.makedirs(a.data, exist_ok=True)
    os.environ["DATA_DIR"] = os.path.abspath(a.data)          # must be set before db/app are imported
    os.environ.setdefault("FLASK_ENV", "local")
    import local_backup
    if os.path.exists(os.path.join(os.environ["DATA_DIR"], "school.db")):
        try:
            print("Safety backup before start-up:", local_backup.make_backup(prefix="school"))
        except Exception as exc:
            print("Safety backup skipped:", exc)
    import app as school_app                                  # runs migrations on the existing database
    local_backup.BackupScheduler(hours=a.backup_hours).start()

    host = "0.0.0.0" if a.lan else "127.0.0.1"
    url = f"http://localhost:{a.port}"
    print(f"\nMy School Hub is running. Open {url}\nData folder: {os.environ['DATA_DIR']}\nPress Ctrl+C to stop.\n")
    if not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        from waitress import serve                           # pure-Python server that works on Windows
        serve(school_app.app, host=host, port=a.port, threads=8)
    except ImportError:
        school_app.app.run(host=host, port=a.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
