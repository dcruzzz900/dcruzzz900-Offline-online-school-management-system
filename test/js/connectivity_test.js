// Unit tests for static/js/connectivity.js with a fake network and fake clock.
const path = require("path");
const listeners = {};
global.window = { addEventListener: (n, f) => { (listeners[n] = listeners[n] || []).push(f); } };
const docListeners = {};
global.document = { visibilityState: "visible", addEventListener: (n, f) => { (docListeners[n] = docListeners[n] || []).push(f); }, dispatchEvent() {} };
global.CustomEvent = class { constructor(n, o) { this.detail = o && o.detail; } };
const C = require(path.join(__dirname, "..", "..", "static", "js", "connectivity.js"));

let failures = 0;
const check = (label, cond, extra) => { if (!cond) { failures++; console.log("FAIL:", label, extra === undefined ? "" : JSON.stringify(extra)); } else console.log("ok:  ", label); };
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };

function makeSched() {
    let t = 0, id = 0; const q = [];
    return {
        now: () => t,
        setTimeout: (fn, ms) => { const h = ++id; q.push({ h, at: t + ms, fn }); return h; },
        clearTimeout: (h) => { const i = q.findIndex((x) => x.h === h); if (i >= 0) q.splice(i, 1); },
        async advance(ms) {
            const end = t + ms;
            for (;;) { q.sort((a, b) => a.at - b.at); const n = q[0]; if (!n || n.at > end) break; q.shift(); t = n.at; n.fn(); await flush(); }
            t = end; await flush();
        },
    };
}

async function scenario(name, fn) {
    const sched = makeSched();
    const net = { mode: "ok", calls: [] };
    let browserOnline = true;
    C._reset(true);
    C._configure({
        setTimeout: sched.setTimeout, clearTimeout: sched.clearTimeout, now: sched.now, browserOnline: () => browserOnline,
        fetch: (url, opts) => {
            net.calls.push(sched.now());
            if (net.mode === "refuse") return Promise.reject(new TypeError("Failed to fetch"));
            if (net.mode === "hang") return new Promise(() => {});
            if (net.mode === "portal") return Promise.resolve({ ok: true, json: async () => { throw new SyntaxError("<html>"); } });
            if (net.mode === "wrongjson") return Promise.resolve({ ok: true, json: async () => ({ status: "nope" }) });
            if (net.mode === "500") return Promise.resolve({ ok: false, json: async () => ({}) });
            return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
        },
    });
    const events = [];
    C.onChange((on) => events.push(on));
    console.log("--", name);
    await fn({ sched, net, events, setBrowser: (v) => { browserOnline = v; } });
}

(async () => {
    await scenario("healthy server stays online and is re-checked periodically", async ({ sched, net, events }) => {
        C.start(); await flush();
        check("verified online after first answer", C.isOnline() && C.isVerified());
        const before = net.calls.length;
        await sched.advance(46000);
        check("re-checked about every 15s", net.calls.length - before === 3, net.calls);
        check("no change events while healthy", events.length === 0);
    });

    await scenario("one failed check is not an outage; two are", async ({ sched, net, events }) => {
        C.start(); await flush();
        net.mode = "refuse";
        await sched.advance(15000);
        check("still online after ONE failure", C.isOnline() === true && events.length === 0);
        await sched.advance(1500);
        check("offline after the second consecutive failure", C.isOnline() === false && events.join() === "false", events);
    });

    await scenario("recovery is noticed by a single good answer, with backoff while down", async ({ sched, net, events }) => {
        C.start(); await flush();
        net.mode = "refuse";
        await sched.advance(15000 + 1500);
        const down = net.calls.length;
        await sched.advance(2000 + 4000 + 8000 + 15000 + 30000 + 30000);
        check("probes back off 2s, 4s, 8s, 15s, 30s, 30s while offline", net.calls.length - down === 6, net.calls.slice(down));
        net.mode = "ok";
        await sched.advance(30000);
        check("back online after one good answer, event fired once", C.isOnline() === true && events.join() === "false,true", events);
    });

    await scenario("a captive-portal page, wrong JSON, a 500 or a hang all count as NOT reachable", async ({ sched, net, events }) => {
        for (const mode of ["portal", "wrongjson", "500", "hang"]) {
            C._reset(true); events.length = 0; net.mode = mode;
            C._configure({});
            C.onChange((on) => events.push(on));
            C.start(); await flush();
            await sched.advance(mode === "hang" ? 12000 : 3000);
            check(`mode '${mode}' => offline`, C.isOnline() === false, { mode, events });
        }
    });

    await scenario("the browser reporting NO network is believed immediately; 'online' is only a hint", async ({ sched, net, events, setBrowser }) => {
        C.start(); await flush();
        setBrowser(false); (listeners.offline || []).forEach((f) => f());
        check("offline instantly on the browser's offline event", C.isOnline() === false && events.join() === "false");
        net.mode = "refuse";
        setBrowser(true); (listeners.online || []).forEach((f) => f()); await flush();
        check("browser says online but the server can't be reached => stays offline (lie-fi)", C.isOnline() === false && events.join() === "false", events);
        net.mode = "ok";
        (listeners.online || []).forEach((f) => f()); await flush();
        check("and comes back the moment the server answers", C.isOnline() === true && events.join() === "false,true", events);
    });

    await scenario("a network error reported by the sync engine triggers an immediate re-check", async ({ sched, net, events }) => {
        C.start(); await flush();
        net.mode = "refuse";
        const before = net.calls.length;
        C.reportFailure(); await flush();
        check("probe happened right away", net.calls.length === before + 1);
        C.reportFailure(); await sched.advance(0); await flush();
        await sched.advance(1600); 
        check("two failures in quick succession => offline within seconds, not 15s", C.isOnline() === false, { events });
    });

    console.log(failures ? `\n${failures} FAILED` : "\nconnectivity OK");
    process.exit(failures ? 1 : 0);
})();
