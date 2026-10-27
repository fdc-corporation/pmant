/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

const pmantNotifierService = {
    dependencies: ["notification", "action", "bus_service"],
    start(env) {
        const notification = env.services.notification;
        const action = env.services.action;
        const busService = env.services.bus_service;
        const seen = new Set();
        const POLL_DELAY = 30000;
        const HIDDEN_POLL_DELAY = 60000;
        let polling = false;
        let timerId;
        let audioContext;

        function primeAudio() {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) {
                return;
            }
            audioContext ||= new AudioContext();
            if (audioContext.state === "suspended") {
                audioContext.resume().catch(() => {});
            }
        }

        function playNotificationSound() {
            try {
                primeAudio();
                if (!audioContext || audioContext.state !== "running") {
                    return;
                }
                const oscillator = audioContext.createOscillator();
                const gain = audioContext.createGain();
                oscillator.type = "sine";
                oscillator.frequency.setValueAtTime(740, audioContext.currentTime);
                oscillator.frequency.exponentialRampToValueAtTime(1040, audioContext.currentTime + 0.12);
                gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.16, audioContext.currentTime + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.22);
                oscillator.connect(gain);
                gain.connect(audioContext.destination);
                oscillator.start();
                oscillator.stop(audioContext.currentTime + 0.23);
            } catch (error) {
                console.debug("pmant_notifier: el navegador bloqueó el sonido", error);
            }
        }

        function repairText(value) {
            if (typeof value !== "string" || !/[\u00c2\u00c3\u00e2]/.test(value)) {
                return value;
            }
            try {
                const bytes = Uint8Array.from(value, (character) => character.charCodeAt(0));
                return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
            } catch {
                return value;
            }
        }

        async function acknowledge(ids) {
            if (!ids.length) {
                return;
            }
            try {
                await rpc("/pmant/notify/ack", { ids });
            } catch (error) {
                console.warn("pmant_notifier: no se pudo confirmar la alerta", error);
            }
        }

        function showNotification(item) {
            if (!item?.id || seen.has(item.id)) {
                return false;
            }
            seen.add(item.id);
            const type = item.type || "info";
            const options = {
                title: repairText(item.title) || "Notificación PMANT",
                type,
                sticky: Boolean(item.sticky),
                className: `pmant-notification pmant-notification--${type}`,
            };
            if (item.res_model && item.res_id) {
                options.buttons = [{
                    name: "Ver registro",
                    icon: "fa-external-link",
                    primary: true,
                    onClick: () => action.doAction({
                        type: "ir.actions.act_window",
                        res_model: item.res_model,
                        res_id: item.res_id,
                        views: [[false, "form"]],
                        target: "current",
                    }),
                }];
            }
            notification.add(repairText(item.message), options);
            playNotificationSound();
            return true;
        }

        function scheduleNextPoll() {
            window.clearTimeout(timerId);
            timerId = window.setTimeout(
                poll,
                document.hidden ? HIDDEN_POLL_DELAY : POLL_DELAY
            );
        }

        async function poll() {
            if (polling) {
                return;
            }
            polling = true;
            try {
                const result = await rpc("/pmant/notify/poll", {});
                if (Array.isArray(result) && result.length) {
                    const ids = [];
                    for (const item of result) {
                        if (showNotification(item)) {
                            ids.push(item.id);
                        }
                    }
                    await acknowledge(ids);
                }
            } catch (error) {
                console.warn("pmant_notifier: error durante la consulta", error);
            } finally {
                polling = false;
                scheduleNextPoll();
            }
        }

        document.addEventListener("pointerdown", primeAudio, { once: true });
        busService.subscribe("pmant.notification", (item) => {
            if (showNotification(item)) {
                acknowledge([item.id]);
            }
        });
        busService.start();
        window.addEventListener("focus", poll);
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) {
                poll();
            }
        });
        poll();
    },
};

registry.category("services").add("pmant_core_notifier", pmantNotifierService);

