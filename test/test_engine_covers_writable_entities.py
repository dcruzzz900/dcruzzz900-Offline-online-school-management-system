"""Every entity a device is allowed to WRITE must be in the sync engine's push
order (SYNC_TIERS). Twice an entity was made writable on the server but left out
of that list, so edits were queued on the device and silently never sent."""
import re
from helpers import fresh_app, ROOT


def test_every_writable_entity_is_pushed_by_the_engine():
    fresh_app()
    import sync_api
    js = open(f"{ROOT}/static/js/sync-engine.js", encoding="utf-8").read()
    block = re.search(r"const SYNC_TIERS = \[(.*?)\];", js, re.S).group(1)
    in_engine = set(re.findall(r'"([a-z_]+)"', block))
    writable = {name for name, cfg in sync_api.ENTITIES.items() if cfg["can_write"]}
    missing = writable - in_engine
    assert not missing, f"writable on the server but never pushed by the client: {sorted(missing)}"
