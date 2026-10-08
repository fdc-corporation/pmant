/** @odoo-module **/

import { Component, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class KdServiceTimer extends Component {
    static template = "pmant.ServiceTimer";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({ now: Date.now() });
        this.interval = setInterval(() => { this.state.now = Date.now(); }, 1000);
        onWillUnmount(() => clearInterval(this.interval));
    }

    get displayValue() {
        const started = this.props.record.data.kd_active_since;
        const accumulated = this.props.record.data.kd_elapsed_seconds || 0;
        if (!started) return this.formatSeconds(accumulated);
        const startedMs = typeof started.toMillis === "function" ? started.toMillis() : new Date(started).getTime();
        return this.formatSeconds(accumulated + Math.max(0, Math.floor((this.state.now - startedMs) / 1000)));
    }

    formatSeconds(value) {
        const seconds = Math.floor(value);
        const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
        const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
        return `${hours}:${minutes}:${String(seconds % 60).padStart(2, "0")}`;
    }
}

registry.category("fields").add("pmant_service_timer", { component: KdServiceTimer, supportedTypes: ["float"] });

