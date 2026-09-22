/*
 * Connectivity monitor.
 *
 * The browser's own "online" flag only says a network interface is up; it says nothing
 * about whether the SERVER can be reached (wifi with no internet, a captive portal, a
 * mobile signal that carries nothing, the server being down). So the app doesn't trust
 * it. This monitor VERIFIES reachability by asking the server a tiny question
 * (GET /healthz, answered with {"status":"ok"}) and only believes a real answer:
 * a timeout, a refused connection, or a login/captive-portal page in its place all count
 * as "not reachable".
 *
 *   - Going OFFLINE needs two failed checks in a row (one dropped packet is not an outage),
 *     or the browser reporting that it has no network at all (that direction is reliable).
 *   - Going back ONLINE needs a single good answer, and is checked quickly and repeatedly
 *     (2s, 4s, 8s … up to 30s) while offline, so recovery is noticed within seconds.
 *   - While online it re-checks every 15 seconds, and immediately whenever the sync engine
 *     hits a network error, the tab becomes visible again, or the browser reports a change.
 *
 * Nothing here changes what the person sees except a "connectivity-change" event, which
 * the status indicator and the sync engine listen to. Modes are never switched by hand.
 */
const Connectivity = (function () {
    const cfg = {
        url: "/healthz",
        probeTimeoutMs: 4000,
        onlineIntervalMs: 15000,
        offlineBackoffMs: [2000, 4000, 8000, 15000, 30000],
        quickRecheckMs: 1500,
        failuresToGoOffline: 2,
    };
    const env = {
        fetch: (typeof fetch !== "undefined") ? (...a) => fetch(...a) : null,
        setTimeout: (...a) => setTimeout(...a),
        clearTimeout: (...a) => clearTimeout(...a),
        now: () => Date.now(),
        browserOnline: () => (typeof navigator === "undefined" || navigator.onLine !== false),
    };

    let online = env.browserOnline();     // provisional until the first real answer
    let verified = false;
    let failures = 0;
    let offlineAttempts = 0;
    let timer = null;
    let inFlight = null;
    let started = false;
    let lastChange = null;
    const listeners = [];

    function emit() {
        lastChange = env.now();
        const detail = { online, verified };
        for (const fn of listeners.slice()) { try { fn(online, detail); } catch (e) { /* a listener's bug must not stop the monitor */ } }
        if (typeof document !== "undefined" && typeof CustomEvent !== "undefined") {
            document.dispatchEvent(new CustomEvent("connectivity-change", { detail }));
        }
    }

    function setOnline(next) {
        if (online === next) return;
        online = next;
        emit();
    }

    function schedule(ms) {
        if (timer) env.clearTimeout(timer);
        timer = env.setTimeout(() => { timer = null; probe(); }, ms);
    }

    function nextDelayAfterFailure() {
        if (online) return cfg.quickRecheckMs;               // suspicious: confirm soon
        const i = Math.min(offlineAttempts, cfg.offlineBackoffMs.length - 1);
        offlineAttempts += 1;
        return cfg.offlineBackoffMs[i];
    }

    function apply(ok) {
        verified = true;
        if (ok) {
            failures = 0;
            offlineAttempts = 0;
            setOnline(true);
            schedule(cfg.onlineIntervalMs);
        } else {
            failures += 1;
            if (failures >= cfg.failuresToGoOffline || !env.browserOnline()) setOnline(false);
            schedule(nextDelayAfterFailure());
        }
    }

    // Asks the server. Resolves true only for a genuine {"status":"ok"} answer.
    async function check() {
        if (!env.fetch) return env.browserOnline();
        const controller = (typeof AbortController !== "undefined") ? new AbortController() : null;
        let timedOut = false;
        const guard = env.setTimeout(() => { timedOut = true; if (controller) controller.abort(); }, cfg.probeTimeoutMs);
        try {
            const res = await Promise.race([
                env.fetch(`${cfg.url}?t=${env.now()}`, { cache: "no-store", credentials: "omit", signal: controller ? controller.signal : undefined }),
                new Promise((_, reject) => env.setTimeout(() => reject(new Error("timeout")), cfg.probeTimeoutMs + 500)),
            ]);
            if (timedOut || !res || !res.ok) return false;
            const body = await res.json();
            return !!body && body.status === "ok";
        } catch (e) {
            return false;                                    // refused, dropped, timed out, or not our JSON
        } finally {
            env.clearTimeout(guard);
        }
    }

    // Check now (one at a time). Returns the resulting online state.
    function probeNow() {
        if (!inFlight) {
            inFlight = check().then((ok) => { apply(ok); return online; }).finally(() => { inFlight = null; });
        }
        return inFlight;
    }
    const probe = probeNow;

    function start() {
        if (started) return;
        started = true;
        if (typeof window !== "undefined") {
            // "offline" from the browser means no network interface at all — believe it
            // straight away. "online" only means an interface came up — verify it.
            window.addEventListener("offline", () => { failures = cfg.failuresToGoOffline; setOnline(false); schedule(cfg.offlineBackoffMs[0]); });
            window.addEventListener("online", () => { probeNow(); });
        }
        if (typeof document !== "undefined") {
            document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") probeNow(); });
        }
        probeNow();
    }

    // Called by the sync engine: a request just failed at the network level, or just
    // got a real answer from the server. Cheap, and makes detection near-instant.
    function reportFailure() { if (started) { failures += 0; probeNow(); } }
    function reportSuccess() { if (started && !online) apply(true); else if (started) { failures = 0; } }

    function onChange(fn) { listeners.push(fn); return () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); }; }

    // Test hooks.
    function _configure(overrides) {
        if (overrides.cfg) Object.assign(cfg, overrides.cfg);
        for (const k of ["fetch", "setTimeout", "clearTimeout", "now", "browserOnline"]) if (overrides[k]) env[k] = overrides[k];
    }
    function _reset(startOnline) {
        if (timer) env.clearTimeout(timer);
        timer = null; inFlight = null; started = false; verified = false; failures = 0; offlineAttempts = 0;
        online = startOnline !== undefined ? startOnline : true;
        listeners.length = 0;
    }

    const api = {
        isOnline: () => online,
        isVerified: () => verified,
        lastChange: () => lastChange,
        start, probeNow, onChange, reportFailure, reportSuccess, _configure, _reset,
    };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    return api;
})();
