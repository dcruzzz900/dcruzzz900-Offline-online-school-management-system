/*
 * Learning materials saved for offline use.
 *
 * On the online Learning Materials page a teacher/admin taps "Save offline"
 * on a material; the file is fetched once and kept in Cache Storage under a
 * cache named for THAT school (srs-materials-<schoolId>). A small index entry
 * alongside it records the title/subject/type so the offline app can list
 * what's on the device without any network. Only materials someone has
 * explicitly saved are available offline — nothing is downloaded behind the
 * user's back, and a different school's materials are never listed because
 * each school has its own cache.
 */
const OfflineMaterials = (function () {
    const INDEX_KEY = "/__materials_index__";

    function cacheName(schoolId) {
        return `srs-materials-${schoolId}`;
    }

    async function readIndex(cache) {
        const hit = await cache.match(INDEX_KEY);
        if (!hit) return [];
        try { return await hit.json(); } catch (e) { return []; }
    }

    async function writeIndex(cache, list) {
        await cache.put(INDEX_KEY, new Response(JSON.stringify(list), { headers: { "Content-Type": "application/json" } }));
    }

    function fileUrl(id) {
        return `/materials/${id}/download`;
    }

    async function save(schoolId, meta) {
        if (!("caches" in self)) throw new Error("This browser can't save files for offline use.");
        const cache = await caches.open(cacheName(schoolId));
        const list = await readIndex(cache);
        let size = 0;
        if (!meta.external_url) {
            const res = await fetch(fileUrl(meta.id), { credentials: "same-origin" });
            if (!res.ok) throw new Error("Couldn't download that file (are you still logged in?).");
            const blob = await res.blob();
            size = blob.size;
            await cache.put(fileUrl(meta.id), new Response(blob, { headers: { "Content-Type": blob.type || "application/octet-stream" } }));
        }
        const entry = {
            id: meta.id, title: meta.title, kind: meta.kind, subject: meta.subject, class_name: meta.class_name,
            filename: meta.filename || null, external_url: meta.external_url || null, size, saved_at: new Date().toISOString(),
        };
        await writeIndex(cache, list.filter((x) => x.id !== meta.id).concat(entry));
        return entry;
    }

    async function list(schoolId) {
        if (!("caches" in self)) return [];
        const cache = await caches.open(cacheName(schoolId));
        return (await readIndex(cache)).sort((a, b) => String(a.title).localeCompare(String(b.title)));
    }

    async function isSaved(schoolId, id) {
        return (await list(schoolId)).some((x) => x.id === id);
    }

    async function remove(schoolId, id) {
        const cache = await caches.open(cacheName(schoolId));
        await cache.delete(fileUrl(id));
        await writeIndex(cache, (await readIndex(cache)).filter((x) => x.id !== id));
    }

    // Returns a Blob to open/download (or null for link-only entries).
    async function blobFor(schoolId, id) {
        const cache = await caches.open(cacheName(schoolId));
        const hit = await cache.match(fileUrl(id));
        return hit ? hit.blob() : null;
    }

    const api = { save, list, isSaved, remove, blobFor, cacheName };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    return api;
})();
