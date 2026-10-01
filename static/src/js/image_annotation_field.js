/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ImageField, imageField } from "@web/views/fields/image/image_field";
import { Component, onMounted, useRef, useState } from "@odoo/owl";

export class ImageAnnotationDialog extends Component {
    static template = "pmant.ImageAnnotationDialog";
    static components = { Dialog };
    static props = ["close", "imageUrl", "onSave"];

    setup() {
        this.canvasRef = useRef("canvas");
        this.state = useState({
            tool: "pencil",
            color: "#ff0000",
            width: 4,
            loading: true,
            loadError: false,
            historyCount: 0,
        });
        this.history = [];
        this.drawing = false;
        this.startPoint = null;
        this.snapshot = null;
        onMounted(() => this.loadImage());
    }

    get canvas() {
        return this.canvasRef.el;
    }

    get context() {
        return this.canvas.getContext("2d");
    }

    loadImage() {
        const image = new Image();
        image.onload = () => {
            this.canvas.width = image.naturalWidth;
            this.canvas.height = image.naturalHeight;
            this.context.drawImage(image, 0, 0);
            this.original = this.context.getImageData(0, 0, this.canvas.width, this.canvas.height);
            this.state.loading = false;
        };
        image.onerror = () => {
            this.state.loading = false;
            this.state.loadError = true;
        };
        image.src = this.props.imageUrl;
    }

    setTool(tool) {
        this.state.tool = tool;
    }

    point(event) {
        const rect = this.canvas.getBoundingClientRect();
        return {
            x: (event.clientX - rect.left) * (this.canvas.width / rect.width),
            y: (event.clientY - rect.top) * (this.canvas.height / rect.height),
        };
    }

    pointerDown(event) {
        if (this.state.loading) return;
        event.preventDefault();
        this.canvas.setPointerCapture(event.pointerId);
        this.drawing = true;
        this.startPoint = this.point(event);
        this.snapshot = this.context.getImageData(0, 0, this.canvas.width, this.canvas.height);
        this.history.push(this.snapshot);
        this.state.historyCount = this.history.length;
        if (this.state.tool === "pencil") {
            this.prepareContext();
            this.context.beginPath();
            this.context.moveTo(this.startPoint.x, this.startPoint.y);
        }
    }

    pointerMove(event) {
        if (!this.drawing) return;
        event.preventDefault();
        const current = this.point(event);
        this.prepareContext();
        if (this.state.tool === "pencil") {
            this.context.lineTo(current.x, current.y);
            this.context.stroke();
            return;
        }
        this.context.putImageData(this.snapshot, 0, 0);
        if (this.state.tool === "circle") {
            const centerX = (this.startPoint.x + current.x) / 2;
            const centerY = (this.startPoint.y + current.y) / 2;
            const radiusX = Math.abs(current.x - this.startPoint.x) / 2;
            const radiusY = Math.abs(current.y - this.startPoint.y) / 2;
            this.context.beginPath();
            this.context.ellipse(centerX, centerY, radiusX, radiusY, 0, 0, Math.PI * 2);
            this.context.stroke();
        } else if (this.state.tool === "arrow") {
            this.drawArrow(this.startPoint, current);
        }
    }

    pointerUp(event) {
        if (!this.drawing) return;
        this.pointerMove(event);
        this.drawing = false;
        this.context.closePath();
    }

    prepareContext() {
        this.context.strokeStyle = this.state.color;
        this.context.fillStyle = this.state.color;
        this.context.lineWidth = Number(this.state.width);
        this.context.lineCap = "round";
        this.context.lineJoin = "round";
    }

    drawArrow(start, end) {
        const angle = Math.atan2(end.y - start.y, end.x - start.x);
        const headLength = Math.max(14, Number(this.state.width) * 4);
        this.context.beginPath();
        this.context.moveTo(start.x, start.y);
        this.context.lineTo(end.x, end.y);
        this.context.stroke();
        this.context.beginPath();
        this.context.moveTo(end.x, end.y);
        this.context.lineTo(
            end.x - headLength * Math.cos(angle - Math.PI / 6),
            end.y - headLength * Math.sin(angle - Math.PI / 6)
        );
        this.context.lineTo(
            end.x - headLength * Math.cos(angle + Math.PI / 6),
            end.y - headLength * Math.sin(angle + Math.PI / 6)
        );
        this.context.closePath();
        this.context.fill();
    }

    undo() {
        const previous = this.history.pop();
        if (previous) this.context.putImageData(previous, 0, 0);
        this.state.historyCount = this.history.length;
    }

    clearAnnotations() {
        if (!this.original) return;
        this.history.push(this.context.getImageData(0, 0, this.canvas.width, this.canvas.height));
        this.state.historyCount = this.history.length;
        this.context.putImageData(this.original, 0, 0);
    }

    save() {
        const data = this.canvas.toDataURL("image/png").split(",")[1];
        this.props.onSave(data);
        this.props.close();
    }
}

export class AnnotatableImageField extends ImageField {
    static template = "pmant.AnnotatableImageField";

    setup() {
        super.setup();
        this.dialog = useService("dialog");
    }

    openEditor() {
        this.dialog.add(ImageAnnotationDialog, {
            imageUrl: this.getUrl(this.props.previewImage || this.props.name),
            onSave: (data) => {
                this.state.isValid = true;
                this.lastURL = undefined;
                this.props.record.update({ [this.props.name]: data });
            },
        });
    }
}

registry.category("fields").add("pmant_image_annotation", {
    ...imageField,
    component: AnnotatableImageField,
});
