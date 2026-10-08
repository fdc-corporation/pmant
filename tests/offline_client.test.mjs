import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../static/offline/core.js", import.meta.url), "utf8");
const {acknowledge, appendEvent, elapsedSeconds, formatTime, syncFailureState, syncPayload} = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const order = () => ({id: 1, sheet_id: 8, token: "base", time_state: "new", sessions: [], events: [], plans: [], dirty_plans: []});
test("las pausas y la reapertura no agregan tiempo", () => {
    let item = order();
    for (const [action, at] of [["start", "09:00"], ["pause", "10:30"], ["resume", "11:00"], ["finish", "12:00"]]) {
        appendEvent(item, action, `2026-10-04T${at}:00Z`);
        item = JSON.parse(JSON.stringify(item));
    }
    assert.equal(formatTime(elapsedSeconds(item)), "02:30:00");
    assert.equal(elapsedSeconds(item, Date.parse("2026-10-05T00:00:00Z")), 9000);
});
test("finalizar en pausa conserva solo los tramos trabajados", () => {
    const item = order();
    appendEvent(item, "start", "2026-10-04T09:00:00Z");
    appendEvent(item, "pause", "2026-10-04T09:30:00Z");
    appendEvent(item, "finish", "2026-10-04T12:00:00Z");
    assert.equal(elapsedSeconds(item), 1800);
});
test("rechaza acciones repetidas, otro servicio activo y reloj atrasado", () => {
    const item = order();
    assert.throws(() => appendEvent(item, "resume", "2026-10-04T09:00:00Z"));
    assert.throws(() => appendEvent(item, "start", "2026-10-04T09:00:00Z", [{id: 2, time_state: "running"}]));
    appendEvent(item, "start", "2026-10-04T09:00:00Z");
    assert.throws(() => appendEvent(item, "pause", "2026-10-04T08:00:00Z"));
});
test("el envío queda congelado y solo contiene los informes modificados", () => {
    const item = order(); item.plans = [{id: 1, observations: "Borrador"}, {id: 2}]; item.dirty_plans = [1];
    item.pending = syncPayload(item, "operación");
    item.plans[0].observations = "Otro";
    assert.equal(item.pending.plans[0].observations, "Borrador");
    assert.equal(item.pending.plans.length, 1);
    appendEvent(item, "start", "2026-10-04T09:00:00Z");
    assert.equal(item.pending.events.length, 0);
});
test("continúa un inicio previo capturado por PMANT", () => {
    const item = order(); item.time_state = "running"; item.legacy_start = "2026-10-04T09:00:00Z";
    appendEvent(item, "pause", "2026-10-04T10:00:00Z");
    assert.equal(elapsedSeconds(item), 3600);
});
test("permite continuar sin señal mientras queda un envío sin confirmar", () => {
    const item = order(); item.plans = [{id: 1, observations: "Inicial", processes: []}]; item.dirty_plans = [1]; item.plan_versions = {1: 1};
    appendEvent(item, "start", "2026-10-04T09:00:00Z");
    item.pending = syncPayload(item, "operación"); item.pending_versions = {1: 1};
    appendEvent(item, "pause", "2026-10-04T10:30:00Z");
    appendEvent(item, "resume", "2026-10-04T11:00:00Z");
    item.plans[0].observations = "Editado durante el envío"; item.plan_versions[1]++;
    const received = {...order(), time_state: "running", token: "nuevo", sessions: [{start: "2026-10-04T09:00:00Z", end: null}], plans: [{id: 1, observations: "Inicial", processes: []}]};
    const merged = acknowledge(item, received);
    assert.equal(merged.events.length, 2);
    assert.equal(merged.time_state, "running");
    assert.equal(merged.plans[0].observations, "Editado durante el envío");
    assert.equal(formatTime(elapsedSeconds(merged, Date.parse("2026-10-04T12:00:00Z"))), "02:30:00");
    assert.equal(merged.token, "nuevo");
    assert.equal(merged.dirty, true);
});
test("solo exige comparar cuando PMANT informa un conflicto", () => {
    assert.deepEqual(syncFailureState({rejected: true, conflict: false}), {requiresReview: false, clearPending: true});
    assert.deepEqual(syncFailureState({rejected: true, conflict: true}), {requiresReview: true, clearPending: true});
    assert.deepEqual(syncFailureState(new TypeError("red interrumpida")), {requiresReview: false, clearPending: false});
});


