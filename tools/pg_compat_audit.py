"""Static audit: which SQL in this code base will NOT run unchanged on PostgreSQL (it was written for SQLite).
usage: python tools/pg_compat_audit.py [--list]   (no database needed; counts per category and per file)"""
import re, sys, glob, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = [
 ("INSERT OR IGNORE / OR REPLACE (needs ON CONFLICT + a conflict target)", r"INSERT\s+OR\s+(IGNORE|REPLACE)"),
 ("cursor.lastrowid (needs INSERT ... RETURNING id)", r"\.lastrowid"),
 ("PRAGMA statements (sqlite only)", r"PRAGMA\s+\w+"),
 ("sqlite_master / table_info introspection", r"sqlite_master|table_info"),
 ("datetime('now') / date('now') / strftime", r"datetime\(\s*'now|date\(\s*'now|strftime\s*\("),
 ("IFNULL (use COALESCE)", r"\bIFNULL\s*\("),
 ("GROUP_CONCAT (use string_agg)", r"GROUP_CONCAT\s*\("),
 ("AUTOINCREMENT / rowid", r"AUTOINCREMENT|\browid\b"),
 ("CREATE TRIGGER (sqlite syntax)", r"CREATE\s+TRIGGER"),
 ("ALTER TABLE ... ADD COLUMN IF NOT EXISTS emulation / table rebuilds", r"ALTER\s+TABLE\s+\w+\s+RENAME|DROP\s+TABLE"),
 ("executescript (multi-statement)", r"executescript\s*\("),
 ("'?' placeholders (PostgreSQL drivers use %s)", r"execute(?:many)?\s*\(\s*(?:f?\"|f?')[^\"']*\?"),
 ("LIKE on text (sqlite is case-insensitive, PostgreSQL is not)", r"\bLIKE\b"),
 ("GROUP BY with non-aggregated columns (PostgreSQL is strict)", r"GROUP\s+BY"),
 ("random() / RANDOM()", r"\bRANDOM\s*\(\s*\)"),
 ("INTEGER-vs-TEXT comparison risk: tenant_id (TEXT) compared to ids", r"tenant_id\s*=\s*\?"),
]
files = [f for f in glob.glob(ROOT + "/*.py")] + glob.glob(ROOT + "/schema.sql")
totals, per = collections.Counter(), collections.defaultdict(collections.Counter)
hits = collections.defaultdict(list)
for f in files:
    for n, line in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
        for name, rx in RULES:
            if re.search(rx, line, re.I):
                totals[name] += 1; per[os.path.basename(f)][name] += 1; hits[name].append(f"{os.path.basename(f)}:{n}")
print(f"{'category':78s} count")
for name, _ in RULES: print(f"{name:78s} {totals[name]:5d}")
print("\nexecute() calls:", sum(open(f, errors='ignore').read().count('.execute(') for f in files))
print("\nbusiest files:"); 
for f, c in sorted(per.items(), key=lambda kv: -sum(kv[1].values()))[:6]: print(f"  {f:24s} {sum(c.values()):5d}")
if "--list" in sys.argv:
    for name, _ in RULES:
        print("\n#", name); print("  " + ", ".join(hits[name][:400]))
