import {accounts, acknowledge, appendEvent, clone, decryptAccount, deriveKey, elapsedSeconds, formatTime, saveAccount, syncFailureState, syncPayload} from "./core.js";

const $ = id => document.getElementById(id);
const labels = {new: "Sin iniciar", running: "En curso", paused: "Pausado", finished: "Finalizado"};
let profile, encryptionKey, data, selected, identity, busy = false, online = false, lastActivity = Date.now();
let queue = Promise.resolve(), releaseLock, reviewOrder;
let unsaved = false, saving = 0, shellReady = false;

function notice(text) { $("message").textContent = text; }
function node(tag, text, attributes = {}) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    Object.assign(element, attributes);
    return element;
}
function button(text, action, disabled = false) {
    const element = node("button", text, {type: "button", disabled});
    element.addEventListener("click", () => Promise.resolve().then(action).catch(error => notice(error.message)));
    return element;
}
function connection() {
    $("connection").textContent = online ? "Vinculado con PMANT · Puede descargar y sincronizar" : "Sin conexión con PMANT · Puede seguir trabajando con las órdenes descargadas";
    $("connection").classList.toggle("offline", !online);
}
async function api(action, payload) {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), action === "sync" ? 90000 : 12000);
    try {
        const response = await fetch("/pmant/offline/api", {method: "POST", credentials: "same-origin", cache: "no-store",
            headers: {"Content-Type": "application/json"}, signal: abort.signal,
            body: JSON.stringify({jsonrpc: "2.0", method: "call", params: {action, payload}, id: crypto.randomUUID()})});
        if (!response.ok) throw new Error("PMANT no respondió. El trabajo permanece en el dispositivo.");
        const result = await response.json();
        if (result.error) throw new Error(result.error.data?.message || "La sesión de PMANT venció. Inicie sesión para sincronizar.");
        if (result.result?.error) {
            const error = new Error(result.result.error);
            error.rejected = result.result.rejected;
            error.conflict = result.result.conflict;
            throw error;
        }
        online = true; connection();
        return result.result;
    } catch (error) {
        if (error.name === "AbortError" || error instanceof TypeError) {
            online = false; connection();
            throw new Error("No se pudo contactar con PMANT. Su trabajo sigue guardado en este dispositivo.");
        }
        throw error;
    } finally { clearTimeout(timeout); }
}
function mutate(change, render = true) {
    saving++;
    const operation = queue.then(async () => {
        if (!data || !encryptionKey) throw new Error("Abra su cuenta local para guardar.");
        const next = clone(data);
        change(next);
        next.saved_at = new Date().toISOString();
        try { await saveAccount(profile, encryptionKey, next); }
        catch (error) {
            data = next; unsaved = true;
            throw new Error("No se pudo guardar en el dispositivo. Revise el espacio disponible; no cierre la pantalla hasta guardar o exportar su trabajo.");
        }
        data = next;
        unsaved = false;
        $("last-save").textContent = `Guardado en este dispositivo a las ${new Date(data.saved_at).toLocaleTimeString("es-PE")}`;
        renderWorkspace(render);
        if ($("ready")) $("ready").disabled = Boolean(data.orders.find(item => item.id === selected)?.pending) || !data.orders.find(item => item.id === selected)?.dirty;
    }).finally(() => {saving--;});
    queue = operation.catch(error => notice(error.message));
    return operation;
}
async function checkIdentity() {
    const current = await api("identity");
    if (profile && current.key !== profile.key) {
        await lock();
        throw new Error("PMANT tiene otra cuenta abierta. Sus borradores están protegidos; ingrese con la cuenta correspondiente.");
    }
    identity = current;
    return current;
}
async function refreshProfiles() {
    const stored = await accounts();
    const options = new Map(stored.map(item => [item.key, item]));
    if (identity && !options.has(identity.key)) options.set(identity.key, identity);
    $("profiles").replaceChildren();
    for (const item of options.values()) $("profiles").append(node("option", item.name, {value: item.key}));
    if (identity) $("profiles").value = identity.key;
    $("unlock").hidden = !options.size;
    $("login-link").hidden = Boolean(identity);
    const help = () => {
        const exists = stored.some(item => item.key === $("profiles").value);
        $("pin-help").textContent = exists ? "Escriba la clave de protección que creó para este dispositivo. No es su contraseña de PMANT." : "Cree una clave de al menos 6 caracteres. No es su contraseña de PMANT; protege los informes si pierde el dispositivo.";
    };
    $("profiles").onchange = help;
    help();
}
async function acquireLocalLock(key) {
    if (!navigator.locks) throw new Error("Este navegador no permite proteger el trabajo entre pestañas. Use un navegador actualizado.");
    await new Promise((resolve, reject) => {
        navigator.locks.request(`kd-pmant:${key}`, {ifAvailable: true}, async lockHandle => {
            if (!lockHandle) { reject(new Error("Su cuenta ya está abierta en otra pestaña. Bloquéela allí antes de continuar.")); return; }
            await new Promise(release => { releaseLock = release; resolve(); });
        }).catch(reject);
    });
}
$("unlock").addEventListener("submit", async event => {
    event.preventDefault();
    const submit = event.submitter; submit.disabled = true;
    try {
        const accountKey = $("profiles").value;
        const password = $("pin").value;
        if (password.length < 6) throw new Error("Use al menos 6 caracteres para su clave local.");
        if (online && identity?.key !== accountKey) throw new Error("Inicie sesión en PMANT con esta cuenta antes de abrirla con conexión.");
        await acquireLocalLock(accountKey);
        const stored = (await accounts()).find(item => item.key === accountKey);
        const salt = stored?.salt || crypto.getRandomValues(new Uint8Array(16));
        const key = await deriveKey(password, salt);
        let local;
        if (stored) {
            try { local = await decryptAccount(stored, key); }
            catch { throw new Error("La clave local no es correcta. No se modificó ningún borrador."); }
        } else {
            if (!online || identity?.key !== accountKey) throw new Error("Necesita conexión para preparar una cuenta por primera vez.");
            local = {orders: [], states: [], history: [], saved_at: null};
        }
        for (const order of local.orders || []) {
            const oldConflict = /cambi(ó|aron)|programación cambió|versión actual/i.test(order.error || "");
            if (order.requires_review && !oldConflict) order.requires_review = false;
        }
        profile = {key: accountKey, name: stored?.name || identity.name, salt};
        encryptionKey = key; data = local;
        await saveAccount(profile, encryptionKey, data);
        $("pin").value = ""; $("access").hidden = true; $("workspace").hidden = false; $("lock").hidden = false;
        $("user").textContent = profile.name;
        notice(online ? "Dispositivo vinculado con PMANT. Descargando sus órdenes…" : "Dispositivo abierto. Puede trabajar con las órdenes ya descargadas.");
        lastActivity = Date.now(); renderWorkspace();
        if (navigator.storage?.persist) await navigator.storage.persist();
        if (online && !stored) await download();
    } catch (error) {
        if (!data) { releaseLock?.(); releaseLock = undefined; }
        notice(error.message);
    } finally { submit.disabled = false; }
});
async function lock() {
    await queue;
    if (unsaved) throw new Error("Hay cambios que no se pudieron guardar. Exporte el respaldo o libere espacio antes de bloquear.");
    data = undefined; encryptionKey = undefined; profile = undefined; selected = undefined;
    reviewOrder = undefined;
    $("review").close(); $("local-version").textContent = ""; $("server-version").textContent = "";
    $("orders").replaceChildren(); $("editor").replaceChildren(); $("workspace").hidden = true; $("access").hidden = false; $("lock").hidden = true;
    releaseLock?.(); releaseLock = undefined;
    await refreshProfiles();
}
$("lock").addEventListener("click", () => lock().catch(error => notice(error.message)));

async function download() {
    if (busy) return;
    if (!shellReady) throw new Error("La interfaz todavía no está preparada para abrir sin conexión. Vuelva a cargar esta pantalla con internet.");
    busy = true;
    try {
        await checkIdentity();
        const downloaded = await api("download");
        await mutate(next => {
            const dirty = new Set(next.orders.filter(item => item.dirty || item.pending).map(item => item.id));
            const preserved = next.orders.filter(item => dirty.has(item.id) || item.time_state === "finished");
            for (const order of downloaded.orders) {
                if (dirty.has(order.id)) continue;
                const index = preserved.findIndex(item => item.id === order.id);
                if (index >= 0) preserved.splice(index, 1);
                preserved.push({...order, events: [], dirty_plans: [], dirty: false, ready: false});
            }
            next.orders = preserved;
            next.states = downloaded.states;
        });
        notice(`Descarga completada: ${downloaded.orders.length} órdenes. Se conservaron los borradores pendientes.`);
    } finally { busy = false; }
}
function renderWorkspace(updateEditor = true) {
    if (!data) return;
    $("work-area").classList.toggle("has-selection", Boolean(selected));
    $("orders").replaceChildren();
    const query = ($("order-search").value || "").trim().toLocaleLowerCase("es");
    const visibleOrders = data.orders.filter(order => [order.name, order.site, order.stage, labels[order.time_state], ...order.plans.map(item => item.equipment)]
        .filter(Boolean).join(" ").toLocaleLowerCase("es").includes(query));
    $("order-count").textContent = query ? `${visibleOrders.length} de ${data.orders.length}` : `${data.orders.length} ${data.orders.length === 1 ? "orden" : "órdenes"}`;
    if (!data.orders.length) $("orders").append(node("div", "Todavía no hay órdenes descargadas. Use “Descargar órdenes” antes de salir.", {className: "empty-state"}));
    else if (!visibleOrders.length) $("orders").append(node("div", "No hay órdenes que coincidan con la búsqueda.", {className: "empty-state"}));
    for (const order of visibleOrders) {
        const card = node("section", undefined, {className: `card${selected === order.id ? " selected" : ""}`});
        const heading = node("div", undefined, {className: "card-heading"});
        const title = node("div"); title.append(node("span", "Orden de trabajo", {className: "eyebrow"}), node("h2", order.name));
        heading.append(title, node("span", labels[order.time_state], {className: `badge time-${order.time_state}`}));
        card.append(heading, node("p", `⌖ ${order.site}`, {className: "site"}));
        const status = order.requires_review ? "Requiere comparar cambios" : order.error ? "No se pudo enviar · Corrija e intente nuevamente" : order.pending || order.dirty ? "Pendiente de sincronizar" : order.synced_at ? "Recibida por PMANT" : "Disponible sin conexión";
        const metadata = node("div", undefined, {className: "card-meta"});
        metadata.append(node("span", `Etapa: ${order.stage || "Sin etapa"}`), node("span", `${order.plans.length} ${order.plans.length === 1 ? "equipo" : "equipos"}`));
        const equipment = node("p", undefined, {className: "equipment"}); equipment.append(node("strong", "Equipos: "), document.createTextNode(order.plans.map(item => item.equipment).join(" · ") || "Sin equipos"));
        const footer = node("div", undefined, {className: "card-footer"});
        footer.append(node("span", status, {className: `sync-status${order.requires_review || order.error ? " warning" : ""}`}), button(order.error ? "Corregir informe  →" : "Completar informe  →", () => { selected = order.id; renderWorkspace(false); renderEditor(); $("editor").scrollIntoView({behavior: "smooth", block: "start"}); }));
        if (order.requires_review) footer.append(button("Revisar cambios", () => review(order.id)));
        card.append(metadata, equipment, footer);
        $("orders").append(card);
    }
    if (selected && updateEditor) renderEditor();
}
function textField(parent, label, value, change, disabled = false) {
    const wrapper = node("label", label);
    const input = node("textarea", undefined, {value: value || "", disabled});
    input.addEventListener("input", () => { const value = input.value; change(value).catch(error => notice(error.message)); });
    wrapper.append(input); parent.append(wrapper);
}
function editPlan(orderId, planId, change, render = false) {
    return mutate(next => {
        const order = next.orders.find(item => item.id === orderId);
        change(order.plans.find(item => item.id === planId));
        order.error = null;
        order.plan_versions ||= {};
        order.plan_versions[planId] = (order.plan_versions[planId] || 0) + 1;
        order.dirty_plans ||= [];
        if (!order.dirty_plans.includes(planId)) order.dirty_plans.push(planId);
        order.dirty = true;
    }, render);
}
function editSignature(orderId, change, render = false) {
    return mutate(next => {
        const order = next.orders.find(item => item.id === orderId);
        order.signature ||= {data: "", name: "", document: "", comment: ""};
        change(order.signature);
        order.error = null;
        order.dirty = true;
    }, render);
}
function signatureField(parent, label, value, change, disabled = false) {
    const wrapper = node("label", label);
    const input = node("input", undefined, {type: "text", value: value || "", disabled});
    input.addEventListener("input", () => change(input.value).catch(error => notice(error.message)));
    wrapper.append(input); parent.append(wrapper);
}
function renderCustomerSignature(editor, order, frozen) {
    const signature = order.signature || {data: "", name: "", document: "", comment: ""};
    const section = node("section", undefined, {className: "signature-section"});
    const heading = node("div", undefined, {className: "section-title"});
    heading.append(node("span", "03", {className: "section-number"}), node("div"));
    heading.lastChild.append(node("h3", "Firma del cliente"), node("p", "Solicite al cliente firmar dentro del recuadro para confirmar el informe."));
    section.append(heading);
    const fields = node("div", undefined, {className: "signature-fields"});
    signatureField(fields, "Nombre del firmante", signature.name, value => editSignature(order.id, item => {item.name = value;}), frozen);
    signatureField(fields, "DNI / Documento", signature.document, value => editSignature(order.id, item => {item.document = value;}), frozen);
    section.append(fields);
    const pad = node("div", undefined, {className: "signature-pad"});
    const canvas = node("canvas", undefined, {width: 900, height: 260});
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff"; context.fillRect(0, 0, canvas.width, canvas.height);
    if (signature.data) { const image = new Image(); image.onload = () => context.drawImage(image, 0, 0, canvas.width, canvas.height); image.src = `data:image/png;base64,${signature.data}`; }
    let drawing = false;
    const point = event => { const rect = canvas.getBoundingClientRect(); return [(event.clientX - rect.left) * canvas.width / rect.width, (event.clientY - rect.top) * canvas.height / rect.height]; };
    canvas.addEventListener("pointerdown", event => { if (frozen) return; drawing = true; canvas.setPointerCapture(event.pointerId); context.beginPath(); context.moveTo(...point(event)); });
    canvas.addEventListener("pointermove", event => { if (!drawing) return; context.lineWidth = 4; context.lineCap = "round"; context.strokeStyle = "#10213a"; context.lineTo(...point(event)); context.stroke(); });
    const finish = () => { if (!drawing) return; drawing = false; editSignature(order.id, item => {item.data = canvas.toDataURL("image/png").split(",")[1];}, true).catch(error => notice(error.message)); };
    canvas.addEventListener("pointerup", finish); canvas.addEventListener("pointercancel", finish);
    pad.append(canvas, node("span", "Firme aquí", {className: "signature-hint"})); section.append(pad);
    if (!frozen) section.append(button("Limpiar firma", async () => { await editSignature(order.id, item => {item.data = "";}, true); }));
    textField(section, "Comentario del firmante", signature.comment, value => editSignature(order.id, item => {item.comment = value;}), frozen);
    editor.append(section);
}
function renderEditor() {
    const order = data?.orders.find(item => item.id === selected);
    const editor = $("editor"); editor.replaceChildren(); editor.hidden = !order;
    if (!order) return;
    $("work-area").classList.add("has-selection");
    const frozen = order.time_state === "finished" && (Boolean(order.pending) || !order.error);
    const editorHead = node("div", undefined, {className: "editor-head"});
    const editorTitle = node("div"); editorTitle.append(node("span", "Informe técnico", {className: "eyebrow"}), node("h2", order.name), node("p", order.site, {className: "site"}));
    const clock = node("div", undefined, {className: "clock"}); clock.append(node("span", labels[order.time_state], {className: `badge time-${order.time_state}`}), node("div", formatTime(elapsedSeconds(order)), {className: "timer", id: "timer"}));
    editorHead.append(editorTitle, clock); editor.append(editorHead);
    if (order.error) editor.append(node("p", order.requires_review
        ? `PMANT detectó cambios en esta orden: ${order.error}`
        : `El informe todavía no fue recibido por PMANT: ${order.error}`, {className: "sync-error", role: "alert"}));
    const actions = node("div", undefined, {className: "actions"});
    for (const [action, text, states] of [["start", "Iniciar servicio", ["new"]], ["pause", "Pausar", ["running"]], ["resume", "Reanudar", ["paused"]], ["finish", "Finalizar servicio", ["running", "paused"]]]) {
        if (!states.includes(order.time_state)) continue;
        actions.append(button(text, async () => {
            if (action === "finish" && !confirm("¿Finalizar el servicio y dejar el informe listo para revisión? Revise los datos y adjuntos antes de continuar.")) return;
            await mutate(next => appendEvent(next.orders.find(item => item.id === order.id), action, new Date().toISOString(), next.orders));
            if (online) await synchronize();
        }, !order.sheet_id));
    }
    editor.append(actions, node("p", "Las pausas no se suman a las horas trabajadas. El cronómetro continúa aunque cierre la aplicación.", {className: "muted"}));
    const history = node("details"); history.append(node("summary", "Marcas de tiempo"));
    const dateText = value => new Date(value).toLocaleString("es-PE");
    for (const session of order.sessions || []) history.append(node("p", `Tramo: ${dateText(session.start)} → ${session.end ? dateText(session.end) : "En curso"}`));
    if (order.legacy_start) history.append(node("p", `Inicio previo: ${dateText(order.legacy_start)}`));
    const eventLabels = {start: "Inicio", pause: "Pausa", resume: "Reanudación", finish: "Finalización"};
    for (const event of order.events || []) history.append(node("p", `${eventLabels[event.action]}: ${dateText(event.at)} · Pendiente de sincronizar`));
    editor.append(history);
    if (!order.sheet_id) editor.append(node("p", "Esta orden no tiene una hoja de horas programada. Solicite su programación antes de iniciar."));
    if (order.pending) editor.append(node("p", "PMANT todavía no confirmó este envío. Se reintentará automáticamente; puede seguir trabajando y los nuevos cambios se conservarán por separado."));
    for (const plan of order.plans) {
        const panel = node("details", undefined, {open: true, className: "equipment-panel"}); panel.append(node("summary", plan.equipment));
        const processTitle = node("div", undefined, {className: "section-title"}); processTitle.append(node("span", "01", {className: "section-number"}), node("div"));
        processTitle.lastChild.append(node("h3", "Procesos realizados"), node("p", "Registre el resultado, comentarios y evidencias de cada proceso.")); panel.append(processTitle);
        for (const process of plan.processes) {
            const block = node("div", undefined, {className: "process"});
            block.append(node("span", "PROCESO", {className: "process-label"}), node("h3", process.name), node("p", process.instructions || "Sin descripción del proceso.", {className: "process-description"}));
            const resultLabel = node("label", "Resultado");
            const result = node("select", undefined, {disabled: frozen});
            result.append(node("option", "Sin resultado", {value: ""}));
            for (const state of data.states) result.append(node("option", state.name, {value: String(state.id)}));
            result.value = process.state_id ? String(process.state_id) : "";
            result.addEventListener("change", () => { const stateId = Number(result.value) || false; editPlan(order.id, plan.id, item => {item.processes.find(entry => entry.id === process.id).state_id = stateId;}).catch(error => notice(error.message)); });
            resultLabel.append(result); block.append(resultLabel);
            textField(block, "Comentarios", process.comment, value => editPlan(order.id, plan.id, item => {item.processes.find(entry => entry.id === process.id).comment = value;}), frozen);
            block.append(node("p", `Evidencias existentes en PMANT: ${process.photo_count || 0}. Las nuevas fotos se guardan en este dispositivo.`, {className: "muted"}));
            for (const attachment of process.existing_photos || []) {
                const saved = node("div", undefined, {className: "saved-photo"});
                saved.append(node("strong", attachment.name), node("p", `Comentario del adjunto: ${attachment.comment || "Sin comentario"}`));
                block.append(saved);
            }
            const cameraLabel = node("label", "Agregar fotografías");
            const camera = node("input", undefined, {type: "file", accept: "image/jpeg,image/png,image/webp", multiple: true, disabled: frozen});
            camera.setAttribute("capture", "environment");
            camera.addEventListener("change", async () => {
                try {
                    const photos = [];
                    for (const file of camera.files) photos.push({uid: crypto.randomUUID(), name: file.name, data: await photoFile(file), comment: ""});
                    await editPlan(order.id, plan.id, item => item.processes.find(entry => entry.id === process.id).photos.push(...photos), true);
                } catch (error) { notice(error.message); }
            });
            cameraLabel.append(camera); block.append(cameraLabel);
            const photos = node("div", undefined, {className: "photos"});
            process.photos.forEach((photo, index) => {
                const figure = node("figure"); figure.append(node("img", undefined, {src: `data:image/jpeg;base64,${photo.data}`, alt: photo.name}));
                const commentLabel = node("label", "Comentario del adjunto");
                const comment = node("textarea", undefined, {value: photo.comment, placeholder: "Describa lo que muestra esta fotografía", disabled: frozen});
                comment.setAttribute("aria-label", "Comentario del adjunto");
                comment.addEventListener("input", () => { const value = comment.value; editPlan(order.id, plan.id, item => {item.processes.find(entry => entry.id === process.id).photos[index].comment = value;}).catch(error => notice(error.message)); });
                commentLabel.append(comment);
                figure.append(node("figcaption", photo.name), commentLabel, button("Quitar", () => editPlan(order.id, plan.id, item => item.processes.find(entry => entry.id === process.id).photos.splice(index, 1), true), frozen)); photos.append(figure);
            });
            block.append(photos); panel.append(block);
        }
        const conclusionTitle = node("div", undefined, {className: "section-title"}); conclusionTitle.append(node("span", "02", {className: "section-number"}), node("div"));
        conclusionTitle.lastChild.append(node("h3", "Conclusiones y recomendaciones"), node("p", "Complete el resultado general del trabajo realizado.")); panel.append(conclusionTitle);
        for (const [field, title] of [["conclusions", "Conclusiones"], ["recommendations", "Recomendaciones"]]) {
            textField(panel, title, plan[field], value => editPlan(order.id, plan.id, item => {item[field] = value;}), frozen);
        }
        const modeLabel = node("label", undefined, {className: "toggle-field"});
        const mode = node("input", undefined, {type: "checkbox", checked: plan.file_mode, disabled: frozen});
        mode.addEventListener("change", () => editPlan(order.id, plan.id, item => {item.file_mode = mode.checked;}, true).catch(error => notice(error.message)));
        modeLabel.append(mode, node("span", "Subir informe como archivo")); panel.append(modeLabel);
        if (plan.file_mode) {
            panel.append(node("p", plan.filename ? `Informe: ${plan.filename}${plan.file ? " · Guardado localmente" : " · Ya adjunto en PMANT"}` : "Adjunte el informe técnico (máximo 15 MB)."));
            const file = node("input", undefined, {type: "file", disabled: frozen});
            file.addEventListener("change", async () => {
                try { const attachment = file.files[0]; if (!attachment) return; const encoded = await readFile(attachment); await editPlan(order.id, plan.id, item => {item.file = encoded; item.filename = attachment.name;}, true); }
                catch (error) { notice(error.message); }
            });
            panel.append(file);
        }
        editor.append(panel);
    }
    renderCustomerSignature(editor, order, frozen);
    const finalActions = node("div", undefined, {className: "final-actions"});
    finalActions.append(button("Guardar como borrador", async () => { await queue; await mutate(() => {}, false); notice("Borrador guardado en este dispositivo."); }));
    const readyButton = button("Enviar informe a PMANT", async () => {
        const current = data.orders.find(item => item.id === order.id);
        if (!current.signature?.data || !current.signature?.name?.trim()) throw new Error("Capture la firma y el nombre del cliente antes de enviar el informe.");
        await mutate(next => { const item = next.orders.find(item => item.id === order.id); item.ready = true; });
        notice(online ? "Enviando informe a PMANT…" : "Informe listo. Se enviará automáticamente al recuperar conexión.");
        if (online) await synchronize();
    }, Boolean(order.pending) || !order.dirty);
    readyButton.id = "ready";
    finalActions.append(readyButton); editor.append(finalActions);
}

$("order-search").addEventListener("input", () => { $("clear-search").hidden = !$("order-search").value; renderWorkspace(false); });
$("clear-search").addEventListener("click", () => { $("order-search").value = ""; $("clear-search").hidden = true; renderWorkspace(false); $("order-search").focus(); });
function readFile(file) {
    if (!file.size || file.size > 15 * 1024 * 1024) throw new Error("El archivo debe tener contenido y no superar los 15 MB.");
    return new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(",")[1]); reader.onerror = () => reject(new Error("No se pudo leer el archivo.")); reader.readAsDataURL(file);
    });
}
async function photoFile(file) {
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) throw new Error("Use fotografías JPG, PNG o WEBP.");
    if (file.size > 15 * 1024 * 1024) throw new Error("La fotografía supera los 15 MB.");
    const bitmap = await createImageBitmap(file);
    try {
        const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement("canvas"); canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
        canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.82).split(",")[1];
    } finally { bitmap.close(); }
}
async function synchronize(automatic = false) {
    if (!data || busy) return;
    busy = true;
    let sent = 0;
    try {
        await queue; await checkIdentity();
        const ids = data.orders.filter(order => order.pending || (order.dirty && (!automatic || order.ready))).filter(order => !automatic || !order.requires_review).map(order => order.id);
        for (const id of ids) {
            if (!data) break;
            let order = data.orders.find(item => item.id === id);
            if (!order.pending) {
                const payload = syncPayload(order, crypto.randomUUID());
                if (new TextEncoder().encode(JSON.stringify(payload)).length > 38 * 1024 * 1024) { notice("El informe supera el tamaño máximo de envío. Reduzca las fotografías o el archivo adjunto."); continue; }
                await mutate(next => {
                    const item = next.orders.find(item => item.id === id);
                    item.pending = payload; item.pending_versions = clone(item.plan_versions || {});
                });
                order = data.orders.find(item => item.id === id);
            }
            const accountKey = profile.key;
            try {
                const received = await api("sync", order.pending);
                if (!data || profile.key !== accountKey) break;
                await mutate(next => {
                    const index = next.orders.findIndex(item => item.id === id);
                    next.orders[index] = acknowledge(next.orders[index], received.order);
                });
                sent++;
            } catch (error) {
                const failure = syncFailureState(error);
                if (data && profile.key === accountKey) await mutate(next => {
                    const item = next.orders.find(item => item.id === id);
                    item.error = error.message;
                    item.requires_review = failure.requiresReview;
                    if (failure.clearPending) {item.pending = null; item.ready = false;}
                });
                notice(error.message);
                if (!online) break;
            }
        }
        if (sent) notice(`${sent} informe(s) confirmado(s) por PMANT. Las horas y fotografías se registraron sin duplicados.`);
        else if (!ids.length && !automatic) notice("No hay cambios pendientes de sincronizar.");
    } finally {
        busy = false;
        if (sent && data?.orders.some(order => order.dirty && order.ready && !order.requires_review)) setTimeout(() => synchronize(true).catch(error => notice(error.message)), 0);
    }
}
function versionText(order) {
    return JSON.stringify({orden: order.name, etapa: order.stage, estado_tiempo: labels[order.time_state], horas: formatTime(elapsedSeconds(order)), marcas: order.events || [], equipos: order.plans.map(plan => ({equipo: plan.equipment, observaciones: plan.observations, conclusiones: plan.conclusions, recomendaciones: plan.recommendations, archivo: plan.filename, procesos: plan.processes.map(process => ({proceso: process.name, resultado: data.states.find(state => state.id === process.state_id)?.name || "Sin resultado", comentario: process.comment, fotos_nuevas: process.photos.length}))}))}, null, 2);
}
async function review(id) {
    await checkIdentity();
    const current = await api("review", {id});
    const local = data.orders.find(item => item.id === id);
    reviewOrder = {local: clone(local), server: current.order};
    $("local-version").textContent = versionText(local); $("server-version").textContent = versionText(current.order); $("review").showModal();
}
$("keep-draft").addEventListener("click", () => {$("review").close(); reviewOrder = undefined;});
$("restore-server").addEventListener("click", async () => {
    try {
        if (!reviewOrder || !confirm("Se archivará una copia completa de su borrador local y se abrirá la versión de PMANT. Podrá exportar el borrador archivado como respaldo. ¿Continuar?")) return;
        const {local, server} = reviewOrder;
        await mutate(next => {
            next.history.push({archived_at: new Date().toISOString(), order: local});
            next.orders[next.orders.findIndex(item => item.id === local.id)] = {...server, events: [], dirty_plans: [], dirty: false, ready: false};
        });
        $("review").close(); reviewOrder = undefined; notice("Borrador archivado. La versión actual de PMANT está disponible.");
    } catch (error) { notice(error.message); }
});
function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob); const anchor = node("a", undefined, {href: url, download: filename}); anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("export").addEventListener("click", async () => {
    try {
        await queue;
        if (!data) return;
        if (!confirm("El respaldo contendrá informes y fotografías en un archivo sin cifrar. Guárdelo en un lugar protegido. ¿Exportar?")) return;
        downloadBlob(new Blob([JSON.stringify({format: "moubrix-offline-backup-v1", account: profile.key, ...data}, null, 2)], {type: "application/json"}), `moubrix-respaldo-${new Date().toISOString().slice(0,10)}.json`);
    } catch (error) { notice(error.message); }
});
$("download").addEventListener("click", () => download().catch(error => notice(error.message)));
$("sync").addEventListener("click", () => synchronize().catch(error => notice(error.message)));
for (const event of ["pointerdown", "keydown", "input"]) document.addEventListener(event, () => {lastActivity = Date.now();});
window.addEventListener("offline", () => {online = false; connection();});
window.addEventListener("online", () => {if (data) synchronize(true).catch(error => notice(error.message));});
window.addEventListener("beforeunload", event => {if (busy || saving || unsaved) {event.preventDefault(); event.returnValue = "";}});
setInterval(() => {
    if (data && selected && $("timer")) $("timer").textContent = formatTime(elapsedSeconds(data.orders.find(item => item.id === selected)));
    if (data && !unsaved && Date.now() - lastActivity > 15 * 60 * 1000) lock().then(() => notice("Cuenta bloqueada por inactividad. Sus tiempos y borradores se conservan.")).catch(error => notice(error.message));
}, 1000);
setInterval(() => {if (data && navigator.onLine && !busy) synchronize(true).catch(() => {});}, 30000);

async function boot() {
    if (!window.isSecureContext || !crypto.subtle || !window.indexedDB) {
        $("unlock").hidden = true;
        throw new Error("El modo offline necesita HTTPS (o localhost), almacenamiento local y un navegador actualizado.");
    }
    if ("serviceWorker" in navigator) {
        try {
            await navigator.serviceWorker.register("/pmant/offline/sw.js", {scope: "/pmant/offline"});
            await Promise.race([navigator.serviceWorker.ready, new Promise((_, reject) => setTimeout(() => reject(new Error("Tiempo de preparación agotado")), 15000))]);
            shellReady = true;
        }
        catch { notice("No se pudo preparar la apertura sin conexión. Revise HTTPS y vuelva a abrir esta pantalla antes de salir."); }
    }
    try { identity = await api("identity"); } catch { online = false; connection(); }
    await refreshProfiles();
}
boot().catch(error => notice(error.message));


