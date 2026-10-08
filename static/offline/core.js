export const clone = value => structuredClone(value);
export function elapsedSeconds(order, now = Date.now()) {
    const sessions = clone(order.sessions || []);
    if (!sessions.length && order.legacy_start) sessions.push({start: order.legacy_start, end: null});
    for (const event of order.events || []) {
        if (event.action === "start" || event.action === "resume") sessions.push({start: event.at, end: null});
        else {
            const active = sessions.findLast(item => !item.end);
            if (active) active.end = event.at;
        }
    }
    return sessions.reduce((sum, item) => sum + Math.max(0, ((item.end ? Date.parse(item.end) : now) - Date.parse(item.start)) / 1000), 0);
}
export function formatTime(value) {
    const seconds = Math.floor(value);
    return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60].map(item => String(item).padStart(2, "0")).join(":");
}
export function appendEvent(order, action, at, otherOrders = []) {
    const allowed = {start: ["new"], pause: ["running"], resume: ["paused"], finish: ["running", "paused"]};
    if (!allowed[action]?.includes(order.time_state)) throw new Error("La acción no corresponde al estado actual.");
    if (["start", "resume"].includes(action) && otherOrders.some(item => item.id !== order.id && item.time_state === "running")) throw new Error("Pause o finalice el otro servicio activo.");
    const last = order.events?.at(-1)?.at || order.sessions?.at(-1)?.end || order.sessions?.at(-1)?.start || order.legacy_start;
    if (!Number.isFinite(Date.parse(at)) || (last && Date.parse(at) < Date.parse(last))) throw new Error("El reloj retrocedió. Revise la fecha y hora del dispositivo.");
    if (action === "finish" && order.plans.some(plan => plan.file_mode && !plan.file && !plan.has_file)) throw new Error("Adjunte el informe técnico de los equipos que usan Subir informe.");
    order.events ||= [];
    order.events.push({action, at});
    order.time_state = {start: "running", pause: "paused", resume: "running", finish: "finished"}[action];
    order.dirty = true;
    order.ready = true;
}
export function syncPayload(order, operationId) {
    return {id: order.id, sheet_id: order.sheet_id, token: order.token, operation_id: operationId,
        events: clone(order.events || []), signature: clone(order.signature || {}),
        plans: clone(order.plans.filter(plan => order.dirty_plans?.includes(plan.id)))};
}
export function syncFailureState(error) {
    return {
        requiresReview: Boolean(error?.conflict),
        clearPending: Boolean(error?.rejected),
    };
}
export function acknowledge(order, snapshot) {
    const sent = order.pending;
    const remainingEvents = (order.events || []).slice(sent.events.length);
    const dirtyPlans = [];
    const plans = snapshot.plans.map(serverPlan => {
        const local = order.plans.find(plan => plan.id === serverPlan.id);
        const sentPlan = sent.plans.find(plan => plan.id === serverPlan.id);
        const changed = order.dirty_plans?.includes(serverPlan.id) && (!sentPlan || (order.plan_versions?.[serverPlan.id] || 0) !== (order.pending_versions?.[serverPlan.id] || 0));
        if (!changed) return clone(serverPlan);
        const merged = clone(local);
        if (sentPlan) {
            if (merged.file && merged.file === sentPlan.file) {delete merged.file; merged.has_file = serverPlan.has_file;}
            for (const process of merged.processes) {
                const submitted = sentPlan.processes.find(item => item.id === process.id)?.photos || [];
                process.photos = process.photos.filter(photo => !submitted.some(item => item.uid === photo.uid));
                process.photo_count = serverPlan.processes.find(item => item.id === process.id)?.photo_count || 0;
            }
        }
        dirtyPlans.push(serverPlan.id);
        return merged;
    });
    let state = snapshot.time_state;
    for (const event of remainingEvents) state = {start: "running", pause: "paused", resume: "running", finish: "finished"}[event.action];
    return {...clone(snapshot), plans, time_state: state, events: remainingEvents, dirty_plans: dirtyPlans,
        plan_versions: clone(order.plan_versions || {}), dirty: Boolean(remainingEvents.length || dirtyPlans.length),
        ready: Boolean(order.ready && (remainingEvents.length || dirtyPlans.length)), synced_at: new Date().toISOString()};
}

function openDatabase() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open("kd-pmant-offline-v1", 1);
        request.onupgradeneeded = () => request.result.createObjectStore("accounts", {keyPath: "key"});
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}
export async function accounts() {
    const db = await openDatabase();
    try {
        return await new Promise((resolve, reject) => {
            const request = db.transaction("accounts").objectStore("accounts").getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    } finally { db.close(); }
}
export async function deriveKey(password, salt) {
    const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
    return crypto.subtle.deriveKey({name: "PBKDF2", salt, iterations: 210000, hash: "SHA-256"}, material, {name: "AES-GCM", length: 256}, false, ["encrypt", "decrypt"]);
}
export async function decryptAccount(record, key) {
    const plain = await crypto.subtle.decrypt({name: "AES-GCM", iv: record.iv}, key, record.data);
    return JSON.parse(new TextDecoder().decode(plain));
}
export async function saveAccount(profile, key, data) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encrypted = await crypto.subtle.encrypt({name: "AES-GCM", iv}, key, new TextEncoder().encode(JSON.stringify(data)));
    const db = await openDatabase();
    try {
        await new Promise((resolve, reject) => {
            const tx = db.transaction("accounts", "readwrite");
            tx.objectStore("accounts").put({key: profile.key, name: profile.name, salt: profile.salt, iv, data: encrypted});
            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error || new Error("No se pudo guardar el informe."));
        });
    } finally { db.close(); }
}


