<script setup lang="ts">
// Barebones native media player. The browser plays whatever codecs it
// supports (MP4/H.264, WebM, Ogg); anything it can't, the download link covers.
const props = defineProps<{
    url: string;
    name: string;
    type: string;
}>();

const isVideo = (props.type || "").indexOf("video/") === 0;
</script>

<template>
    <div class="media-viewer">
        <video
            v-if="isVideo"
            class="media-viewer-el"
            controls
            :src="url"
        ></video>
        <audio
            v-else
            class="media-viewer-el media-viewer-el--audio"
            controls
            :src="url"
        ></audio>
        <a
            class="btn btn-primary"
            :href="url"
            :download="name"
        >
            <i
                class="fa fa-download"
                aria-hidden="true"
            ></i>
            Download
        </a>
    </div>
</template>

<style scoped>
.media-viewer {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 16px;
}

.media-viewer-el {
    width: 100%;
    max-height: 60vh;
}

.media-viewer-el--audio {
    width: 100%;
}
</style>
