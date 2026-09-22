"""Conflict-resolution rules for multi-device sync.

Kept free of Flask/SQLite so the rules can be unit-tested (and reasoned
about) on their own. sync_api.py calls `decide()` whenever a pushed change
touches a row that has moved on since the device last saw it.

The rules (also documented for admins in OFFLINE_ARCHITECTURE.md):

  no concurrent change   -> the change is simply applied.
  POLICY_MERGE           -> field-level three-way merge. The device sends the
                            field values it last synced (`base`). Fields the
                            device changed are applied on top of the server's
                            current row, so two teachers editing DIFFERENT
                            fields (say, one fixes a CA1, another adds the
                            exam mark) both keep their work. If both changed
                            the SAME field to DIFFERENT values, nothing is
                            overwritten: both versions are kept and a person
                            resolves it.
  POLICY_LATEST_WINS     -> for low-stakes, frequently re-taken data such as
                            attendance marks: the later edit wins, judged by
                            the device's own timestamp (clamped so a phone with
                            a clock set to next year cannot win forever). The
                            losing value is never lost silently: it is written
                            to the audit trail.
  POLICY_MANUAL          -> any concurrent change becomes a conflict for a
                            person to resolve.
"""
import datetime

POLICY_MERGE = "merge"
POLICY_LATEST_WINS = "latest_wins"
POLICY_MANUAL = "manual"

# A device clock may run ahead of the server by at most this much before we
# stop trusting it for "who edited last" decisions.
MAX_CLOCK_SKEW_SECONDS = 300


def parse_ts(value):
    """Parse an ISO-8601 timestamp (with or without 'Z' / milliseconds /
    an offset) into a naive UTC datetime. Returns None if unparseable."""
    if not value:
        return None
    s = str(value).strip().replace(" ", "T")
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def effective_client_ts(client_ts, server_now):
    """The timestamp we are willing to believe for a device's edit.
    Missing/garbled -> arrival time. Future-dated beyond the allowed skew ->
    arrival time (so a wrong clock can't win every future conflict)."""
    dt = parse_ts(client_ts)
    if dt is None:
        return server_now
    if dt > server_now + datetime.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        return server_now
    return dt


def values_equal(a, b):
    """Compare field values the way a person would: None and '' are the
    same 'empty', 0 equals empty, and 5, 5.0 and '5' are the same number."""
    def empty(v):
        if v is None:
            return True
        if isinstance(v, str):
            return v.strip() == ""
        return False

    def as_number(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    a_empty, b_empty = empty(a), empty(b)
    if a_empty and b_empty:
        return True
    # A blank score cell and a 0 are the same thing to a teacher (the score
    # screens save blanks as 0), so 0 counts as "empty" when compared to blank.
    if a_empty or b_empty:
        other = b if a_empty else a
        return as_number(other) == 0
    na, nb = as_number(a), as_number(b)
    if na is not None and nb is not None:
        return na == nb
    return str(a).strip() == str(b).strip()


class Decision:
    """kind is one of:
        'apply'          no concurrent change; apply the client's fields
        'merge'          concurrent, but no overlap; apply `fields`
        'latest_client'  concurrent; the device's edit is later and wins
        'latest_server'  concurrent; the server's row is later and stays
        'conflict'       needs a person; nothing is overwritten
    """

    def __init__(self, kind, fields=None, conflicting=None, note=None):
        self.kind = kind
        self.fields = fields or {}
        self.conflicting = conflicting or []
        self.note = note

    def __repr__(self):
        return f"Decision({self.kind!r}, fields={self.fields}, conflicting={self.conflicting}, note={self.note!r})"


def decide(policy, field_names, client, server, base, client_ts, server_updated_at, server_now):
    """`client`: the field values the device wants to write.
    `server`: the row currently on the server.
    `base`: the values the device last synced (dict) or None if unknown.
    Only called when the row DID change since the device last saw it."""
    if policy == POLICY_MERGE:
        if base is None:
            return Decision("conflict", note="Changed elsewhere and this device has no record of the values it started from.")
        client_changed = {f: client[f] for f in field_names
                          if f in client and not values_equal(client[f], base.get(f))}
        server_changed = {f for f in field_names if not values_equal(server.get(f), base.get(f))}
        clashing = sorted(f for f in client_changed
                          if f in server_changed and not values_equal(client_changed[f], server.get(f)))
        if clashing:
            return Decision("conflict", conflicting=clashing,
                            note="Both this device and another changed: " + ", ".join(clashing))
        # Fields where both sides landed on the same value need no write.
        to_apply = {f: v for f, v in client_changed.items() if not values_equal(v, server.get(f))}
        return Decision("merge", fields=to_apply,
                        note="Combined with a change made elsewhere (different fields).")

    if policy == POLICY_LATEST_WINS:
        c_ts = effective_client_ts(client_ts, server_now)
        s_ts = parse_ts(server_updated_at) or datetime.datetime.min
        if c_ts >= s_ts:
            return Decision("latest_client", fields={f: client[f] for f in field_names if f in client},
                            note="This device's edit was more recent than the server's.")
        return Decision("latest_server", note="The server already held a more recent edit.")

    return Decision("conflict", note="Changed elsewhere since this device last synced it.")
