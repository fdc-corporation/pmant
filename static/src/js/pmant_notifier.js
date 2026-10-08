/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

const pmantNotifierService = {
    dependencies: ["notification"],
    start(env) {
        const notification = env.services.notification;
        const seen = new Set();
        const POLL_DELAY = 2000;
        const HIDDEN_POLL_DELAY = 10000;
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
                        if (seen.has(item.id)) {
                            continue;
                        }
                        seen.add(item.id);
                        notification.add(item.message, {
                            title: item.title || "Notificación PMANT",
                            type: item.type || "info",
                            sticky: Boolean(item.sticky),
                        });
                        playNotificationSound();
                        ids.push(item.id);
                    }
                    if (ids.length) {
                        await rpc("/pmant/notify/ack", { ids });
                    }
                }
            } catch (error) {
                console.warn("pmant_notifier: error durante la consulta", error);
            } finally {
                polling = false;
                scheduleNextPoll();
            }
        }

        document.addEventListener("pointerdown", primeAudio, { once: true });
        window.addEventListener("focus", poll);
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) {
                poll();
            }
        });
        poll();
    },
};

registry.category("services").add("pmant_notifier", pmantNotifierService);


