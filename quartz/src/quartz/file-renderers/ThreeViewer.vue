<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps<{
    url: string;
    name: string;
}>();

const container = ref<HTMLDivElement | null>(null);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let viewer: any = null;

onMounted(async () => {
    if (!container.value) return;
    const OV = await import("online-3d-viewer");
    viewer = new OV.EmbeddedViewer(container.value, {
        backgroundColor: new OV.RGBAColor(255, 255, 255, 255),
        defaultColor: new OV.RGBColor(200, 200, 200),
    });
    const response = await fetch(props.url);
    const blob = await response.blob();
    const file = new File([blob], props.name, {
        type: blob.type || "application/octet-stream",
    });
    console.log("Rendering file in Vue:", file);
    viewer.LoadModelFromFileList([file]);
});

onBeforeUnmount(() => {
    if (viewer && typeof viewer.Destroy === "function") {
        viewer.Destroy();
    }
});
</script>

<template>
    <div
        ref="container"
        class="three-viewer"
        style="width: 100%; height: 100%;"
    ></div>
</template>
