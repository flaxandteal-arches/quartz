<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps<{
    url: string;
    name: string;
}>();

const container = ref<HTMLDivElement | null>(null);
const wrapper = ref<HTMLDivElement | null>(null);
const edgesOn = ref(false);
const isFullscreen = ref(false);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let viewer: any = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let OV: any = null;

onMounted(async () => {
    if (!container.value) return;
    OV = await import("online-3d-viewer");
    viewer = new OV.EmbeddedViewer(container.value, {
        backgroundColor: new OV.RGBAColor(0, 0, 0, 0),
        defaultColor: new OV.RGBColor(180, 184, 192),
        edgeSettings: new OV.EdgeSettings(
            false,
            new OV.RGBColor(40, 40, 40),
            1,
        ),
    });
    const response = await fetch(props.url);
    const blob = await response.blob();
    const file = new File([blob], props.name, {
        type: blob.type || "application/octet-stream",
    });
    viewer.LoadModelFromFileList([file]);
});

onBeforeUnmount(() => {
    if (viewer && typeof viewer.Destroy === "function") {
        viewer.Destroy();
    }
    document.removeEventListener("fullscreenchange", onFullscreenChange);
});

function resetView() {
    if (!viewer || !OV) return;
    const v = viewer.GetViewer?.();
    if (!v) return;
    try {
        const sphere = v.GetBoundingSphere(() => true);
        if (sphere) v.FitSphereToWindow(sphere, true);
    } catch (err) {
        console.warn("Reset view failed:", err);
    }
}

function toggleEdges() {
    if (!viewer || !OV) return;
    const v = viewer.GetViewer?.();
    if (!v) return;
    edgesOn.value = !edgesOn.value;
    v.SetEdgeSettings(
        new OV.EdgeSettings(
            edgesOn.value,
            new OV.RGBColor(40, 40, 40),
            1,
        ),
    );
}

function onFullscreenChange() {
    isFullscreen.value = !!document.fullscreenElement;
}

function toggleFullscreen() {
    if (!wrapper.value) return;
    if (!document.fullscreenElement) {
        wrapper.value.requestFullscreen?.();
    } else {
        document.exitFullscreen?.();
    }
}

document.addEventListener("fullscreenchange", onFullscreenChange);
</script>

<template>
    <div ref="wrapper" class="model-viewer-wrapper">
        <div ref="container" class="model-viewer"></div>
        <div class="model-viewer-controls">
            <button type="button" title="Reset view" @click="resetView">
                <i class="fa fa-undo" aria-hidden="true"></i>
            </button>
            <button
                type="button"
                :title="edgesOn ? 'Hide edges' : 'Show edges'"
                :class="{ active: edgesOn }"
                @click="toggleEdges"
            >
                <i class="fa fa-cube" aria-hidden="true"></i>
            </button>
            <button
                type="button"
                :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
                @click="toggleFullscreen"
            >
                <i
                    :class="isFullscreen ? 'fa fa-compress' : 'fa fa-expand'"
                    aria-hidden="true"
                ></i>
            </button>
        </div>
    </div>
</template>

<style scoped>
.model-viewer-wrapper {
    position: relative;
    width: 100%;
    height: 100%;
    background: radial-gradient(ellipse at center, #e8ecf2 0%, #c4cad4 70%, #a8afbc 100%);
    border-radius: 6px;
    overflow: hidden;
}

.model-viewer {
    width: 100%;
    height: 100%;
}

.model-viewer-controls {
    --btn-size: 36px;
    position: absolute;
    top: 10px;
    right: 10px;
    display: flex;
    gap: calc(var(--btn-size) * 0.15);
    padding: calc(var(--btn-size) * 0.15);
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(8px);
    border-radius: calc(var(--btn-size) * 0.22);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    z-index: 10;
}

.model-viewer-controls button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--btn-size);
    height: var(--btn-size);
    font-size: calc(var(--btn-size) * 0.5);
    padding: 0;
    border: none;
    border-radius: calc(var(--btn-size) * 0.15);
    background: transparent;
    color: #333;
    cursor: pointer;
    transition: background 0.15s ease;
}

.model-viewer-controls button:hover {
    background: rgba(0, 0, 0, 0.08);
}

.model-viewer-controls button.active {
    background: rgba(59, 130, 246, 0.15);
    color: #1d4ed8;
}

.model-viewer-wrapper:fullscreen {
    background: radial-gradient(ellipse at center, #2a2f3a 0%, #1a1d24 100%);
    border-radius: 0;
}

.model-viewer-wrapper:fullscreen .model-viewer-controls {
    background: rgba(30, 30, 35, 0.75);
}

.model-viewer-wrapper:fullscreen .model-viewer-controls button {
    color: #e5e7eb;
}

.model-viewer-wrapper:fullscreen .model-viewer-controls button:hover {
    background: rgba(255, 255, 255, 0.12);
}
</style>
