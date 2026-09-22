/*
 * The offline app shell (templates/offline_app.html) is a normal
 * server-rendered page like every other page in this app — the point is
 * that its HTML/CSS/JS is small and static enough to be fully precached by
 * the service worker (see SHELL_ASSETS in service-worker.js), so it opens
 * with zero network at all, including for a device's very first login of
 * the day. Everything it shows comes from IndexedDB, not from the server,
 * once it's open.
 *
 * This intentionally covers three representative offline workflows
 * (attendance, score entry, student registration) plus sync status/
 * conflict resolution, rather than reimplementing every admin screen as a
 * client-rendered view — see OFFLINE_ARCHITECTURE.md for the extension
 * pattern used to bring more screens in over time.
 */
(function () {
    const root = document.getElementById("offlineRoot");
    // Names, comments and usernames are typed by staff (or imported from a
    // file) and end up on other people's screens, so every piece of stored
    // text goes through esc() before it is put into HTML.
    const esc = (typeof OfflineResults !== "undefined" && OfflineResults.esc) || ((v) =>
        String(v === null || v === undefined ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"));
    let session = null;   // { device_id, device_secret, user, started_at }
    let schoolId = null;

    function el(html) {
        const t = document.createElement("template");
        t.innerHTML = html.trim();
        return t.content.firstElementChild;
    }

    function todayStr() {
        return new Date().toISOString().slice(0, 10);
    }

    // ---------------- boot ----------------

    // ---------------- one app: routing, navigation, connection indicator ----------------
    // The same screens, navigation and forms are used whether the connection is up or
    // down: every screen reads and writes THIS DEVICE's copy of the school's data, and
    // the sync engine exchanges changes with the server automatically in the background.

    // Online means the server was VERIFIED reachable (connectivity.js checks it in the
    // background) — not merely that the phone has wifi.
    const isOnline = () => Connectivity.isOnline();

    // The message a save should show. Saying "will sync when back online" while actually
    // online is misleading (spec item 1): a save made while online has already been queued
    // for a sync that is either already running or about to run in the background, so it
    // reads "Saved — syncing to the server now" instead. Only when the device is verified
    // offline does it say the record is waiting for a connection.
    function saveStatusMessage(n) {
        const noun = n === undefined ? "" : ` ${n} ${n === 1 ? "record" : "records"}`;
        return isOnline()
            ? `Saved${noun} — syncing to the server now.`
            : `Saved${noun} offline — will sync automatically when you're back online.`;
    }

    let profile = null;        // school profile (name, logo) cached on the device
    let logoUrl = null;
    let lastDetail = null;

    async function boot() {
        document.addEventListener("offline-sync-status", (e) => {
            lastDetail = e.detail;
            refreshPill(e.detail);
            // The school's name/logo arrive with the first download; show them as soon as they do.
            if (session && schoolId && !profile) loadProfile().then((got) => { if (got) renderNavbar(); });
        });
        document.addEventListener("offline-sync-progress", (e) => {
            const n = document.getElementById("setupRows");
            if (n) n.textContent = e.detail.rows;
        });
        // Nothing switches "modes": the same screens keep working; only the indicator changes
        // (and the sync engine starts/stops sending in the background).
        Connectivity.onChange(() => refreshPill(lastDetail));
        Connectivity.start();
        window.addEventListener("hashchange", () => { if (session) dispatch(); });
        startClock();
        session = OfflineAuth.getSession();
        if (session) {
            schoolId = session.user.school_id;
            await afterUnlock();
        } else {
            clearNavbar();
            await renderAccountPicker();
        }
    }

    // After the person is unlocked: make sure this device has the school's data
    // (first-time setup downloads it, with progress), start automatic syncing, and
    // show the screen the address asks for.
    async function afterUnlock() {
        session = OfflineAuth.getSession();
        schoolId = session.user.school_id;
        await loadProfile();
        SyncEngine.startAutoSync(schoolId);
        const ready = await OfflineDB.getMeta(schoolId, "last_sync_at");
        if (!ready) return renderFirstSetup();
        SyncEngine.ensureReady(schoolId, session.device_id, session.device_secret).catch(() => {});
        return dispatch();
    }

    async function loadProfile() {
        profile = await OfflineDB.getMeta(schoolId, "school_profile");
        logoUrl = await OfflineDB.getMeta(schoolId, "school_logo");
        return profile;
    }

    function startClock() {
        const tick = () => {
            const box = document.getElementById("liveClock");
            if (!box) return;
            const d = new Date(), p = (n) => String(n).padStart(2, "0");
            box.textContent = `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} — ${p(d.getHours())}:${p(d.getMinutes())}`;
        };
        tick();
        setInterval(tick, 15000);
    }

    const ROUTES = {
        "": () => renderHome(),
        attendance: () => renderAttendance(),
        scores: () => renderScoreEntry(),
        comments: () => renderComments(),
        register: () => renderStudentRegistration(),
        results: () => renderResults(),
        "import-export": () => renderImportExport(),
        materials: () => renderMaterials(),
        settings: () => renderSettings(),
        setup: () => renderSetupHub(),
        reports: () => renderReportsHub(),
        classes: () => renderClassManagement(),
        subjects: () => renderSubjectManagement(),
        assign: () => renderAssignSubjects(),
        students: () => renderStudentsAdmin(),
        teachers: () => renderTeacherManagement(),
        actions: () => renderActionsQueue(),
        sync: () => renderSyncStatus(),
        "staff-attendance": () => renderStaffAttendance(),
        "roll-call-history": () => renderRollCallHistory(),
        notifications: () => renderNotifications(),
    };

    function go(route) {
        const target = "#/" + (route || "");
        if (location.hash === target || (!route && !location.hash)) dispatch();
        else location.hash = target;
    }

    function currentRoute() { return (location.hash || "").replace(/^#\/?/, ""); }

    async function dispatch() {
        if (!session) return;
        const fn = ROUTES[currentRoute()] || ROUTES[""];
        await fn();
        window.scrollTo(0, 0);
    }

    function isAdminRole() { return ["admin", "sub_admin"].includes(session.user.role); }

    // The same menu the server-rendered pages show. Items marked `online` are pages
    // that only the server can do (they change things for the whole school in ways that
    // can't be safely merged later); offline they say so instead of failing.
    function navItems() {
        const teacher = session.user.role === "teacher";
        const items = [{ label: "Dashboard", route: "" }, { label: "Classes", route: "results" }];
        if (teacher) items.push({ label: "My Class", route: "attendance" });
        items.push({ label: "Materials", route: "materials" });
        if (isAdminRole()) {
            items.push({ label: "Setup", route: "setup" });
            items.push({ label: "Terms", href: "/admin/terms", online: true });
            items.push({ label: "Staff Attendance", route: "staff-attendance" });
            items.push({ label: "Promote Students", href: "/admin/promote", online: true });
            items.push({ label: "Reports", route: "reports" });
        }
        items.push({ label: "Notifications", route: "notifications" });
        items.push({ label: "Settings", route: "settings" });
        return items;
    }

    function clearNavbar() {
        const nav = document.getElementById("appNav");
        if (nav) nav.innerHTML = "";
    }

    function toast(message) {
        const t = el(`<div style="position:fixed; left:50%; bottom:1.5rem; transform:translateX(-50%); background:#333; color:#fff; padding:0.6rem 1rem; border-radius:8px; z-index:99; max-width:90%; font-size:0.9rem;">${esc(message)}</div>`);
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 3500);
    }

    function renderNavbar() {
        const nav = document.getElementById("appNav");
        if (!nav || !session) return;
        const name = (profile && profile.name) || "School Results";
        nav.innerHTML = "";
        const bar = el(`<nav class="navbar">
            <div class="navbar-brand navbar-brand-${esc((profile && profile.logo_align) || "center")}">
                ${logoUrl ? `<img src="${esc(logoUrl)}" alt="" class="navbar-logo">` : ""}<span>${esc(name)}</span>
            </div>
            <span id="syncPill" role="button" tabindex="0" title="Connection and sync status"></span>
            <button class="navbar-toggle" id="navbarToggle" aria-label="Toggle menu" type="button">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
            </button>
            <div class="navbar-links" id="navbarLinks"></div>
        </nav>`);
        const links = bar.querySelector("#navbarLinks");
        for (const item of navItems()) {
            const a = el(`<a href="${item.route !== undefined ? "#/" + esc(item.route) : esc(item.href)}">${esc(item.label)}${item.online ? "" : ""}</a>`);
            a.addEventListener("click", (ev) => {
                links.classList.remove("nav-open");
                if (item.route !== undefined) return;            // hash change is handled by the router
                ev.preventDefault();
                if (!isOnline()) toast(`${item.label} needs an internet connection.`);
                else location.href = item.href;
            });
            links.appendChild(a);
        }
        links.appendChild(el(`<span class="navbar-user">${esc(session.user.name)} (${esc(session.user.role.replace("_", " "))})</span>`));
        const out = el(`<a href="/logout">Logout</a>`);
        out.addEventListener("click", (ev) => {
            ev.preventDefault();
            OfflineAuth.lock();
            SyncEngine.stopAutoSync();
            session = null;
            clearNavbar();
            try { navigator.serviceWorker.ready.then((reg) => reg.active && reg.active.postMessage({ type: "purge-pages" })); } catch (e) { /* no service worker */ }
            if (isOnline()) setTimeout(() => { location.href = "/logout"; }, 200);
            else renderAccountPicker();
        });
        links.appendChild(out);
        bar.querySelector("#navbarToggle").addEventListener("click", () => links.classList.toggle("nav-open"));
        const pill = bar.querySelector("#syncPill");
        pill.addEventListener("click", () => go("sync"));
        pill.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go("sync"); });
        nav.appendChild(bar);
        refreshPill(lastDetail);
    }

    // The only connection indicator: three states, small, always visible.
    //   🟢 Online — Synced   |   🟠 Offline — Saved Locally   |   🔄 Syncing
    async function refreshPill(detail) {
        const pill = document.getElementById("syncPill");
        if (!pill) return;
        if (!detail && schoolId) detail = { ...(await OfflineDB.getPendingCounts(schoolId)), online: isOnline() };
        detail = detail || { online: isOnline(), pending: 0, conflict: 0, failed: 0 };
        const online = isOnline();
        const attention = (detail.conflict || 0) + (detail.failed || 0);
        let text, bg, fg;
        if (!online) { text = "🟠 Offline — Saved Locally"; bg = "#fff1dc"; fg = "#8a5300"; }
        else if (detail.syncing || detail.pending) { text = "🔄 Syncing"; bg = "#e6effa"; fg = "#1f3a5f"; }
        else if (attention) { text = `🟠 ${attention} to review`; bg = "#fff1dc"; fg = "#8a5300"; }
        else { text = "🟢 Online — Synced"; bg = "#e3f5e8"; fg = "#1d6b3a"; }
        pill.textContent = text;
        pill.dataset.state = !online ? "offline" : (detail.syncing || detail.pending) ? "syncing" : attention ? "attention" : "synced";
        pill.style.cssText = `background:${bg}; color:${fg}; font-size:0.75rem; font-weight:600; padding:0.15rem 0.6rem; border-radius:999px; white-space:nowrap; cursor:pointer; margin-left:auto; margin-right:0.5rem;`;
    }

    // First time on this device (or after its data was cleared): download the
    // school's data securely so everything works offline from here on.
    async function renderFirstSetup() {
        renderNavbar();
        root.innerHTML = "";
        if (!isOnline()) {
            root.appendChild(el(`<div class="card"><h2>This device isn't ready yet</h2>
                <p>The first time you use this device it needs to download your school's data, which needs an internet connection. Connect once, and it will finish setting up automatically.</p></div>`));
            const off = Connectivity.onChange((on) => { if (on) { off(); afterUnlock(); } });
            return;
        }
        root.appendChild(el(`<div class="card"><h2>Setting up this device…</h2>
            <p>Downloading your school's data so you can keep working even without internet. This only happens once on each device.</p>
            <p><b id="setupRows">0</b> records downloaded</p></div>`));
        try {
            const r = await SyncEngine.ensureReady(schoolId, session.device_id, session.device_secret);
            if (r && r.authError) throw new Error("auth");
            return dispatch();
        } catch (e) {
            root.appendChild(el(`<div class="card"><p style="color:#b3261e;">${e.message === "auth" ? "Your sign-in on this device needs renewing. Log in online again." : "The download was interrupted."}</p>
                <button class="btn" id="setupRetry">Try again</button></div>`));
            root.querySelector("#setupRetry").addEventListener("click", () => renderFirstSetup());
        }
    }

    // ---------------- dashboards (same layout as the server-rendered ones) ----------------

    async function termLabel() {
        const term = await activeTerm();
        if (!term) return null;
        const se = (await OfflineDB.getAll(schoolId, "sessions")).find((s) => s.id === term.session_id);
        return `${se ? se.name : ""} — ${term.name}`;
    }

    async function renderHome() {
        return isAdminRole() ? renderAdminDashboard() : renderTeacherDashboard();
    }

    async function renderAdminDashboard() {
        const label = await termLabel();
        const [students, classes, users, subjects] = await Promise.all(
            ["students", "classes", "users", "subjects"].map((e) => OfflineDB.getAll(schoolId, e)));
        const body = el(`<div>
            ${label ? `<p class="badge">Active: ${esc(label)}</p>` : `<p class="flash flash-error">No active term set. Set one up under Terms (needs internet).</p>`}
            <div class="stat-grid">
                <div class="stat-box"><div class="num">${students.filter((s) => s.is_active).length}</div><div class="label">Students</div></div>
                <div class="stat-box"><div class="num">${classes.length}</div><div class="label">Classes</div></div>
                <div class="stat-box"><div class="num">${users.filter((u) => u.role === "teacher").length}</div><div class="label">Teachers</div></div>
                <div class="stat-box"><div class="num">${subjects.length}</div><div class="label">Subjects</div></div>
            </div>
            <div class="grid-2">
                <div class="card" id="dashSetup"><h3>School Setup</h3><p>Manage classes, subjects, students and teachers.</p></div>
                <div class="card" id="dashResults"><h3>Results</h3><p>View broadsheets and terminal results by class.</p></div>
                <div class="card" id="dashWork"><h3>Daily Work</h3><p>Attendance, scores and comments.</p></div>
            </div>
        </div>`);
        const add = (parent, text, route, gold) => {
            const b = el(`<a class="btn${gold ? " btn-gold" : ""}" href="#/${route}">${esc(text)}</a>`);
            body.querySelector(parent).appendChild(b);
        };
        for (const [t, r] of [["Classes", "classes"], ["Subjects", "subjects"], ["Assign Subjects", "assign"], ["Students", "students"], ["Teachers", "teachers"]]) add("#dashSetup", t, r);
        add("#dashResults", "Go to Classes", "results", true);
        for (const [t, r] of [["Attendance / Roll Call", "attendance"], ["Score Entry", "scores"], ["Teacher / Principal Comments", "comments"], ["Student Registration", "register"], ["Roll-Call History", "roll-call-history"]]) add("#dashWork", t, r);
        frame("Admin Dashboard", body);
    }

    async function renderTeacherDashboard() {
        const label = await termLabel();
        const [links, classes, subjects] = await Promise.all(["class_subjects", "classes", "subjects"].map((e) => OfflineDB.getAll(schoolId, e)));
        const mine = links.filter((l) => l.teacher_id === session.user.user_id);
        const isFormTeacher = classes.some((c) => c.form_teacher_id === session.user.user_id);
        const rows = mine.map((l) => {
            const c = classes.find((x) => x.id === l.class_id), s = subjects.find((x) => x.id === l.subject_id);
            return `<tr><td>${esc(c ? c.name : "")}</td><td>${esc(s ? s.name : "")}</td><td><a class="btn btn-small" href="#/scores">Enter Scores</a></td></tr>`;
        }).join("");
        const body = el(`<div>
            ${isFormTeacher ? `<a href="#/attendance" class="btn btn-small">Manage My Class Register</a>` : ""}
            ${label ? `<p class="badge">Active: ${esc(label)}</p>` : `<p class="flash flash-error">No active term set yet. Contact the admin.</p>`}
            <div class="card"><h3>Your Subject Assignments</h3>
                ${rows ? `<table><tr><th>Class</th><th>Subject</th><th>Action</th></tr>${rows}</table>` : `<p>No subjects assigned to you yet.</p>`}
            </div>
            <div class="card"><h3>Daily Work</h3>
                <a class="btn" href="#/attendance">Attendance / Roll Call</a>
                <a class="btn" href="#/scores">Score Entry</a>
                <a class="btn" href="#/comments">Teacher / Principal Comments</a>
                <a class="btn" href="#/results">Results &amp; Broadsheets</a>
                <a class="btn" href="#/roll-call-history">Roll-Call History</a>
            </div>
        </div>`);
        frame(`Welcome, ${session.user.name}`, body);
    }

    async function renderSetupHub() {
        const body = el(`<div class="card"><h3>School Setup</h3><p>Manage classes, subjects, students and teachers.</p></div>`);
        for (const [t, r] of [["Classes", "classes"], ["Subjects", "subjects"], ["Assign Subjects", "assign"], ["Students", "students"], ["Teachers", "teachers"], ["Student Registration", "register"], ["Import / Export (CSV & Excel)", "import-export"], ["Queue Internet-Only Actions", "actions"]]) {
            body.appendChild(el(`<a class="btn" href="#/${r}">${esc(t)}</a>`));
        }
        frame("School Setup", body);
    }

    async function renderReportsHub() {
        const body = el(`<div class="card"><h3>Reports</h3><p>Terminal results and broadsheets are worked out on this device, so they are always available.</p>
            <a class="btn" href="#/results">Results &amp; Broadsheets (view / print)</a>
            <a class="btn" href="#/roll-call-history">Roll-Call History</a>
            <a class="btn" href="#/import-export">Import / Export (CSV &amp; Excel)</a>
            <a class="btn" href="#/sync">Sync Status &amp; Conflicts</a></div>`);
        frame("Reports", body);
    }

    // ---------------- staff attendance (admins) ----------------

    const STAFF_STATUSES = ["Present", "Absent", "Late", "Leave"];
    // Mirrors POSITION_LABELS in db.py.
    const POSITIONS = { "": "None", principal: "Principal", vice_principal: "Vice Principal", exam_officer: "Exam Officer", subject_teacher: "Subject Teacher", form_teacher: "Form Teacher" };

    function isoDate(d) {
        const p = (n) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }
    function shiftDay(iso, delta) {
        const [y, m, d] = iso.split("-").map(Number);
        return isoDate(new Date(y, m - 1, d + delta));
    }

    async function renderStaffAttendance(dateStr) {
        const today = isoDate(new Date());
        dateStr = dateStr || today;
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const staff = (await OfflineDB.getAll(schoolId, "users")).filter((u) => u.id)
            .sort((a, b) => (a.role < b.role ? -1 : a.role > b.role ? 1 : a.name.localeCompare(b.name)));
        const records = await OfflineDB.getAll(schoolId, "staff_attendance");
        const forDay = new Map(records.filter((r) => r.date === dateStr).map((r) => [r.user_id, r]));
        const nav = el(`<div class="card"><div style="display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center;">
            <button class="btn btn-small" id="saPrev">&larr; Previous Day</button>
            <input type="date" id="saDate" value="${esc(dateStr)}" max="${today}" style="width:auto;">
            <button class="btn btn-small" id="saNext" ${dateStr >= today ? "disabled" : ""}>Next Day &rarr;</button>
            ${dateStr !== today ? `<button class="btn btn-small" id="saToday">Jump to Today</button>` : ""}
        </div><p style="font-size:0.85rem; color:#666;">Mark each staff member's status for the day. Everyone defaults to Present.</p></div>`);
        body.appendChild(nav);
        const table = el(`<div class="card"><table><thead><tr><th>Name</th><th>Role</th>${STAFF_STATUSES.map((s) => `<th>${s}</th>`).join("")}</tr></thead><tbody></tbody></table>
            <button class="btn" id="saSave" style="margin-top:1rem;">Save Attendance</button><p id="saMsg"></p></div>`);
        table.querySelector("thead tr").insertAdjacentHTML("beforeend", "<th>Recorded</th>");
        for (const m of staff) {
            const rec = forDay.get(m.id);
            const current = rec ? rec.status : "Present";
            const recordedNote = rec
                ? `${esc(new Date(rec.recorded_at || rec.updated_at).toLocaleString())} <span style="color:#888;">(${esc(rec.source || "online")})</span>`
                : `<span style="color:#999;">not yet recorded</span>`;
            table.querySelector("tbody").appendChild(el(`<tr data-user="${m.id}"><td>${esc(m.name)}</td><td>${esc((POSITIONS[m.position] || m.role.replace("_", " ")))}</td>${
                STAFF_STATUSES.map((s) => `<td><input type="radio" name="sa_${m.id}" value="${s}" ${current === s ? "checked" : ""} style="width:auto;"></td>`).join("")}<td style="font-size:0.8rem;">${recordedNote}</td></tr>`));
        }
        body.appendChild(table);
        // History & reports: counts per person over a date range, from this device's records
        const start = dateStr.slice(0, 8) + "01";
        const hist = el(`<div class="card"><h3>History &amp; Reports</h3>
            <div style="display:flex; gap:0.5rem; flex-wrap:wrap; align-items:end;">
                <div><label>From</label><input type="date" id="shStart" value="${start}"></div>
                <div><label>To</label><input type="date" id="shEnd" value="${dateStr}"></div>
            </div><table style="margin-top:1rem;"><thead><tr><th>Name</th>${STAFF_STATUSES.map((s) => `<th>${s}</th>`).join("")}<th>Total</th></tr></thead><tbody id="shBody"></tbody></table></div>`);
        body.appendChild(hist);
        frame("Staff Attendance", body);

        const drawHistory = async () => {
            const a = hist.querySelector("#shStart").value, b = hist.querySelector("#shEnd").value;
            const recs = (await OfflineDB.getAll(schoolId, "staff_attendance")).filter((r) => r.date >= a && r.date <= b);
            const tb = hist.querySelector("#shBody");
            tb.innerHTML = "";
            for (const m of staff) {
                const counts = Object.fromEntries(STAFF_STATUSES.map((s) => [s, recs.filter((r) => r.user_id === m.id && r.status === s).length]));
                tb.appendChild(el(`<tr><td>${esc(m.name)}</td>${STAFF_STATUSES.map((s) => `<td>${counts[s]}</td>`).join("")}<td>${Object.values(counts).reduce((x, y) => x + y, 0)}</td></tr>`));
            }
        };
        hist.querySelector("#shStart").addEventListener("change", drawHistory);
        hist.querySelector("#shEnd").addEventListener("change", drawHistory);
        await drawHistory();

        nav.querySelector("#saPrev").addEventListener("click", () => renderStaffAttendance(shiftDay(dateStr, -1)));
        const nextBtn = nav.querySelector("#saNext");
        if (nextBtn) nextBtn.addEventListener("click", () => renderStaffAttendance(shiftDay(dateStr, 1)));
        const todayBtn = nav.querySelector("#saToday");
        if (todayBtn) todayBtn.addEventListener("click", () => renderStaffAttendance(today));
        nav.querySelector("#saDate").addEventListener("change", (e) => { if (e.target.value) renderStaffAttendance(e.target.value); });
        table.querySelector("#saSave").addEventListener("click", async () => {
            let saved = 0;
            for (const tr of table.querySelectorAll("tbody tr")) {
                const userId = parseInt(tr.dataset.user, 10);
                const status = tr.querySelector("input:checked").value;
                const existing = forDay.get(userId);
                if (existing && existing.status === status) continue;
                const data = { user_id: userId, date: dateStr, status, recorded_by: session.user.user_id, source: isOnline() ? "online" : "offline" };
                if (existing) await SyncEngine.queueChange(schoolId, "staff_attendance", "update", data, existing.client_uuid);
                else await SyncEngine.queueChange(schoolId, "staff_attendance", "create", data);
                saved++;
            }
            const msg = table.querySelector("#saMsg");
            msg.style.color = "#2e7d4f";
            msg.textContent = saved ? `Saved ${saved} change(s). They sync automatically.` : "No changes to save.";
            if (saved) setTimeout(() => renderStaffAttendance(dateStr), 600);
        });
    }

    // ---------------- notifications (read on the device; sending is online) ----------------

    async function renderNotifications() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const data = await OfflineDB.getMeta(schoolId, "notifications");
        const items = (data && data.items) || [];
        const seen = (data && data.last_seen_id) || 0;
        if (isAdminRole()) {
            const compose = el(`<a class="btn btn-small" href="/notifications/compose">Send a notification (needs internet)</a>`);
            compose.addEventListener("click", (ev) => { if (!isOnline()) { ev.preventDefault(); toast("Sending a notification needs an internet connection."); } });
            body.appendChild(compose);
        }
        if (!items.length) {
            body.appendChild(el(`<div class="card"><p>No notifications.${data ? "" : " They will appear here after this device has synced once."}</p></div>`));
        }
        for (const n of items) {
            const isNew = n.id > seen;
            body.appendChild(el(`<div class="card" ${isNew ? 'style="border-left:4px solid #c8952a;"' : ""}>
                <h3>${esc(n.title)} ${isNew ? '<span class="badge">New</span>' : ""}</h3>
                <p style="white-space:pre-wrap;">${esc(n.message)}</p>
                <p style="font-size:0.8rem; color:#777;">${esc(n.sender_label)} · ${esc(OfflineResults.dmy(String(n.created_at || "").slice(0, 10)))}${n.platform_wide ? " · from the platform" : ""}</p></div>`));
        }
        frame("Notifications", body);
        // Opening the inbox marks everything as read (on the server, when we can reach it).
        if (isOnline() && items.length && items[0].id > seen) {
            fetch("/api/sync/notifications/seen", { method: "POST", headers: { "X-Device-Id": session.device_id, "X-Device-Secret": session.device_secret } })
                .then(() => { data.last_seen_id = items[0].id; OfflineDB.setMeta(schoolId, "notifications", data); }).catch(() => {});
        }
    }

    // ---------------- roll-call history ----------------

    async function renderRollCallHistory() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const term = await activeTerm();
        const classes = (await OfflineDB.getAll(schoolId, "classes")).filter((c) => c.id);
        const students = await OfflineDB.getAll(schoolId, "students");
        const usable = classes.filter((c) => students.some((s) => s.class_id === c.id));
        if (!term || !usable.length) {
            body.appendChild(el(`<div class="card"><p>No class register is available on this device yet, or there is no active term.</p></div>`));
            frame("Roll-Call History", body);
            return;
        }
        const card = el(`<div class="card"><label>Class</label><select id="rhClass">${usable.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select></div>`);
        const out = el(`<div></div>`);
        body.appendChild(card);
        body.appendChild(out);
        frame("Roll-Call History", body);
        const draw = async () => {
            const classId = parseInt(card.querySelector("#rhClass").value, 10);
            const records = (await OfflineDB.getAll(schoolId, "attendance_records")).filter((r) => r.class_id === classId && r.term_id === term.id);
            const pupils = students.filter((s) => s.class_id === classId && s.is_active).sort((a, b) => (a.admission_no < b.admission_no ? -1 : 1));
            const rows = pupils.map((s) => {
                const mine = records.filter((r) => r.student_id === s.id);
                const opened = mine.length, present = mine.filter((r) => r.status === "present").length;
                return `<tr><td>${esc(OfflineResults.fullName(s))}</td><td>${opened}</td><td>${present}</td><td>${opened - present}</td><td>${opened ? Math.round(present / opened * 1000) / 10 : 0}%</td></tr>`;
            }).join("");
            const byDate = {};
            for (const r of records) {
                byDate[r.date] = byDate[r.date] || { present: 0, absent: 0 };
                if (r.status === "present") byDate[r.date].present++; else if (r.status === "absent") byDate[r.date].absent++;
            }
            const dateRows = Object.keys(byDate).sort().reverse().map((d) => `<tr><td>${esc(OfflineResults.dmy(d))}</td><td>${byDate[d].present}</td><td>${byDate[d].absent}</td></tr>`).join("");
            out.innerHTML = "";
            out.appendChild(el(`<div class="card"><h3>Per student — this term</h3><table><thead><tr><th>Student</th><th>Days open</th><th>Present</th><th>Absent</th><th>Attendance</th></tr></thead><tbody>${rows}</tbody></table></div>`));
            out.appendChild(el(`<div class="card"><h3>Per day</h3>${dateRows ? `<table><thead><tr><th>Date</th><th>Present</th><th>Absent</th></tr></thead><tbody>${dateRows}</tbody></table>` : "<p>No roll calls recorded yet this term.</p>"}</div>`));
        };
        card.querySelector("#rhClass").addEventListener("change", draw);
        await draw();
    }

    // ---------------- students (list, search, edit) ----------------

    async function renderStudentsAdmin() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const classes = (await OfflineDB.getAll(schoolId, "classes")).filter((c) => c.id).sort((a, b) => a.name.localeCompare(b.name));
        const card = el(`<div class="card">
            <label>Class</label><select id="stClass">${classes.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            <label>Search</label><input type="search" id="stSearch" placeholder="Name or admission number">
            <table style="margin-top:1rem;"><thead><tr><th>Adm. No.</th><th>Name</th><th>Gender</th><th>Status</th><th></th></tr></thead><tbody id="stBody"></tbody></table>
        </div>`);
        body.appendChild(card);
        const holder = el(`<div></div>`);
        body.appendChild(holder);
        frame("Students", body);
        const list = async () => {
            const classId = parseInt(card.querySelector("#stClass").value, 10);
            const q = card.querySelector("#stSearch").value.trim().toLowerCase();
            const rows = (await OfflineDB.getAll(schoolId, "students")).filter((s) => s.class_id === classId)
                .filter((s) => !q || `${s.first_name} ${s.last_name} ${s.admission_no}`.toLowerCase().includes(q))
                .sort((a, b) => (a.last_name < b.last_name ? -1 : 1));
            const tb = card.querySelector("#stBody");
            tb.innerHTML = "";
            for (const s of rows) {
                const tr = el(`<tr><td>${esc(s.admission_no)}</td><td>${esc(s.last_name)} ${esc(s.first_name)}</td><td>${esc(s.gender || "")}</td><td>${s.is_active ? "Active" : "Inactive"}${s._sync && s._sync.status !== "synced" ? " · pending sync" : ""}</td><td></td></tr>`);
                const b = el(`<button class="btn btn-small">Edit</button>`);
                b.addEventListener("click", () => editStudent(s, classes, holder, list));
                tr.lastElementChild.appendChild(b);
                tb.appendChild(tr);
            }
            if (!rows.length) tb.appendChild(el(`<tr><td colspan="5">No students found.</td></tr>`));
        };
        card.querySelector("#stClass").addEventListener("change", list);
        card.querySelector("#stSearch").addEventListener("input", list);
        await list();
    }

    function editStudent(s, classes, holder, refresh) {
        holder.innerHTML = "";
        const f = (id, label, value, type) => `<label>${label}</label><input type="${type || "text"}" id="${id}" value="${esc(value ?? "")}">`;
        const card = el(`<div class="card"><h3>Edit ${esc(s.first_name)} ${esc(s.last_name)}</h3>
            ${f("esAdm", "Admission No.", s.admission_no)}${f("esFirst", "First Name", s.first_name)}${f("esLast", "Last Name", s.last_name)}${f("esOther", "Other Names", s.other_names)}
            <label>Gender</label><select id="esGender"><option value="">—</option><option value="M" ${s.gender === "M" ? "selected" : ""}>Male</option><option value="F" ${s.gender === "F" ? "selected" : ""}>Female</option></select>
            <label>Class</label><select id="esClass">${classes.map((c) => `<option value="${c.id}" ${c.id === s.class_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
            ${f("esDob", "Date of birth", s.date_of_birth, "date")}${f("esParent", "Parent / guardian", s.parent_name)}${f("esPhone", "Parent phone", s.parent_phone)}${f("esEmail", "Parent email", s.parent_email)}
            <label><input type="checkbox" id="esActive" ${s.is_active ? "checked" : ""} style="width:auto;"> Active student</label>
            <button class="btn" id="esSave" style="margin-top:1rem;">Save changes</button>
            <button class="btn" id="esCancel" style="margin-top:1rem; background:#888;">Cancel</button><p id="esMsg"></p></div>`);
        holder.appendChild(card);
        card.querySelector("#esCancel").addEventListener("click", () => { holder.innerHTML = ""; });
        card.querySelector("#esSave").addEventListener("click", async () => {
            const v = (id) => card.querySelector("#" + id).value.trim();
            const msg = card.querySelector("#esMsg");
            if (!v("esAdm") || !v("esFirst") || !v("esLast")) { msg.style.color = "#b3261e"; msg.textContent = "Admission number and both names are required."; return; }
            const data = {
                admission_no: v("esAdm"), first_name: v("esFirst"), last_name: v("esLast"), other_names: v("esOther") || null,
                gender: v("esGender") || null, class_id: parseInt(v("esClass"), 10), date_of_birth: v("esDob") || null,
                parent_name: v("esParent") || null, parent_phone: v("esPhone") || null, parent_email: v("esEmail") || null,
                is_active: card.querySelector("#esActive").checked ? 1 : 0,
            };
            await SyncEngine.queueChange(schoolId, "students", "update", data, s.client_uuid);
            holder.innerHTML = "";
            toast("Saved. It syncs automatically.");
            await refresh();
        });
    }

    // ---------------- assign subjects to teachers ----------------

    async function renderAssignSubjects() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const classes = (await OfflineDB.getAll(schoolId, "classes")).filter((c) => c.id).sort((a, b) => a.name.localeCompare(b.name));
        const subjects = (await OfflineDB.getAll(schoolId, "subjects")).filter((s) => s.id).sort((a, b) => a.name.localeCompare(b.name));
        const teachers = (await OfflineDB.getAll(schoolId, "users")).filter((u) => ["teacher", "sub_admin"].includes(u.role) && u.id);
        const card = el(`<div class="card"><label>Class</label>
            <select id="asClass"><option value="">Choose a class…</option>${classes.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            <table style="margin-top:1rem;"><thead><tr><th>Subject</th><th>Teacher</th></tr></thead><tbody id="asBody"></tbody></table>
            <p style="font-size:0.85rem; color:#777;">Choose a teacher to assign or change. Removing a subject from a class is done online, because it also removes that subject's scores for the class.</p></div>`);
        body.appendChild(card);
        frame("Assign Subjects", body);
        const draw = async () => {
            const classId = parseInt(card.querySelector("#asClass").value, 10);
            const tb = card.querySelector("#asBody");
            tb.innerHTML = "";
            if (!classId) return;
            const links = (await OfflineDB.getAll(schoolId, "class_subjects")).filter((l) => l.class_id === classId);
            for (const sb of subjects) {
                const link = links.find((l) => l.subject_id === sb.id);
                const sel = el(`<select><option value="">— not assigned —</option>${teachers.map((t) => `<option value="${t.id}" ${link && link.teacher_id === t.id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select>`);
                if (!link) sel.dataset.unassigned = "1";
                sel.addEventListener("change", async () => {
                    const tid = sel.value ? parseInt(sel.value, 10) : null;
                    if (link) await SyncEngine.queueChange(schoolId, "class_subjects", "update", { class_id: classId, subject_id: sb.id, teacher_id: tid }, link.client_uuid);
                    else if (tid) await SyncEngine.queueChange(schoolId, "class_subjects", "create", { class_id: classId, subject_id: sb.id, teacher_id: tid });
                    toast("Saved. It syncs automatically.");
                    await draw();
                });
                const tr = el(`<tr><td>${esc(sb.name)}</td><td></td></tr>`);
                tr.lastElementChild.appendChild(sel);
                tb.appendChild(tr);
            }
        };
        card.querySelector("#asClass").addEventListener("change", draw);
    }

    // ---------------- unlock (password) ----------------

    function onlineSiteLink() {
        // "?online=1" tells the service worker not to bounce this straight back here.
        return `<a href="/login?online=1">Log in online instead</a>`;
    }

    async function renderAccountPicker() {
        const accounts = await OfflineAuth.listAccounts();
        root.innerHTML = "";
        if (!accounts.length) {
            const card = el(`<div class="card login-wrapper"><h2>Offline Login</h2>
                <p>Offline access isn't set up on this device yet.</p>
                <p>Log in once while you have internet — your normal username and password — and this device will be ready to work offline.</p>
                <a class="btn" href="/login?online=1" style="display:block; text-align:center;">Log in online</a></div>`);
            root.appendChild(card);
            return;
        }
        // One person on this device (the normal case): go straight to the password box.
        if (accounts.length === 1) return renderPasswordPrompt(accounts[0], false);
        const card = el(`<div class="card login-wrapper"><h2>Offline Login</h2><p>Choose your account:</p></div>`);
        for (const account of accounts) {
            const btn = el(`<button class="btn" style="display:block; width:100%; margin-bottom:0.5rem;">${esc(account.label)}</button>`);
            btn.addEventListener("click", () => renderPasswordPrompt(account, true));
            card.appendChild(btn);
        }
        card.appendChild(el(`<p style="font-size:0.85rem; margin-top:1rem;">${onlineSiteLink()}</p>`));
        root.appendChild(card);
    }

    function renderPasswordPrompt(account, canGoBack) {
        root.innerHTML = "";
        const card = el(`
            <div class="card login-wrapper">
                <h2>🔒 ${esc(account.label)}</h2>
                <p style="color:#666;">You're working offline. Enter your password to continue where you left off.</p>
                <form id="unlockForm">
                    <label for="pwInput">Password</label>
                    <input type="password" id="pwInput" autocomplete="current-password" autofocus required>
                    <p id="pwError" style="color:#b3261e;"></p>
                    <button class="btn" id="unlockBtn" type="submit" style="width:100%;">Unlock</button>
                </form>
                ${canGoBack ? `<button class="btn" id="backBtn" style="background:#888; margin-top:0.5rem; width:100%;">Not you? Choose another account</button>` : ""}
                <p style="font-size:0.8rem; color:#999; margin-top:0.75rem;">${onlineSiteLink()}</p>
            </div>
        `);
        root.appendChild(card);
        if (canGoBack) card.querySelector("#backBtn").addEventListener("click", renderAccountPicker);
        const input = card.querySelector("#pwInput");
        input.focus();
        card.querySelector("#unlockForm").addEventListener("submit", async (ev) => {
            ev.preventDefault();
            const err = card.querySelector("#pwError");
            const btn = card.querySelector("#unlockBtn");
            err.textContent = "";
            btn.disabled = true;
            btn.textContent = "Unlocking…";
            try {
                const user = await OfflineAuth.unlock(account.device_id, input.value);
                session = OfflineAuth.getSession();
                schoolId = user.school_id;
                await afterUnlock();
            } catch (e) {
                btn.disabled = false;
                btn.textContent = "Unlock";
                input.value = "";
                if (e.code === "expired") {
                    err.innerHTML = `${esc(e.message)} <br><br><a class="btn" href="/login?online=1" style="display:block; text-align:center;">Log in online to renew</a>`;
                } else {
                    err.textContent = e.message;
                    input.focus();
                }
            }
        });
    }

    // Notices shown at the top of every screen: things a person needs to know
    // about the state of THIS device (never blocking, never destructive).
    const AUTH_MESSAGES = {
        expired: "This device hasn't connected for a while, so its offline access has expired. Log in online to renew it. Everything you entered is still saved here and will sync then.",
        revoked: "Your access on this device was turned off (your account was deactivated or this device was removed). Your unsynced entries are still saved here — use \"Download backup\" on the Sync screen and speak to your school admin.",
        school_suspended: "Your school's account is suspended. Your unsynced entries are safe on this device and will sync once it's reactivated.",
        school_archived: "Your school's account has been archived. Your unsynced entries are still saved on this device.",
        bad_secret: "This device's saved credentials are out of date. Log in online to refresh them — your entries are safe.",
        not_found: "This device isn't recognised any more. Log in online to set it up again — your entries are safe.",
        not_authenticated: "The server didn't accept this device's sign-in. Log in online to refresh it — your entries are safe.",
    };

    async function fillBanners(container) {
        if (!schoolId) return;
        const notes = [];
        const problem = await OfflineDB.getMeta(schoolId, "auth_problem");
        if (problem) {
            notes.push({ color: "#b3261e", html: `${esc(AUTH_MESSAGES[problem.status] || AUTH_MESSAGES.not_authenticated)}
                ${problem.status === "revoked" || problem.status === "school_suspended" || problem.status === "school_archived" ? "" : ` <a href="/login?online=1"><b>Log in online</b></a>`}` });
        }
        const accounts = await OfflineAuth.listAccounts();
        const mine = accounts.find((a) => a.device_id === session.device_id);
        if (mine && mine.expires_at) {
            const days = Math.ceil((new Date(mine.expires_at).getTime() - Date.now()) / 86400000);
            if (days <= 7 && days >= 0 && !problem) {
                notes.push({ color: "#a97f22", html: `Offline access on this device runs out in ${days} day${days === 1 ? "" : "s"}. Connect to the internet and log in to renew it.` });
            }
        }
        // Forms queued by the EARLIER version of the app (before the update) are kept in the
        // browser's storage, and are sent from the "Offline Queue" page while logged in.
        let legacy = 0;
        for (const k of [`offline_queue_v1:${schoolId}`, "offline_queue_v1"]) {
            try { legacy += (JSON.parse(localStorage.getItem(k) || "[]") || []).length; } catch (e) { /* ignore */ }
        }
        if (legacy) {
            notes.push({ color: "#a97f22", html: `${legacy} item${legacy === 1 ? "" : "s"} saved by the previous version of the app ${legacy === 1 ? "is" : "are"} still waiting to be sent. <a href="/offline"><b>Send them now</b></a> (needs internet and a login).` });
        }
        const counts = await OfflineDB.getPendingCounts(schoolId);
        const waiting = counts.pending + counts.failed + counts.conflict;
        if (waiting) {
            const info = await OfflineAuth.storageInfo();
            if (!info.persisted) {
                notes.push({ color: "#a97f22", html: `${waiting} change${waiting === 1 ? " isn't" : "s aren't"} synced yet, and this browser may clear saved data if the phone runs low on storage. Sync when you can, or <a href="#" id="bannerBackup"><b>download a backup</b></a>.` });
            }
        }
        container.innerHTML = notes.map((n) => `<div class="card" style="border-left:4px solid ${n.color}; font-size:0.9rem;">${n.html}</div>`).join("");
        const b = container.querySelector("#bannerBackup");
        if (b) b.addEventListener("click", (ev) => { ev.preventDefault(); exportBackup(); });
    }

    // Everything not yet synced, as a file the person can keep. A safety net for
    // the rare cases where the browser's own storage can't be trusted (phone
    // storage cleaned, browser data cleared, a device that has to be replaced).
    async function exportBackup() {
        const records = [];
        for (const entity of OfflineDB.ENTITY_STORES) {
            for (const st of ["pending", "failed", "conflict"]) {
                for (const r of await OfflineDB.getByStatus(schoolId, entity, st)) records.push({ entity, record: r });
            }
        }
        const actions = [];
        for (const st of ["pending", "failed"]) actions.push(...(await OfflineDB.getByStatus(schoolId, "actions", st).catch(() => [])));
        const file = { app: "school-results-offline-backup", version: 1, school_id: schoolId, exported_at: new Date().toISOString(),
            exported_by: session.user.name, records, actions };
        downloadBlob(`unsynced-backup-${new Date().toISOString().slice(0, 10)}.json`, new Blob([JSON.stringify(file)], { type: "application/json" }));
    }

    async function importBackup(file) {
        const data = JSON.parse(await file.text());
        if (data.app !== "school-results-offline-backup" || data.version !== 1) throw new Error("That isn't a backup file from this app.");
        if (data.school_id !== schoolId) throw new Error("That backup belongs to a different school.");
        let restored = 0, skipped = 0;
        for (const { entity, record } of data.records || []) {
            if (!OfflineDB.ENTITY_STORES.includes(entity) || !record || !record.client_uuid) { skipped++; continue; }
            const local = await OfflineDB.getRecord(schoolId, entity, record.client_uuid);
            if (local && local._sync && local._sync.status !== "synced") { skipped++; continue; }   // never overwrite newer unsynced work
            record._sync = { ...(record._sync || {}), status: "pending", attempts: 0 };
            delete record._sync.last_error;
            await OfflineDB.putRecord(schoolId, entity, record);
            restored++;
        }
        SyncEngine.broadcastStatus(schoolId);
        return { restored, skipped };
    }

    // ---------------- home ----------------

    function frame(title, bodyEl) {
        renderNavbar();
        root.innerHTML = "";
        const wrap = el(`<div></div>`);
        const banners = el(`<div></div>`);
        wrap.appendChild(banners);
        fillBanners(banners).catch(() => {});
        wrap.appendChild(el(`<h1>${esc(title)}</h1>`));
        wrap.appendChild(bodyEl);
        root.appendChild(wrap);
        refreshPill(lastDetail);
    }

    // ---------------- helpers shared by views ----------------

    async function accessibleClasses() {
        const classes = await OfflineDB.getAll(schoolId, "classes");
        if (["admin", "sub_admin"].includes(session.user.role)) return classes;
        return classes.filter((c) => c.form_teacher_id === session.user.user_id);
    }

    async function teachingClasses() {
        // classes a teacher has at least one subject assignment in
        if (["admin", "sub_admin"].includes(session.user.role)) return OfflineDB.getAll(schoolId, "classes");
        const links = (await OfflineDB.getAll(schoolId, "class_subjects")).filter((cs) => cs.teacher_id === session.user.user_id);
        const classIds = new Set(links.map((l) => l.class_id));
        const classes = await OfflineDB.getAll(schoolId, "classes");
        return classes.filter((c) => classIds.has(c.id));
    }

    async function activeTerm() {
        const sessions = await OfflineDB.getAll(schoolId, "sessions");
        const activeSession = sessions.find((s) => s.is_active);
        if (!activeSession) return null;
        const terms = await OfflineDB.getAll(schoolId, "terms");
        return terms.find((t) => t.is_active && t.session_id === activeSession.id) || null;
    }

    function backButton() {
        const btn = el(`<button class="btn" style="background:#888; margin-bottom:1rem;">&larr; Dashboard</button>`);
        btn.addEventListener("click", () => go(""));
        return btn;
    }

    // ---------------- dependency-safe references ----------------
    // A record created offline (e.g. a brand-new class) doesn't have a
    // real numeric id yet — only a client_uuid — until it syncs. These
    // helpers let a <select> offer such "still syncing" parent records
    // alongside already-synced ones, and turn whichever one was picked
    // into either a real foreign key or a `_pending_refs` entry that
    // SyncEngine resolves automatically once the parent syncs (see
    // "Dependency-safe offline creation" in OFFLINE_ARCHITECTURE.md).

    function refKey(record) {
        return record.id ? String(record.id) : `pending:${record.client_uuid}`;
    }

    function refOptions(records, labelFn) {
        return records.map((r) => `<option value="${esc(refKey(r))}">${esc(labelFn(r))}${r.id ? "" : " (not yet synced)"}</option>`).join("");
    }

    // Reads a <select> populated by refOptions() and applies the choice
    // either as a resolved numeric field on `data`, or as an entry in
    // `pendingRefs` for SyncEngine to resolve later. `data` and
    // `pendingRefs` are mutated in place.
    function applyRefSelection(selectValue, fieldName, parentEntity, data, pendingRefs) {
        if (!selectValue) return;
        if (selectValue.startsWith("pending:")) {
            pendingRefs[fieldName] = `${parentEntity}:${selectValue.slice("pending:".length)}`;
        } else {
            data[fieldName] = parseInt(selectValue, 10);
        }
    }

    // ---------------- attendance ----------------

    async function renderAttendance() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const term = await activeTerm();
        if (!term) {
            body.appendChild(el(`<p>No active term found in this device's offline data. Connect to the internet once to sync the current term.</p>`));
            frame("Attendance / Roll Call", body);
            return;
        }
        // Attendance is tied 1:1 to a class+date; a class that hasn't
        // synced yet has no real id to attach the record to, so (unlike
        // Student Registration) it's excluded here rather than made
        // dependency-safe -- a class is normally set up in advance, not
        // in the same breath as taking attendance for it.
        const classes = (await accessibleClasses()).filter((c) => c.id);
        if (!classes.length) {
            body.appendChild(el(`<p>No synced classes available yet on this device — connect once online first, or add one under "Manage Classes" and wait for it to sync.</p>`));
            frame("Attendance / Roll Call", body);
            return;
        }
        const controls = el(`
            <div class="card">
                <label>Class</label>
                <select id="classSelect"><option value="">Choose a class…</option>${classes.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
                <label>Date</label>
                <input type="date" id="dateSelect" value="${todayStr()}">
            </div>
        `);
        body.appendChild(controls);
        const listWrap = el(`<div id="attendanceList"></div>`);
        body.appendChild(listWrap);
        frame("Attendance / Roll Call", body);

        async function renderList() {
            const classId = parseInt(document.getElementById("classSelect").value, 10);
            const date = document.getElementById("dateSelect").value;
            listWrap.innerHTML = "";
            if (!classId || !date) return;
            const students = (await OfflineDB.getAll(schoolId, "students")).filter((s) => s.class_id === classId && s.is_active);
            const records = await OfflineDB.getAll(schoolId, "attendance_records");
            const card = el(`<div class="card"><table><thead><tr><th>Student</th><th>Present</th><th>Absent</th></tr></thead><tbody></tbody></table>
                <button class="btn" id="saveAttendanceBtn" style="margin-top:1rem;">Save Attendance</button></div>`);
            const tbody = card.querySelector("tbody");
            for (const s of students) {
                const existing = records.find((r) => r.student_id === s.id && r.term_id === term.id && r.date === date);
                const current = existing ? existing.status : "present";
                const row = el(`
                    <tr data-student="${s.id}" data-client-uuid="${existing ? esc(existing.client_uuid) : ''}">
                        <td>${esc(s.first_name)} ${esc(s.last_name)}</td>
                        <td><input type="radio" name="att_${s.id}" value="present" ${current === "present" ? "checked" : ""}></td>
                        <td><input type="radio" name="att_${s.id}" value="absent" ${current === "absent" ? "checked" : ""}></td>
                    </tr>
                `);
                tbody.appendChild(row);
            }
            listWrap.appendChild(card);
            card.querySelector("#saveAttendanceBtn").addEventListener("click", async () => {
                for (const row of tbody.querySelectorAll("tr")) {
                    const studentId = parseInt(row.dataset.student, 10);
                    const status = row.querySelector("input[type=radio]:checked").value;
                    const clientUuid = row.dataset.clientUuid;
                    const data = { student_id: studentId, class_id: classId, term_id: term.id, date, status, recorded_by: session.user.user_id, source: isOnline() ? "online" : "offline" };
                    if (clientUuid) {
                        await SyncEngine.queueChange(schoolId, "attendance_records", "update", data, clientUuid);
                    } else {
                        await SyncEngine.queueChange(schoolId, "attendance_records", "create", data);
                    }
                }
                alert(saveStatusMessage(tbody.querySelectorAll("tr").length));
                renderList();
            });
        }
        document.getElementById("classSelect").addEventListener("change", renderList);
        document.getElementById("dateSelect").addEventListener("change", renderList);
    }

    // ---------------- score entry ----------------

    async function renderScoreEntry() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const term = await activeTerm();
        if (!term) {
            body.appendChild(el(`<p>No active term found in this device's offline data. Connect to the internet once to sync the current term.</p>`));
            frame("Score Entry", body);
            return;
        }
        // Same reasoning as Attendance above -- scores need a real class id.
        const classes = (await teachingClasses()).filter((c) => c.id);
        if (!classes.length) {
            body.appendChild(el(`<p>No synced classes available yet on this device — connect once online first.</p>`));
            frame("Score Entry", body);
            return;
        }
        const controls = el(`
            <div class="card">
                <label>Class</label>
                <select id="seClassSelect"><option value="">Choose a class…</option>${classes.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
                <label>Subject</label>
                <select id="seSubjectSelect"><option value="">Choose a class first…</option></select>
            </div>
        `);
        body.appendChild(controls);
        const listWrap = el(`<div id="scoreList"></div>`);
        body.appendChild(listWrap);
        frame("Score Entry", body);

        document.getElementById("seClassSelect").addEventListener("change", async () => {
            const classId = parseInt(document.getElementById("seClassSelect").value, 10);
            const subjectSelect = document.getElementById("seSubjectSelect");
            subjectSelect.innerHTML = "";
            listWrap.innerHTML = "";
            if (!classId) return;
            const links = (await OfflineDB.getAll(schoolId, "class_subjects")).filter((cs) => cs.class_id === classId &&
                (["admin", "sub_admin"].includes(session.user.role) || cs.teacher_id === session.user.user_id));
            const subjects = await OfflineDB.getAll(schoolId, "subjects");
            subjectSelect.innerHTML = `<option value="">Choose a subject…</option>` +
                links.map((l) => { const subj = subjects.find((s) => s.id === l.subject_id); return subj ? `<option value="${subj.id}">${esc(subj.name)}</option>` : ""; }).join("");
        });

        document.getElementById("seSubjectSelect").addEventListener("change", async () => {
            const classId = parseInt(document.getElementById("seClassSelect").value, 10);
            const subjectId = parseInt(document.getElementById("seSubjectSelect").value, 10);
            listWrap.innerHTML = "";
            if (!classId || !subjectId) return;
            // The school's own maximums (and whether it uses CA3) come from the
            // grading settings synced to this device.
            const config = (await OfflineDB.getAll(schoolId, "grading_config"))[0] || { ca1_max: 20, ca2_max: 20, ca3_max: 0, exam_max: 60 };
            const useCa3 = OfflineResults.ca3Enabled(config);
            const fields = ["ca1", "ca2"].concat(useCa3 ? ["ca3"] : [], ["exam"]);
            const students = (await OfflineDB.getAll(schoolId, "students")).filter((s) => s.class_id === classId && s.is_active);
            const scores = await OfflineDB.getAll(schoolId, "scores");
            const heads = fields.map((f) => `<th>${f === "exam" ? "Exam" : f.toUpperCase()} (/${esc(config[f + "_max"])})</th>`).join("");
            const card = el(`<div class="card"><table><thead><tr><th>Student</th>${heads}<th>Total</th></tr></thead><tbody></tbody></table>
                <button class="btn" id="saveScoresBtn" style="margin-top:1rem;">Save Scores</button>
                <p id="scoreMsg" style="margin-top:0.5rem;"></p></div>`);
            const tbody = card.querySelector("tbody");
            const recomputeRow = (row) => {
                let total = 0;
                for (const f of fields) total += parseFloat(row.querySelector("." + f).value) || 0;
                row.querySelector(".rowTotal").textContent = OfflineResults.round2(total);
            };
            for (const s of students) {
                const existing = scores.find((r) => r.student_id === s.id && r.subject_id === subjectId && r.term_id === term.id);
                const inputs = fields.map((f) => `<td><input type="number" step="0.5" min="0" max="${esc(config[f + "_max"])}" style="width:5rem;" class="${f}" value="${existing ? esc(existing[f] ?? "") : ""}"></td>`).join("");
                const row = el(`
                    <tr data-student="${s.id}" data-client-uuid="${existing ? esc(existing.client_uuid) : ''}">
                        <td>${esc(s.first_name)} ${esc(s.last_name)}</td>${inputs}<td class="rowTotal">0</td>
                    </tr>
                `);
                row.querySelectorAll("input").forEach((i) => i.addEventListener("input", () => recomputeRow(row)));
                recomputeRow(row);
                tbody.appendChild(row);
            }
            listWrap.appendChild(card);
            card.querySelector("#saveScoresBtn").addEventListener("click", async () => {
                const msg = card.querySelector("#scoreMsg");
                const problems = [], work = [];
                for (const row of tbody.querySelectorAll("tr")) {
                    const studentId = parseInt(row.dataset.student, 10);
                    const clientUuid = row.dataset.clientUuid;
                    const raw = {};
                    for (const f of fields) raw[f] = row.querySelector("." + f).value.trim();
                    const existing = clientUuid ? scores.find((r) => r.client_uuid === clientUuid) : null;
                    if (!existing && fields.every((f) => raw[f] === "")) continue;      // untouched blank row
                    const data = { student_id: studentId, subject_id: subjectId, term_id: term.id, ca1: 0, ca2: 0, ca3: 0, exam: 0 };
                    const name = row.children[0].textContent;
                    let ok = true;
                    for (const f of fields) {
                        const v = raw[f] === "" ? 0 : Number(raw[f]);
                        const max = Number(config[f + "_max"]);
                        if (!Number.isFinite(v) || v < 0 || v > max) { problems.push(`${name}: ${f.toUpperCase()} must be between 0 and ${max}`); ok = false; break; }
                        data[f] = v;
                    }
                    if (!ok) continue;
                    if (existing && fields.every((f) => OfflineResults.num(existing[f]) === data[f])) continue;   // unchanged
                    work.push({ data, clientUuid });
                }
                if (problems.length) {
                    msg.style.color = "#b3261e";
                    msg.textContent = "Nothing was saved. " + problems.slice(0, 5).join("; ") + (problems.length > 5 ? ` (+${problems.length - 5} more)` : "");
                    return;
                }
                for (const w of work) {
                    if (w.clientUuid) await SyncEngine.queueChange(schoolId, "scores", "update", w.data, w.clientUuid);
                    else await SyncEngine.queueChange(schoolId, "scores", "create", w.data);
                }
                msg.style.color = "#2e7d4f";
                msg.textContent = work.length
                    ? `Saved ${work.length} score row(s) on this device. They will sync automatically once you're back online.`
                    : "No changes to save.";
            });
        });
    }

    // ---------------- teacher / principal comments ----------------

    async function renderComments() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const term = await activeTerm();
        if (!term) {
            body.appendChild(el(`<p>No active term found in this device's offline data. Connect to the internet once to sync the current term.</p>`));
            frame("Teacher / Principal Comments", body);
            return;
        }
        // Same reasoning as Attendance above -- comments need a real class id.
        const isAdmin = ["admin", "sub_admin"].includes(session.user.role);
        const classes = (await accessibleClasses()).filter((c) => c.id);
        if (!classes.length) {
            body.appendChild(el(`<p>No synced classes available yet on this device — connect once online first.</p>`));
            frame("Teacher / Principal Comments", body);
            return;
        }
        const controls = el(`
            <div class="card">
                <label>Class</label>
                <select id="cClassSelect"><option value="">Choose a class…</option>${classes.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            </div>
        `);
        body.appendChild(controls);
        const listWrap = el(`<div id="commentList"></div>`);
        body.appendChild(listWrap);
        frame("Teacher / Principal Comments", body);

        document.getElementById("cClassSelect").addEventListener("change", async () => {
            const classId = parseInt(document.getElementById("cClassSelect").value, 10);
            listWrap.innerHTML = "";
            if (!classId) return;
            const students = (await OfflineDB.getAll(schoolId, "students")).filter((s) => s.class_id === classId && s.is_active);
            const infos = await OfflineDB.getAll(schoolId, "student_term_info");
            for (const s of students) {
                const existing = infos.find((r) => r.student_id === s.id && r.term_id === term.id);
                const card = el(`
                    <div class="card" data-student="${s.id}" data-client-uuid="${existing ? esc(existing.client_uuid) : ''}">
                        <h4>${esc(s.first_name)} ${esc(s.last_name)}</h4>
                        <label>Teacher's Comment</label>
                        <textarea class="teacherComment" rows="2" ${isAdmin ? "" : ""}>${existing && existing.teacher_comment ? esc(existing.teacher_comment) : ""}</textarea>
                        ${isAdmin ? `
                        <label>Principal's Comment</label>
                        <textarea class="principalComment" rows="2">${existing && existing.principal_comment ? esc(existing.principal_comment) : ""}</textarea>` : ""}
                        <button class="btn btn-small saveCommentBtn" style="margin-top:0.5rem;">Save</button>
                        <span class="saveMsg" style="margin-left:0.5rem; color:#2e7d4f;"></span>
                    </div>
                `);
                listWrap.appendChild(card);
                card.querySelector(".saveCommentBtn").addEventListener("click", async () => {
                    const clientUuid = card.dataset.clientUuid;
                    const data = { student_id: s.id, term_id: term.id, teacher_comment: card.querySelector(".teacherComment").value };
                    if (isAdmin) data.principal_comment = card.querySelector(".principalComment").value;
                    if (clientUuid) {
                        await SyncEngine.queueChange(schoolId, "student_term_info", "update", data, clientUuid);
                    } else {
                        const record = await SyncEngine.queueChange(schoolId, "student_term_info", "create", data);
                        card.dataset.clientUuid = record.client_uuid;
                    }
                    card.querySelector(".saveMsg").textContent = "Saved — will sync when online.";
                });
            }
        });
    }

    // ---------------- student registration ----------------

    async function renderStudentRegistration() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const classes = await accessibleClasses();
        if (!classes.length) {
            body.appendChild(el(`<p>No classes available yet on this device. ${["admin","sub_admin"].includes(session.user.role) ? "Add one under \"Manage Classes\" first — you can do that offline too." : "Ask an admin to set one up."}</p>`));
            frame("Student Registration", body);
            return;
        }
        const card = el(`
            <div class="card">
                <label>Admission No.</label><input type="text" id="regAdmissionNo">
                <label>First Name</label><input type="text" id="regFirstName">
                <label>Last Name</label><input type="text" id="regLastName">
                <label>Gender</label>
                <select id="regGender"><option value="M">Male</option><option value="F">Female</option></select>
                <label>Class</label>
                <select id="regClass">${refOptions(classes, (c) => c.name)}</select>
                <button class="btn" id="regSaveBtn" style="margin-top:1rem;">Register Student</button>
                <p id="regMsg" style="color:#2e7d4f;"></p>
            </div>
        `);
        body.appendChild(card);
        frame("Student Registration", body);

        document.getElementById("regSaveBtn").addEventListener("click", async () => {
            const data = {
                admission_no: document.getElementById("regAdmissionNo").value.trim(),
                first_name: document.getElementById("regFirstName").value.trim(),
                last_name: document.getElementById("regLastName").value.trim(),
                gender: document.getElementById("regGender").value,
                is_active: 1,
            };
            const pendingRefs = {};
            applyRefSelection(document.getElementById("regClass").value, "class_id", "classes", data, pendingRefs);
            if (!data.admission_no || !data.first_name || !data.last_name || (!data.class_id && !pendingRefs.class_id)) {
                document.getElementById("regMsg").style.color = "#b3261e";
                document.getElementById("regMsg").textContent = "Please fill in all fields.";
                return;
            }
            await SyncEngine.queueChange(schoolId, "students", "create", data, undefined, pendingRefs);
            document.getElementById("regMsg").style.color = "#2e7d4f";
            document.getElementById("regMsg").textContent = pendingRefs.class_id
                ? (isOnline()
                    ? "Saved — syncing to the server now. This student's class hasn't synced yet either, so both will go together."
                    : "Saved offline. This student's class hasn't synced yet either — both will sync together once you're back online.")
                : saveStatusMessage(1);
            document.getElementById("regAdmissionNo").value = "";
            document.getElementById("regFirstName").value = "";
            document.getElementById("regLastName").value = "";
        });
    }

    // ---------------- class / subject / teacher management (admin only) ----------------

    async function renderClassManagement() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const listCard = el(`<div class="card"><h3>Existing Classes</h3><table><thead><tr><th>Name</th><th>Level / arm</th><th>Category</th><th>Status</th></tr></thead><tbody id="clsListBody"></tbody></table></div>`);
        body.appendChild(listCard);

        async function refreshList() {
            const classes = await OfflineDB.getAll(schoolId, "classes");
            document.getElementById("clsListBody").innerHTML = classes.map((c) =>
                `<tr><td>${esc(c.name)}</td><td>${esc(c.level ? c.level + (c.arm ? " · " + c.arm : "") : "—")}</td><td>${esc(c.category || "—")}</td><td>${c._sync.status === "synced" ? "Synced" : "Pending sync"}</td></tr>`
            ).join("");
        }

        const teachers = (await OfflineDB.getAll(schoolId, "users")).filter((u) => u.role === "teacher");
        const CLASS_CATEGORIES = ["", "Science", "Arts", "Commercial"]; // must mirror CLASS_CATEGORIES in db.py
        const formCard = el(`
            <div class="card">
                <h3>Add a Class</h3>
                <label>Name (or just the level, if you add arms)</label><input type="text" id="clsName" placeholder="e.g. JSS 1A — or JSS 1">
                <label>Arms (optional)</label><input type="text" id="clsArms" placeholder="A, B, C  → JSS 1 A, JSS 1 B, JSS 1 C">
                <label>Category (optional)</label>
                <select id="clsCategory">${CLASS_CATEGORIES.map((c) => `<option value="${c}">${c || "None"}</option>`).join("")}</select>
                <label>Form Teacher (optional)</label>
                <select id="clsFormTeacher"><option value="">None</option>${refOptions(teachers, (t) => t.name)}</select>
                <button class="btn" id="clsSaveBtn" style="margin-top:1rem;">Add Class</button>
                <p id="clsMsg" style="color:#2e7d4f;"></p>
            </div>
        `);
        body.appendChild(formCard);
        frame("Manage Classes", body);
        await refreshList();

        document.getElementById("clsSaveBtn").addEventListener("click", async () => {
            const name = document.getElementById("clsName").value.trim();
            const msg = document.getElementById("clsMsg");
            if (!name) { msg.style.color = "#b3261e"; msg.textContent = "Class name is required."; return; }
            const category = document.getElementById("clsCategory").value || null;
            const teacherVal = document.getElementById("clsFormTeacher").value;
            // "JSS 1" + arms "A, B, C" makes three classes, exactly as the online screen does.
            const seen = new Set();
            const arms = document.getElementById("clsArms").value.split(/[,;\n]+/)
                .map((a) => a.split(/\s+/).filter(Boolean).join(" ").slice(0, 20))
                .filter((a) => a && !seen.has(a.toLowerCase()) && seen.add(a.toLowerCase())).slice(0, 30);
            const existingNames = new Set((await OfflineDB.getAll(schoolId, "classes")).map((c) => c.name.toLowerCase()));
            const planned = arms.length ? arms.map((arm) => ({ name: `${name} ${arm}`, level: name, arm })) : [{ name, level: null, arm: null }];
            const dupes = planned.filter((p) => existingNames.has(p.name.toLowerCase())).map((p) => p.name);
            if (dupes.length) { msg.style.color = "#b3261e"; msg.textContent = "Already exists: " + dupes.join(", "); return; }
            for (const p of planned) {
                const data = { name: p.name, category };
                if (p.level) { data.level = p.level; data.arm = p.arm; }
                const pendingRefs = {};
                if (teacherVal) applyRefSelection(teacherVal, "form_teacher_id", "users", data, pendingRefs);
                await SyncEngine.queueChange(schoolId, "classes", "create", data, undefined, pendingRefs);
            }
            msg.style.color = "#2e7d4f";
            msg.textContent = saveStatusMessage(planned.length).replace(/\d+ records?/, `${planned.length} class(es)`);
            document.getElementById("clsName").value = "";
            document.getElementById("clsArms").value = "";
            await refreshList();
        });
    }

    async function renderSubjectManagement() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const listCard = el(`<div class="card"><h3>Existing Subjects</h3><table><thead><tr><th>Name</th><th>Status</th></tr></thead><tbody id="subjListBody"></tbody></table></div>`);
        body.appendChild(listCard);

        async function refreshList() {
            const subjects = await OfflineDB.getAll(schoolId, "subjects");
            document.getElementById("subjListBody").innerHTML = subjects.map((s) =>
                `<tr><td>${esc(s.name)}</td><td>${s._sync.status === "synced" ? "Synced" : "Pending sync"}</td></tr>`
            ).join("");
        }

        const formCard = el(`
            <div class="card">
                <h3>Add a Subject</h3>
                <label>Name</label><input type="text" id="subjName" placeholder="e.g. Further Mathematics">
                <button class="btn" id="subjSaveBtn" style="margin-top:1rem;">Add Subject</button>
                <p id="subjMsg" style="color:#2e7d4f;"></p>
            </div>
        `);
        body.appendChild(formCard);
        frame("Manage Subjects", body);
        await refreshList();

        document.getElementById("subjSaveBtn").addEventListener("click", async () => {
            const name = document.getElementById("subjName").value.trim();
            const msg = document.getElementById("subjMsg");
            if (!name) { msg.style.color = "#b3261e"; msg.textContent = "Subject name is required."; return; }
            await SyncEngine.queueChange(schoolId, "subjects", "create", { name });
            msg.style.color = "#2e7d4f";
            msg.textContent = saveStatusMessage(1);
            document.getElementById("subjName").value = "";
            await refreshList();
        });
    }

    async function renderTeacherManagement() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const listCard = el(`<div class="card"><h3>Existing Teachers / Staff</h3><table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody id="tListBody"></tbody></table></div>`);
        body.appendChild(listCard);

        // Same rule the server enforces: the main admin manages every staff
        // account; a sub-admin manages teachers only (never other sub-admins).
        const canEdit = (u) => !!u.id && u.role !== "admin" && (session.user.role === "admin" || u.role === "teacher");

        async function refreshList() {
            const staff = (await OfflineDB.getAll(schoolId, "users")).filter((u) => u.role !== "admin");
            const tbody = document.getElementById("tListBody");
            tbody.innerHTML = "";
            for (const u of staff) {
                const tr = el(`<tr><td>${esc(u.name)}</td><td>${esc(u.username)}</td><td>${esc(u.role)}${u.position ? " · " + esc(POSITIONS[u.position] || u.position) : ""}</td><td>${u._sync.status === "synced" ? "Synced" : "Pending sync"}</td><td></td></tr>`);
                if (canEdit(u)) {
                    const b = el(`<button class="btn btn-small">Edit / reset password</button>`);
                    b.addEventListener("click", () => openEditor(u));
                    tr.lastElementChild.appendChild(b);
                }
                tbody.appendChild(tr);
            }
        }

        function openEditor(u) {
            document.querySelectorAll(".staffEditor").forEach((n) => n.remove());
            const card = el(`<div class="card staffEditor">
                <h3>Edit ${esc(u.name)}</h3>
                <label>Full Name</label><input type="text" id="eName" value="${esc(u.name)}">
                <label>Position</label>
                <select id="ePosition">${Object.entries(POSITIONS).map(([k, v]) => `<option value="${esc(k)}" ${(u.position || "") === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
                <label>New password <span style="font-weight:normal; color:#777;">(leave blank to keep the current one)</span></label>
                <input type="password" id="ePassword" autocomplete="new-password">
                <button class="btn" id="eSave" style="margin-top:1rem;">Save changes</button>
                <button class="btn" id="eCancel" style="margin-top:1rem; background:#888;">Cancel</button>
                <p id="eMsg"></p>
            </div>`);
            listCard.after(card);
            card.querySelector("#eCancel").addEventListener("click", () => card.remove());
            card.querySelector("#eSave").addEventListener("click", async () => {
                const msg = card.querySelector("#eMsg");
                const name = card.querySelector("#eName").value.trim();
                const password = card.querySelector("#ePassword").value;
                if (!name) { msg.style.color = "#b3261e"; msg.textContent = "Name can't be empty."; return; }
                if (password && password.length < 6) { msg.style.color = "#b3261e"; msg.textContent = "Use a password of at least 6 characters."; return; }
                const data = { name, position: card.querySelector("#ePosition").value || null };
                if (password) {
                    msg.style.color = "#555"; msg.textContent = "Securing the password on this device…";
                    data.password_hash = await OfflineCrypto.hashPasswordForServer(password);
                }
                await SyncEngine.queueChange(schoolId, "users", "update", data, u.client_uuid);
                card.remove();
                await refreshList();
            });
        }

        // Mirrors POSITION_LABELS in db.py.
        const POSITIONS = { "": "None", principal: "Principal", vice_principal: "Vice Principal", exam_officer: "Exam Officer", subject_teacher: "Subject Teacher", form_teacher: "Form Teacher" };
        const canMakeSubAdmin = session.user.role === "admin";
        const formCard = el(`
            <div class="card">
                <h3>Add a Teacher / Staff Member</h3>
                <label>Full Name</label><input type="text" id="tName">
                <label>Username</label><input type="text" id="tUsername">
                <label>Password</label><input type="password" id="tPassword">
                <label>Position (optional)</label>
                <select id="tPosition">${Object.entries(POSITIONS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
                ${canMakeSubAdmin ? `<label>Role</label><select id="tRole"><option value="teacher">Teacher</option><option value="sub_admin">Sub-Admin</option></select>` : ""}
                <button class="btn" id="tSaveBtn" style="margin-top:1rem;">Add Staff Member</button>
                <p id="tMsg" style="color:#2e7d4f;"></p>
                <p style="font-size:0.8rem; color:#888;">Usernames must be unique across the whole platform, which this device can't fully verify offline — if someone else has already taken this username, you'll see it flagged as a conflict once this syncs.</p>
            </div>
        `);
        body.appendChild(formCard);
        frame("Manage Teachers / Staff", body);
        await refreshList();

        document.getElementById("tSaveBtn").addEventListener("click", async () => {
            const msg = document.getElementById("tMsg");
            const name = document.getElementById("tName").value.trim();
            const username = document.getElementById("tUsername").value.trim();
            const password = document.getElementById("tPassword").value;
            if (!name || !username || !password) { msg.style.color = "#b3261e"; msg.textContent = "Name, username, and password are all required."; return; }
            if (password.length < 6) { msg.style.color = "#b3261e"; msg.textContent = "Use a password of at least 6 characters."; return; }
            msg.style.color = "#555";
            msg.textContent = "Securing the password on this device…";
            // Only a one-way hash is stored and queued — never the password itself.
            const password_hash = await OfflineCrypto.hashPasswordForServer(password);
            document.getElementById("tPassword").value = "";
            const data = {
                name, username, password_hash,
                position: document.getElementById("tPosition").value || null,
                role: canMakeSubAdmin ? document.getElementById("tRole").value : "teacher",
            };
            await SyncEngine.queueChange(schoolId, "users", "create", data);
            msg.style.color = "#2e7d4f";
            msg.textContent = saveStatusMessage(1);
            document.getElementById("tName").value = "";
            document.getElementById("tUsername").value = "";
            document.getElementById("tPassword").value = "";
            await refreshList();
        });
    }

    // ---------------- internet-only actions queue ----------------

    async function renderActionsQueue() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        body.appendChild(el(`<p style="color:#666;">Some things — like emailing results to parents — genuinely need
            a live internet connection. Queue them here while offline; they'll run automatically,
            using this device's regular sync connection, the next time you're online.</p>`));
        const term = await activeTerm();
        // Emailing results needs a class that already exists server-side
        // (results are computed from data the server holds), so unlike
        // other offline screens, a not-yet-synced class isn't offered here.
        const classes = (await OfflineDB.getAll(schoolId, "classes")).filter((c) => c.id);
        if (!term || !classes.length) {
            body.appendChild(el(`<p>No synced classes/term available yet on this device — connect once online first.</p>`));
            frame("Queue Internet-Only Actions", body);
            return;
        }
        const formCard = el(`
            <div class="card">
                <h3>Email Results to Parents</h3>
                <label>Class</label>
                <select id="actClassSelect">${classes.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
                <button class="btn" id="actQueueBtn" style="margin-top:1rem;">Queue for Next Sync</button>
                <p id="actMsg" style="color:#2e7d4f;"></p>
            </div>
        `);
        body.appendChild(formCard);
        const queuedCard = el(`<div class="card"><h3>Queued Actions</h3><div id="queuedList"></div></div>`);
        body.appendChild(queuedCard);
        frame("Queue Internet-Only Actions", body);

        async function refreshQueuedList() {
            const actions = await OfflineDB.getAll(schoolId, "actions");
            const list = document.getElementById("queuedList");
            list.innerHTML = actions.length ? "" : "<p>Nothing queued.</p>";
            for (const a of actions) {
                const statusLabel = a._sync.status === "synced" ? "Done" : a._sync.status === "failed" ? "Failed — will retry" : "Waiting to sync";
                list.appendChild(el(`<div style="border-top:1px solid #eee; padding:0.4rem 0;">
                    ${esc(a.action_type)} (class ${esc(a.payload.class_id)}) — ${statusLabel}
                    ${a._sync.result_message ? `<br><span style="font-size:0.8rem; color:#888;">${esc(a._sync.result_message)}</span>` : ""}
                    ${a._sync.last_error ? `<br><span style="font-size:0.8rem; color:#b3261e;">${esc(a._sync.last_error)}</span>` : ""}
                </div>`));
            }
        }
        await refreshQueuedList();

        document.getElementById("actQueueBtn").addEventListener("click", async () => {
            const classId = parseInt(document.getElementById("actClassSelect").value, 10);
            await SyncEngine.queueAction(schoolId, "email_class_results", { class_id: classId, term_id: term.id });
            document.getElementById("actMsg").textContent = "Queued — will run automatically once this device is back online.";
            await refreshQueuedList();
        });
    }

    // ---------------- helpers for results / import-export screens ----------------

    function downloadBlob(filename, blob) {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    }

    function safeName(s) { return String(s).replace(/[^A-Za-z0-9._-]+/g, "_"); }

    function downloadRows(rows, baseName, format) {
        if (format === "xlsx") {
            downloadBlob(baseName + ".xlsx", new Blob([XlsxLite.write(rows, baseName)],
                { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
        } else {
            downloadBlob(baseName + ".csv", new Blob([OfflineResults.toCsv(rows)], { type: "text/csv;charset=utf-8" }));
        }
    }

    async function readTable(file) {
        if (/\.xlsx$/i.test(file.name)) return XlsxLite.read(await file.arrayBuffer());
        if (/\.xls$/i.test(file.name)) throw new Error("Old .xls files can't be read offline — save the sheet as .xlsx or CSV.");
        return OfflineResults.parseCsv(await file.text());
    }

    // Result sheets are shown in, and printed from, an isolated iframe so their
    // print styles never leak into the app. "Save as PDF" is the browser's own
    // print dialog, which works with no connection.
    function sheetFrame(bodyHtml, title, height) {
        const f = document.createElement("iframe");
        f.style.cssText = `width:100%; height:${height || 560}px; border:1px solid #ccc; background:#fff;`;
        f.srcdoc = OfflineResults.documentHtml(bodyHtml, title);
        return f;
    }

    function printHtml(bodyHtml, title) {
        const f = document.createElement("iframe");
        f.style.cssText = "position:fixed; right:0; bottom:0; width:0; height:0; border:0;";
        document.body.appendChild(f);
        f.srcdoc = OfflineResults.documentHtml(bodyHtml, title);
        f.onload = () => {
            setTimeout(() => { f.contentWindow.focus(); f.contentWindow.print(); }, 200);
            setTimeout(() => f.remove(), 120000);
        };
    }

    async function loadResultData(classId, termId) {
        const names = ["students", "subjects", "class_subjects", "scores", "enrollments", "terms", "classes",
            "grading_config", "grade_scale", "student_term_info", "attendance_records",
            "skill_traits", "student_skill_ratings"];
        const d = { classId, termId };
        for (const n of names) d[n] = await OfflineDB.getAll(schoolId, n);
        d.school_profile = await OfflineDB.getMeta(schoolId, "school_profile");
        return d;
    }

    async function hasUnsyncedWork() {
        const c = await OfflineDB.getPendingCounts(schoolId);
        return (c.pending + c.conflict + c.failed) > 0;
    }

    // ---------------- results & broadsheets ----------------

    async function renderResults() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const classes = (await OfflineDB.getAll(schoolId, "classes")).filter((c) => c.id);
        const students = await OfflineDB.getAll(schoolId, "students");
        const usable = classes.filter((c) => students.some((s) => s.class_id === c.id));
        const allTerms = (await OfflineDB.getAll(schoolId, "terms")).filter((t) => t.id);
        const sessions = await OfflineDB.getAll(schoolId, "sessions");
        // Only the current session's scores are kept on the device (older ones are far too
        // much for a phone); earlier sessions' results are on the server.
        const activeIds = sessions.filter((s) => s.is_active && s.id).map((s) => s.id);
        const currentSession = activeIds.length ? Math.max(...activeIds) : Math.max(0, ...sessions.filter((s) => s.id).map((s) => s.id));
        const terms = allTerms.filter((t) => t.session_id === currentSession);
        if (!usable.length || !terms.length) {
            body.appendChild(el(`<p>No class results are available on this device yet. Results are worked out on the device from synced data — connect once online first. (Teachers see results for the class they are form teacher of; principals and admins see every class.)</p>`));
            frame("Results & Broadsheets", body);
            return;
        }
        const activeT = await activeTerm();
        const termLabel = (t) => { const se = sessions.find((x) => x.id === t.session_id); return `${se ? se.name : ""} — ${t.name}`; };
        const controls = el(`<div class="card">
            <p style="font-size:0.8rem; color:#777; margin:0;">Showing this session. Earlier sessions' results are on the server: <a href="/classes" id="rsOlder">open them online</a>.</p>
            <label>Class</label><select id="rsClass">${usable.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            <label>Term</label><select id="rsTerm">${terms.map((t) => `<option value="${t.id}" ${activeT && activeT.id === t.id ? "selected" : ""}>${esc(termLabel(t))}</option>`).join("")}</select>
            <button class="btn" id="rsLoad" style="margin-top:1rem;">Show results</button>
        </div>`);
        const out = el(`<div id="rsOut"></div>`);
        controls.querySelector("#rsOlder").addEventListener("click", (ev) => { if (!isOnline()) { ev.preventDefault(); toast("Earlier sessions need an internet connection."); } });
        body.appendChild(controls);
        body.appendChild(out);
        frame("Results & Broadsheets", body);

        document.getElementById("rsLoad").addEventListener("click", async () => {
            const classId = parseInt(document.getElementById("rsClass").value, 10);
            const termId = parseInt(document.getElementById("rsTerm").value, 10);
            const d = await loadResultData(classId, termId);
            const sheet = OfflineResults.buildBroadsheet(d);
            const profile = await OfflineDB.getMeta(schoolId, "school_profile");
            const logo = await OfflineDB.getMeta(schoolId, "school_logo");
            const cls = d.classes.find((c) => c.id === classId);
            const note = (await hasUnsyncedWork()) ? "Includes changes on this device that haven't synced yet." : "";
            out.innerHTML = "";
            if (!sheet.rows.length) { out.appendChild(el(`<p>No students in this class for that term.</p>`)); return; }

            const showCa3 = OfflineResults.ca3Enabled(d.grading_config[0]);
            const actions = el(`<div class="card">
                <button class="btn btn-small" id="rsBroad">View / print broadsheet</button>
                <button class="btn btn-small" id="rsAll">Print all result sheets</button>
                <button class="btn btn-small" id="rsCum">Cumulative (whole session)</button>
                <button class="btn btn-small" id="rsCsv" style="background:#555;">Broadsheet CSV</button>
                <button class="btn btn-small" id="rsXlsx" style="background:#555;">Broadsheet Excel</button>
                ${note ? `<p style="font-size:0.85rem; color:#a97f22;">${esc(note)}</p>` : ""}
                <p style="font-size:0.8rem; color:#777;">Printing opens your device's print dialog — choose "Save as PDF" to make a PDF file. Both work without internet.</p>
            </div>`);
            const table = el(`<div class="card"><table><thead><tr><th>Pos.</th><th>Student</th><th>Total</th><th>Average</th><th></th></tr></thead><tbody></tbody></table></div>`);
            for (const r of sheet.rows) {
                const tr = el(`<tr><td>${r.position}</td><td>${esc(OfflineResults.fullName(r.student))}</td><td>${esc(r.total)}</td><td>${esc(r.average)}</td><td><button class="btn btn-small">Result sheet</button></td></tr>`);
                tr.querySelector("button").addEventListener("click", () => {
                    const res = OfflineResults.buildResult(d, r.student.client_uuid);
                    const html = OfflineResults.resultSheetHtml(res, profile, logo, { unsyncedNote: note });
                    const view = el(`<div class="card"><h3>${esc(OfflineResults.fullName(r.student))}</h3></div>`);
                    const fr = sheetFrame(html, "Result sheet", 620);
                    const printBtn = el(`<button class="btn" style="margin-top:0.5rem;">Print / save as PDF</button>`);
                    printBtn.addEventListener("click", () => { fr.contentWindow.focus(); fr.contentWindow.print(); });
                    view.appendChild(fr);
                    view.appendChild(printBtn);
                    out.querySelectorAll(".sheetView").forEach((n) => n.remove());
                    view.classList.add("sheetView");
                    out.appendChild(view);
                    view.scrollIntoView();
                });
                table.querySelector("tbody").appendChild(tr);
            }
            out.appendChild(actions);
            out.appendChild(table);

            const broadRows = () => {
                const head = ["Pos.", "Student"].concat(sheet.subjects.map((x) => x.name), ["Total", "Average"]);
                const rows = sheet.rows.map((r) => [r.position, OfflineResults.fullName(r.student)]
                    .concat(sheet.subjects.map((x) => (r.scores[x.id] ? r.scores[x.id].total : "")), [r.total, r.average]));
                return [head].concat(rows);
            };
            const base = "broadsheet_" + safeName(cls ? cls.name : "class") + "_" + safeName((sheet.term && sheet.term.name) || "term");
            actions.querySelector("#rsBroad").addEventListener("click", () => {
                const html = OfflineResults.broadsheetHtml(sheet, cls, profile, logo);
                out.querySelectorAll(".sheetView").forEach((n) => n.remove());
                const view = el(`<div class="card sheetView"><h3>Broadsheet</h3></div>`);
                const fr = sheetFrame(html, "Broadsheet", 520);
                const pb = el(`<button class="btn" style="margin-top:0.5rem;">Print / save as PDF</button>`);
                pb.addEventListener("click", () => { fr.contentWindow.focus(); fr.contentWindow.print(); });
                view.appendChild(fr); view.appendChild(pb);
                out.appendChild(view);
                view.scrollIntoView();
            });
            actions.querySelector("#rsAll").addEventListener("click", () => {
                const html = sheet.rows.map((r) => OfflineResults.resultSheetHtml(OfflineResults.buildResult(d, r.student.client_uuid), profile, logo, { unsyncedNote: note })).join("");
                printHtml(html, "Result sheets");
            });
            actions.querySelector("#rsCum").addEventListener("click", () => {
                const sessionId = sheet.term ? sheet.term.session_id : null;
                const cum = OfflineResults.buildCumulativeBroadsheet({ ...d, sessionId });
                const se = sessions.find((x) => x.id === sessionId);
                out.querySelectorAll(".sheetView").forEach((n) => n.remove());
                const view = el(`<div class="card sheetView"><h3>Cumulative broadsheet — ${esc(se ? se.name : "")}</h3></div>`);
                const fr = sheetFrame(OfflineResults.cumulativeHtml(cum, cls, profile, logo, se && se.name), "Cumulative broadsheet", 520);
                const pb = el(`<button class="btn" style="margin-top:0.5rem;">Print / save as PDF</button>`);
                pb.addEventListener("click", () => { fr.contentWindow.focus(); fr.contentWindow.print(); });
                const dl = el(`<button class="btn btn-small" style="margin-top:0.5rem; margin-left:0.3rem; background:#555;">Excel</button>`);
                dl.addEventListener("click", () => {
                    const head = ["Pos.", "Student"];
                    for (const sb of cum.subjects) { for (const t of cum.terms) head.push(`${sb.name} ${t.name}`); head.push(`${sb.name} Avg`); }
                    head.push("Overall");
                    const rows = cum.rows.map((r) => {
                        const line = [r.position, OfflineResults.fullName(r.student)];
                        for (const sb of cum.subjects) { const c = r.subjects[sb.id]; c.term_values.forEach((v) => line.push(v === null ? "" : v)); line.push(c.average === "-" ? "" : c.average); }
                        line.push(r.average);
                        return line;
                    });
                    downloadRows([head].concat(rows), "cumulative_" + safeName(cls ? cls.name : "class"), "xlsx");
                });
                view.appendChild(fr); view.appendChild(pb); view.appendChild(dl);
                out.appendChild(view);
                view.scrollIntoView();
            });
            actions.querySelector("#rsCsv").addEventListener("click", () => downloadRows(broadRows(), base, "csv"));
            actions.querySelector("#rsXlsx").addEventListener("click", () => downloadRows(broadRows(), base, "xlsx"));
            void showCa3;
        });
    }

    // ---------------- import / export (CSV and Excel) ----------------

    async function renderImportExport() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const classes = (await OfflineDB.getAll(schoolId, "classes")).filter((c) => c.id);
        const admin = isAdminRole();
        const teach = await teachingClasses();

        // -- students export
        const stuCard = el(`<div class="card"><h3>Students</h3>
            <label>Class</label><select id="ieStuClass">${classes.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            <button class="btn btn-small" id="ieStuCsv" style="margin-top:0.75rem;">Export CSV</button>
            <button class="btn btn-small" id="ieStuXlsx" style="margin-top:0.75rem; background:#555;">Export Excel</button>
        </div>`);
        body.appendChild(stuCard);
        stuCard.querySelector("#ieStuCsv").addEventListener("click", () => exportStudents("csv"));
        stuCard.querySelector("#ieStuXlsx").addEventListener("click", () => exportStudents("xlsx"));
        async function exportStudents(fmt) {
            const classId = parseInt(stuCard.querySelector("#ieStuClass").value, 10);
            const cls = classes.find((c) => c.id === classId);
            const list = (await OfflineDB.getAll(schoolId, "students")).filter((s) => s.class_id === classId)
                .sort((a, b) => (a.last_name < b.last_name ? -1 : 1));
            const head = ["admission_no", "first_name", "last_name", "other_names", "gender", "class_name", "date_of_birth", "religion", "parent_name", "parent_address", "parent_email", "parent_phone"];
            const rows = [head].concat(list.map((s) => head.map((h) => (h === "class_name" ? (cls ? cls.name : "") : (s[h] ?? "")))));
            downloadRows(rows, "students_" + safeName(cls ? cls.name : "class"), fmt);
        }

        // -- students import (admins)
        if (admin) {
            const impCard = el(`<div class="card"><h3>Import students</h3>
                <p style="font-size:0.85rem; color:#666;">Columns: admission_no, first_name, last_name, class_name (required); other_names, gender, date_of_birth, religion, parent_name, parent_address, parent_email, parent_phone (optional). Classes must already exist.</p>
                <input type="file" id="ieStuFile" accept=".csv,.xlsx">
                <div id="ieStuPlan"></div></div>`);
            body.appendChild(impCard);
            impCard.querySelector("#ieStuFile").addEventListener("change", async (e) => {
                const holder = impCard.querySelector("#ieStuPlan");
                holder.innerHTML = "";
                const file = e.target.files[0];
                if (!file) return;
                try {
                    const rows = await readTable(file);
                    const plan = OfflineResults.planStudentImport(rows, await OfflineDB.getAll(schoolId, "classes"), await OfflineDB.getAll(schoolId, "students"));
                    renderPlan(holder, `${plan.creates.length} student(s) ready to import`, plan.skipped, plan.creates.length ? "Import them" : null, async () => {
                        for (const c of plan.creates) await SyncEngine.queueChange(schoolId, "students", "create", c);
                        holder.innerHTML = `<p style="color:#2e7d4f;">Imported ${plan.creates.length} student(s) on this device. They sync when you're back online.</p>`;
                    });
                } catch (err) {
                    holder.innerHTML = `<p style="color:#b3261e;">${esc(err.message)}</p>`;
                }
            });
        }

        // -- scores export/import
        const scoreCard = el(`<div class="card"><h3>Scores</h3>
            <label>Class</label><select id="ieScClass"><option value="">Choose a class…</option>${teach.filter((c) => c.id).map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            <label>Subject</label><select id="ieScSubject"><option value="">Choose a class first…</option></select>
            <div id="ieScButtons" style="display:none; margin-top:0.75rem;">
                <button class="btn btn-small" id="ieScCsv">Export template (CSV)</button>
                <button class="btn btn-small" id="ieScXlsx" style="background:#555;">Export template (Excel)</button>
                <p style="font-size:0.85rem; color:#666;">Fill in the marks, then import the file back here.</p>
                <input type="file" id="ieScFile" accept=".csv,.xlsx">
                <div id="ieScPlan"></div>
            </div></div>`);
        body.appendChild(scoreCard);
        frame("Import / Export", body);

        function renderPlan(holder, headline, skipped, buttonLabel, onConfirm) {
            holder.innerHTML = `<p><b>${esc(headline)}</b></p>` +
                (skipped.length ? `<details open><summary style="color:#b3261e;">${skipped.length} row(s) skipped</summary><ul style="font-size:0.85rem;">${skipped.slice(0, 30).map((x) => `<li>${esc(x)}</li>`).join("")}${skipped.length > 30 ? `<li>…and ${skipped.length - 30} more</li>` : ""}</ul></details>` : "");
            if (buttonLabel) {
                const b = el(`<button class="btn">${esc(buttonLabel)}</button>`);
                b.addEventListener("click", async () => { b.disabled = true; await onConfirm(); });
                holder.appendChild(b);
            }
        }

        const term = await activeTerm();
        const config = (await OfflineDB.getAll(schoolId, "grading_config"))[0] || { ca1_max: 20, ca2_max: 20, ca3_max: 0, exam_max: 60 };
        scoreCard.querySelector("#ieScClass").addEventListener("change", async () => {
            const classId = parseInt(scoreCard.querySelector("#ieScClass").value, 10);
            const sel = scoreCard.querySelector("#ieScSubject");
            scoreCard.querySelector("#ieScButtons").style.display = "none";
            if (!classId) { sel.innerHTML = `<option value="">Choose a class first…</option>`; return; }
            const links = (await OfflineDB.getAll(schoolId, "class_subjects")).filter((cs) => cs.class_id === classId && (admin || cs.teacher_id === session.user.user_id));
            const subjects = await OfflineDB.getAll(schoolId, "subjects");
            sel.innerHTML = `<option value="">Choose a subject…</option>` + links.map((l) => { const sb = subjects.find((x) => x.id === l.subject_id); return sb ? `<option value="${sb.id}">${esc(sb.name)}</option>` : ""; }).join("");
        });
        scoreCard.querySelector("#ieScSubject").addEventListener("change", () => {
            scoreCard.querySelector("#ieScButtons").style.display = scoreCard.querySelector("#ieScSubject").value ? "block" : "none";
            scoreCard.querySelector("#ieScPlan").innerHTML = "";
        });
        async function scoreContext() {
            const classId = parseInt(scoreCard.querySelector("#ieScClass").value, 10);
            const subjectId = parseInt(scoreCard.querySelector("#ieScSubject").value, 10);
            const students = (await OfflineDB.getAll(schoolId, "students")).filter((s) => s.class_id === classId && s.is_active)
                .sort((a, b) => (a.admission_no < b.admission_no ? -1 : 1));
            const all = await OfflineDB.getAll(schoolId, "scores");
            const mine = all.filter((r) => r.subject_id === subjectId && r.term_id === (term && term.id));
            return { classId, subjectId, students, existing: new Map(mine.map((r) => [r.student_id, r])), all: mine };
        }
        async function exportScores(fmt) {
            if (!term) { alert("No active term on this device — sync once while online."); return; }
            const c = await scoreContext();
            const cls = classes.find((x) => x.id === c.classId);
            const sb = (await OfflineDB.getAll(schoolId, "subjects")).find((x) => x.id === c.subjectId);
            downloadRows(OfflineResults.scoresExportRows(c.students, c.existing, config), "scores_" + safeName(cls ? cls.name : "") + "_" + safeName(sb ? sb.name : ""), fmt);
        }
        scoreCard.querySelector("#ieScCsv").addEventListener("click", () => exportScores("csv"));
        scoreCard.querySelector("#ieScXlsx").addEventListener("click", () => exportScores("xlsx"));
        scoreCard.querySelector("#ieScFile").addEventListener("change", async (e) => {
            const holder = scoreCard.querySelector("#ieScPlan");
            holder.innerHTML = "";
            const file = e.target.files[0];
            if (!file) return;
            try {
                if (!term) throw new Error("No active term on this device — sync once while online.");
                const c = await scoreContext();
                const plan = OfflineResults.planScoreImport(await readTable(file), c.students, config);
                renderPlan(holder, `${plan.updates.length} student score row(s) ready to import`, plan.skipped, plan.updates.length ? "Import scores" : null, async () => {
                    let n = 0;
                    for (const u of plan.updates) {
                        const data = { student_id: u.student.id, subject_id: c.subjectId, term_id: term.id, ca1: u.ca1, ca2: u.ca2, ca3: u.ca3, exam: u.exam };
                        const ex = c.existing.get(u.student.id);
                        if (ex) {
                            if (["ca1", "ca2", "ca3", "exam"].every((f) => OfflineResults.num(ex[f]) === data[f])) continue;
                            await SyncEngine.queueChange(schoolId, "scores", "update", data, ex.client_uuid);
                        } else await SyncEngine.queueChange(schoolId, "scores", "create", data);
                        n++;
                    }
                    holder.innerHTML = `<p style="color:#2e7d4f;">Imported ${n} changed row(s) on this device. They sync when you're back online.</p>`;
                });
            } catch (err) {
                holder.innerHTML = `<p style="color:#b3261e;">${esc(err.message)}</p>`;
            }
        });
    }

    // ---------------- learning materials ----------------
    // Every material this person may see is listed from the device's own copy of the
    // school's data. "Save for offline" downloads the file once (needs the server); saved
    // files open with no connection. Uploading and removing materials is an online action.

    async function renderMaterials() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const [mats, classes, subjects] = await Promise.all(["materials", "classes", "subjects"].map((e) => OfflineDB.getAll(schoolId, e)));
        const saved = typeof OfflineMaterials !== "undefined" ? await OfflineMaterials.list(schoolId) : [];
        const savedIds = new Set(saved.map((x) => x.id));
        const className = (id) => { const c = classes.find((x) => x.id === id); return c ? c.name : ""; };
        const subjectName = (id) => { const x = subjects.find((y) => y.id === id); return x ? x.name : ""; };

        const bar = el(`<div class="card"><label>Class</label><select id="mtClass"><option value="">All classes</option>${
            classes.filter((c) => mats.some((m) => m.class_id === c.id)).map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
            <a class="btn btn-small" href="/materials" id="mtManage" style="margin-top:0.75rem;">Upload or manage materials (needs internet)</a></div>`);
        bar.querySelector("#mtManage").addEventListener("click", (ev) => { if (!isOnline()) { ev.preventDefault(); toast("Uploading materials needs an internet connection."); } });
        body.appendChild(bar);
        const listWrap = el(`<div></div>`);
        body.appendChild(listWrap);
        frame("Learning Materials", body);

        const draw = () => {
            const filter = parseInt(bar.querySelector("#mtClass").value, 10) || null;
            const rows = mats.filter((m) => !filter || m.class_id === filter)
                .sort((a, b) => String(b.uploaded_at || "").localeCompare(String(a.uploaded_at || "")));
            listWrap.innerHTML = "";
            if (!rows.length && !saved.length) {
                listWrap.appendChild(el(`<div class="card"><p>No learning materials yet.${mats.length ? "" : " They appear here after this device has synced."}</p></div>`));
                return;
            }
            const card = el(`<div class="card"><table><thead><tr><th>Title</th><th>Class</th><th>Subject</th><th>Type</th><th></th></tr></thead><tbody></tbody></table></div>`);
            const tbody = card.querySelector("tbody");
            for (const m of rows) {
                const tr = el(`<tr><td>${esc(m.title)}</td><td>${esc(className(m.class_id))}</td><td>${esc(subjectName(m.subject_id))}</td><td>${esc(m.kind || "")}</td><td></td></tr>`);
                const cell = tr.lastElementChild;
                const meta = { id: m.id, title: m.title, kind: m.kind, subject: subjectName(m.subject_id), class_name: className(m.class_id),
                               filename: m.original_filename || m.filename || null, external_url: m.external_url || null };
                if (savedIds.has(m.id) && !m.external_url) {
                    const open = el(`<button class="btn btn-small">Open</button>`);
                    open.addEventListener("click", async () => {
                        const blob = await OfflineMaterials.blobFor(schoolId, m.id);
                        if (blob) downloadBlob(meta.filename || safeName(m.title), blob);
                        else toast("That file is no longer stored on this device. Save it again while online.");
                    });
                    const rm = el(`<button class="btn btn-small" style="background:#888; margin-left:0.3rem;">Remove</button>`);
                    rm.addEventListener("click", async () => { await OfflineMaterials.remove(schoolId, m.id); renderMaterials(); });
                    cell.appendChild(open); cell.appendChild(rm);
                } else {
                    const label = m.external_url ? "Open link" : "Save for offline";
                    const btn = el(`<button class="btn btn-small">${label}</button>`);
                    btn.addEventListener("click", async () => {
                        if (!isOnline()) { toast(m.external_url ? "Links need an internet connection." : "Saving a file needs an internet connection — do it once while connected."); return; }
                        if (m.external_url) { window.open(m.external_url, "_blank", "noopener"); return; }
                        btn.disabled = true; btn.textContent = "Saving…";
                        try { await OfflineMaterials.save(schoolId, meta); renderMaterials(); }
                        catch (e) { btn.disabled = false; btn.textContent = label; toast(e.message); }
                    });
                    cell.appendChild(btn);
                }
                tbody.appendChild(tr);
            }
            listWrap.appendChild(card);
        };
        bar.querySelector("#mtClass").addEventListener("change", draw);
        draw();
    }

    // ---------------- school & grading settings (read-only offline) ----------------

    async function renderSettings() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const profile = await OfflineDB.getMeta(schoolId, "school_profile");
        const cfg = (await OfflineDB.getAll(schoolId, "grading_config"))[0];
        const scale = (await OfflineDB.getAll(schoolId, "grade_scale")).sort((a, b) => OfflineResults.num(b.min_score) - OfflineResults.num(a.min_score));
        body.appendChild(el(`<div class="card"><h3>School</h3><p><b>${esc(profile ? profile.name : "")}</b></p></div>`));
        if (cfg) {
            const ca3 = OfflineResults.ca3Enabled(cfg);
            body.appendChild(el(`<div class="card"><h3>Score weighting</h3>
                <p>CA1 max ${esc(cfg.ca1_max)} · CA2 max ${esc(cfg.ca2_max)} · ${ca3 ? `CA3 max ${esc(cfg.ca3_max)} · ` : "CA3 not used · "}Exam max ${esc(cfg.exam_max)}</p></div>`));
        }
        if (scale.length) {
            body.appendChild(el(`<div class="card"><h3>Grade scale</h3><table><thead><tr><th>Grade</th><th>From</th><th>To</th><th>Remark</th></tr></thead><tbody>${
                scale.map((g) => `<tr><td>${esc(g.grade)}</td><td>${esc(g.min_score)}</td><td>${esc(g.max_score)}</td><td>${esc(g.remark || "")}</td></tr>`).join("")}</tbody></table></div>`));
        }
        if (isAdminRole()) {
            const edCard = el(`<div class="card"><h3>Edit grade bands</h3>
                <p style="font-size:0.85rem; color:#666;">Change a band, or add a new one. Bands can't overlap, and each must stay between 0 and 100. Removing a band is done online.</p>
                <table><thead><tr><th>Grade</th><th>From</th><th>To</th><th>Remark</th><th></th></tr></thead><tbody></tbody></table>
                <p id="gbMsg"></p></div>`);
            const tb = edCard.querySelector("tbody");
            const msg = edCard.querySelector("#gbMsg");
            const bandInputs = (b) => `<td><input type="text" class="gbG" value="${esc(b ? b.grade : "")}" style="width:4rem;"></td>
                <td><input type="number" class="gbMin" step="0.01" value="${esc(b ? b.min_score : "")}" style="width:5rem;"></td>
                <td><input type="number" class="gbMax" step="0.01" value="${esc(b ? b.max_score : "")}" style="width:5rem;"></td>
                <td><input type="text" class="gbR" value="${esc(b ? (b.remark || "") : "")}"></td>`;
            const readRow = (tr) => ({ grade: tr.querySelector(".gbG").value.trim(), min_score: Number(tr.querySelector(".gbMin").value),
                max_score: Number(tr.querySelector(".gbMax").value), remark: tr.querySelector(".gbR").value.trim() });
            const problems = (row, self) => {
                if (!row.grade) return "Enter a grade (e.g. A, B, C).";
                if (!Number.isFinite(row.min_score) || !Number.isFinite(row.max_score)) return "From and To must be numbers.";
                if (row.min_score < 0 || row.max_score > 100) return "Limits must be between 0 and 100.";
                if (row.min_score > row.max_score) return "From can't be higher than To.";
                const clash = scale.find((o) => o !== self && row.min_score <= Number(o.max_score) && Number(o.min_score) <= row.max_score);
                return clash ? `That overlaps the band ${clash.grade} (${clash.min_score}–${clash.max_score}).` : null;
            };
            for (const b of scale) {
                const tr = el(`<tr>${bandInputs(b)}<td></td></tr>`);
                const save = el(`<button class="btn btn-small">Save</button>`);
                save.addEventListener("click", async () => {
                    const row = readRow(tr);
                    const bad = problems(row, b);
                    if (bad) { msg.style.color = "#b3261e"; msg.textContent = bad; return; }
                    await SyncEngine.queueChange(schoolId, "grade_scale", "update", row, b.client_uuid);
                    toast("Saved. It syncs automatically.");
                    renderSettings();
                });
                tr.lastElementChild.appendChild(save);
                tb.appendChild(tr);
            }
            const addRow = el(`<tr>${bandInputs(null)}<td></td></tr>`);
            const add = el(`<button class="btn btn-small" style="background:#555;">Add band</button>`);
            add.addEventListener("click", async () => {
                const row = readRow(addRow);
                const bad = problems(row, null);
                if (bad) { msg.style.color = "#b3261e"; msg.textContent = bad; return; }
                await SyncEngine.queueChange(schoolId, "grade_scale", "create", row);
                toast("Added. It syncs automatically.");
                renderSettings();
            });
            addRow.lastElementChild.appendChild(add);
            tb.appendChild(addRow);
            body.appendChild(edCard);
        }
        if (cfg && isAdminRole()) {
            const form = el(`<div class="card"><h3>Change maximum marks</h3>
                <p style="font-size:0.85rem; color:#a97f22;">This changes how every student in the school is graded and syncs to all devices. The maximums can't add up to more than 100, and can't be set below a mark that is already saved.</p>
                <div class="grid-2">
                    <div><label>CA1 max</label><input type="number" min="0" step="0.5" id="wCa1" value="${esc(cfg.ca1_max)}"></div>
                    <div><label>CA2 max</label><input type="number" min="0" step="0.5" id="wCa2" value="${esc(cfg.ca2_max)}"></div>
                    <div><label>CA3 max (0 = not used)</label><input type="number" min="0" step="0.5" id="wCa3" value="${esc(cfg.ca3_max || 0)}"></div>
                    <div><label>Exam max</label><input type="number" min="0" step="0.5" id="wExam" value="${esc(cfg.exam_max)}"></div>
                </div>
                <button class="btn" id="wSave" style="margin-top:1rem;">Save settings</button>
                <p id="wMsg"></p></div>`);
            body.appendChild(form);
            form.querySelector("#wSave").addEventListener("click", async () => {
                const msg = form.querySelector("#wMsg");
                const v = { ca1_max: Number(form.querySelector("#wCa1").value), ca2_max: Number(form.querySelector("#wCa2").value),
                            ca3_max: Number(form.querySelector("#wCa3").value || 0), exam_max: Number(form.querySelector("#wExam").value) };
                const vals = Object.values(v);
                if (vals.some((x) => !Number.isFinite(x) || x < 0)) { msg.style.color = "#b3261e"; msg.textContent = "Every maximum must be a number, zero or more."; return; }
                const sum = vals.reduce((a, b) => a + b, 0);
                if (sum > 100.0001) { msg.style.color = "#b3261e"; msg.textContent = `The maximums add up to ${sum}; they can't exceed 100.`; return; }
                const scores = await OfflineDB.getAll(schoolId, "scores");
                for (const [f, k] of [["ca1", "ca1_max"], ["ca2", "ca2_max"], ["ca3", "ca3_max"], ["exam", "exam_max"]]) {
                    const hi = scores.reduce((m, r) => Math.max(m, OfflineResults.num(r[f])), 0);
                    if (hi > v[k]) { msg.style.color = "#b3261e"; msg.textContent = `${f.toUpperCase()} max can't be ${v[k]}: a saved score is already ${hi}.`; return; }
                }
                await SyncEngine.queueChange(schoolId, "grading_config", "update", v, cfg.client_uuid);
                msg.style.color = "#2e7d4f";
                msg.textContent = sum < 99.9999
                    ? `${saveStatusMessage()} Note: the maximums add up to ${sum}, not 100.`
                    : saveStatusMessage();
            });
        }
        body.appendChild(el(`<p style="font-size:0.85rem; color:#777;">This device receives the latest settings each time it syncs. Removing a grade band is done online.</p>`));
        // Things only the server can do: the same pages as always, one tap away;
        // offline they say so instead of failing.
        const online = el(`<div class="card"><h3>Account &amp; school (needs internet)</h3></div>`);
        const links = [["Change password", "/account/password"], ["School profile & logo", "/admin/school"],
                       ["Email settings", "/admin/email"], ["Offline access on this device", "/settings"]];
        for (const [label, href] of links) {
            if (!isAdminRole() && ["/admin/school", "/admin/email"].includes(href)) continue;
            const a = el(`<a class="btn btn-small" href="${esc(href)}">${esc(label)}</a>`);
            a.addEventListener("click", (ev) => { if (!isOnline()) { ev.preventDefault(); toast(`${label} needs an internet connection.`); } });
            online.appendChild(a);
        }
        body.appendChild(online);
        frame("School & Grading Settings", body);
    }

    // ---------------- sync status ----------------

    function metaKeys(k) { return k.startsWith("_") || k === "is_deleted"; }

    async function labelLookups() {
        return {
            students: await OfflineDB.getAll(schoolId, "students"),
            subjects: await OfflineDB.getAll(schoolId, "subjects"),
        };
    }

    function recordLabel(entity, row, L) {
        const stu = (id) => { const s = L.students.find((x) => x.id === id); return s ? OfflineResults.fullName(s) : "a student"; };
        const sub = (id) => { const s = L.subjects.find((x) => x.id === id); return s ? s.name : "a subject"; };
        switch (entity) {
            case "scores": return `Scores — ${stu(row.student_id)}, ${sub(row.subject_id)}`;
            case "attendance_records": return `Attendance — ${stu(row.student_id)}, ${row.date}`;
            case "student_term_info": return `Comments — ${stu(row.student_id)}`;
            case "students": return `Student — ${OfflineResults.fullName(row)}`;
            case "classes": case "subjects": case "users": return `${entity.slice(0, -1)} — ${row.name}`;
            default: return `${entity} ${String(row.client_uuid).slice(0, 8)}`;
        }
    }

    async function renderSyncStatus() {
        const body = el(`<div></div>`);
        body.appendChild(backButton());
        const syncBtn = el(`<button class="btn" style="margin-bottom:1rem;">Sync Now</button>`);
        syncBtn.addEventListener("click", async () => {
            const s = OfflineAuth.getSession();
            await Connectivity.probeNow();                 // re-verify the connection first
            await SyncEngine.syncNow(schoolId, s.device_id, s.device_secret);
            renderSyncStatus();
        });
        body.appendChild(syncBtn);
        const L = await labelLookups();

        const info = await OfflineAuth.storageInfo();
        const counts = await OfflineDB.getPendingCounts(schoolId);
        const backupCard = el(`<div class="card"><h3>Keep your work safe</h3>
            <p style="font-size:0.9rem;">${counts.pending + counts.failed + counts.conflict} change(s) not yet synced. Storage protection on this browser: <b>${info.persisted ? "on" : "not granted"}</b>${info.usage != null ? ` · using ${(info.usage / 1048576).toFixed(1)} MB` : ""}.</p>
            <button class="btn btn-small" id="bkDownload">Download backup of unsynced changes</button>
            <label class="btn btn-small" style="background:#555; cursor:pointer; margin-left:0.3rem;">Restore from backup<input type="file" id="bkFile" accept=".json" style="display:none;"></label>
            <p id="bkMsg" style="font-size:0.85rem;"></p>
            <p style="font-size:0.8rem; color:#777;">The backup file contains student data — keep it private.</p></div>`);
        backupCard.querySelector("#bkDownload").addEventListener("click", exportBackup);
        backupCard.querySelector("#bkFile").addEventListener("change", async (e) => {
            const msg = backupCard.querySelector("#bkMsg");
            try {
                const r = await importBackup(e.target.files[0]);
                msg.style.color = "#2e7d4f";
                msg.textContent = `Restored ${r.restored} change(s)${r.skipped ? `; left ${r.skipped} alone (already on this device)` : ""}. They will sync when you're online.`;
                setTimeout(renderSyncStatus, 1500);
            } catch (err) { msg.style.color = "#b3261e"; msg.textContent = err.message; }
        });
        body.appendChild(backupCard);

        // Edits the server combined with, or replaced in favour of, another device's.
        const notices = [];
        for (const entity of ["scores", "attendance_records", "student_term_info", "students"]) {
            for (const r of await OfflineDB.getAll(schoolId, entity)) {
                if (r._sync && r._sync.outcome) notices.push({ entity, r });
            }
        }
        if (notices.length) {
            const card = el(`<div class="card"><h3>Combined with other devices</h3></div>`);
            for (const { entity, r } of notices.slice(0, 20)) {
                const what = r._sync.outcome === "merged" ? "Your change was combined with another device's change to different fields."
                    : "Another device had a more recent edit, so it was kept instead of yours.";
                const line = el(`<div style="border-top:1px solid #eee; padding:0.4rem 0; font-size:0.9rem;">${esc(recordLabel(entity, r, L))}<br><span style="color:#777;">${esc(what)}</span> </div>`);
                const ok = el(`<button class="btn btn-small" style="background:#888;">Dismiss</button>`);
                ok.addEventListener("click", async () => { delete r._sync.outcome; delete r._sync.note; delete r._sync.at; await OfflineDB.putRecord(schoolId, entity, r); renderSyncStatus(); });
                line.appendChild(ok);
                card.appendChild(line);
            }
            body.appendChild(card);
        }

        for (const entity of OfflineDB.ENTITY_STORES) {
            for (const status of ["pending", "failed", "conflict"]) {
                const rows = await OfflineDB.getByStatus(schoolId, entity, status);
                if (!rows.length) continue;
                const section = el(`<div class="card"><h3>${esc(entity)} — ${rows.length} ${esc(status)}</h3></div>`);
                for (const row of rows) {
                    const waitingOn = row._pending_refs
                        ? `Waiting on: ${Object.values(row._pending_refs).map((v) => v.split(":")[0]).join(", ")} to sync first`
                        : "";
                    const line = el(`<div style="border-top:1px solid #eee; padding:0.5rem 0;">
                        <b>${esc(recordLabel(entity, row, L))}</b>
                        ${waitingOn ? `<span style="color:#a97f22;"> — ${esc(waitingOn)}</span>` : ""}
                        ${row._sync.last_error ? `<div style="color:#b3261e; font-size:0.9rem;">${esc(row._sync.last_error)}</div>` : ""}
                    </div>`);
                    if (status === "conflict") {
                        const server = row._sync.server_data;
                        if (server) {
                            const keys = (row._sync.conflicting_fields && row._sync.conflicting_fields.length)
                                ? row._sync.conflicting_fields
                                : Object.keys(server).filter((k) => !metaKeys(k) && k !== "id" && k !== "updated_at" && k !== "client_uuid" && String(server[k] ?? "") !== String(row[k] ?? ""));
                            line.appendChild(el(`<table style="font-size:0.85rem; margin:0.4rem 0;"><thead><tr><th>Field</th><th>Yours</th><th>Server's</th></tr></thead><tbody>${
                                keys.map((k) => `<tr><td>${esc(k)}</td><td>${esc(row[k] ?? "")}</td><td>${esc(server[k] ?? "")}</td></tr>`).join("")}</tbody></table>`));
                        } else {
                            line.appendChild(el(`<div style="font-size:0.85rem; color:#777;">The server no longer has this record. "Keep mine" puts it back; "Keep server's" removes it here too.</div>`));
                        }
                        const keepMine = el(`<button class="btn btn-small">Keep mine</button>`);
                        const keepServer = el(`<button class="btn btn-small" style="background:#888;">Keep server's</button>`);
                        keepMine.addEventListener("click", async () => { await SyncEngine.resolveConflict(schoolId, entity, row.client_uuid, true); renderSyncStatus(); });
                        keepServer.addEventListener("click", async () => { await SyncEngine.resolveConflict(schoolId, entity, row.client_uuid, false); renderSyncStatus(); });
                        line.appendChild(keepMine);
                        line.appendChild(keepServer);
                    }
                    if (status === "failed") {
                        const retry = el(`<button class="btn btn-small">Try again</button>`);
                        retry.addEventListener("click", async () => {
                            row._sync = { ...row._sync, status: "pending", attempts: 0 };
                            delete row._sync.last_error;
                            await OfflineDB.putRecord(schoolId, entity, row);
                            renderSyncStatus();
                        });
                        line.appendChild(retry);
                    }
                    if (status === "failed" || status === "pending") {
                        const drop = el(`<button class="btn btn-small" style="background:#888; margin-left:0.3rem;">Discard this change</button>`);
                        drop.addEventListener("click", async () => {
                            if (!confirm("Discard this change? It hasn't reached the server and can't be recovered afterwards.")) return;
                            await SyncEngine.discardChange(schoolId, entity, row.client_uuid);
                            renderSyncStatus();
                        });
                        line.appendChild(drop);
                    }
                    section.appendChild(line);
                }
                body.appendChild(section);
            }
        }
        frame("Sync Status & Conflicts", body);
    }

    boot();
})();
