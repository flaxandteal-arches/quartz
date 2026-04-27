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
const isLoading = ref(true);
const loadStatus = ref("Initialising");
const sizeLabel = ref("");
const loadError = ref<string | null>(null);

function formatBytes(bytes: number): string {
    if (!bytes) return "";
    const units = ["B", "KB", "MB", "GB"];
    let v = bytes;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
        v /= 1024;
        i += 1;
    }
    return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let viewer: any = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let OV: any = null;

onMounted(async () => {
    if (!container.value) return;
    try {
        loadStatus.value = "Loading viewer";
        OV = await import("online-3d-viewer");
        viewer = new OV.EmbeddedViewer(container.value, {
            backgroundColor: new OV.RGBAColor(0, 0, 0, 0),
            defaultColor: new OV.RGBColor(180, 184, 192),
            edgeSettings: new OV.EdgeSettings(
                false,
                new OV.RGBColor(40, 40, 40),
                1,
            ),
            onModelLoaded: () => {
                isLoading.value = false;
            },
        });

        loadStatus.value = "Downloading model";
        const response = await fetch(props.url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const total = Number(response.headers.get("content-length")) || 0;
        if (total) sizeLabel.value = formatBytes(total);

        const blob = await response.blob();
        loadStatus.value = "Parsing model";
        const file = new File([blob], props.name, {
            type: blob.type || "application/octet-stream",
        });
        viewer.LoadModelFromFileList([file]);
    } catch (err) {
        loadError.value = err instanceof Error ? err.message : String(err);
        isLoading.value = false;
    }
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
        <div v-if="isLoading || loadError" class="model-viewer-overlay">
            <div v-if="loadError" class="model-viewer-error">
                <i class="fa fa-exclamation-triangle" aria-hidden="true"></i>
                <div>Failed to load model</div>
                <div class="model-viewer-error-detail">{{ loadError }}</div>
            </div>
            <div v-else class="model-viewer-loader">
                <div class="model-viewer-spinner" aria-hidden="true"></div>
                <div class="model-viewer-status">
                    {{ loadStatus }}<span v-if="sizeLabel"> · {{ sizeLabel }}</span>
                </div>
            </div>
        </div>
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

<style>
.model-viewer-mount {
    width: 100%;
    height: 400px;
}

.model-viewer-mount--full {
    height: calc(100vh - 200px);
}
</style>

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

.model-viewer-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(2px);
    z-index: 5;
    pointer-events: none;
}

.model-viewer-loader {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    color: #333;
    font-size: 14px;
}

.model-viewer-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid rgba(0, 0, 0, 0.12);
    border-top-color: #1d4ed8;
    border-radius: 50%;
    animation: model-viewer-spin 0.8s linear infinite;
}

@keyframes model-viewer-spin {
    to { transform: rotate(360deg); }
}

.model-viewer-status {
    font-weight: 500;
}

.model-viewer-error {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    color: #b91c1c;
    text-align: center;
    padding: 16px;
}

.model-viewer-error .fa {
    font-size: 32px;
}

.model-viewer-error-detail {
    font-size: 12px;
    opacity: 0.8;
}

.model-viewer-wrapper:fullscreen .model-viewer-overlay {
    background: rgba(20, 22, 28, 0.6);
}

.model-viewer-wrapper:fullscreen .model-viewer-loader {
    color: #e5e7eb;
}
</style>
