from helpers import fresh_app, login, enroll, device_headers


def test_baseline_enroll_bootstrap_push_pull():
    app_mod, _ = fresh_app()
    c = app_mod.app.test_client()
    assert login(c, "admin", "admin123").status_code == 302
    cred = enroll(c)
    h = device_headers(cred)
    dev = app_mod.app.test_client()
    r = dev.get("/api/sync/bootstrap", headers=h)
    assert r.status_code == 200
    ents = r.get_json()["entities"]
    assert len(ents["students"]) == 3 and len(ents["classes"]) == 1
