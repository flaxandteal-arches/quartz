// Project-level extension of arches-her's digital-object report.
// We do NOT edit arches-her; we let it self-register, then swap in a
// wrapped viewmodel that composes the upstream one and adds modelFiles.
import "arches_her/arches_her/media/js/views/components/reports/digital-object";
import "views/components/cards/file-renderers/modelviewer";
import ko from "knockout";

const MODEL_EXTENSIONS = [
    "stl", "glb", "gltf", "obj", "ply", "3ds", "fbx", "dae", "3mf", "off", "3dm", "wrl",
];

let upstreamConfig;
ko.components.defaultLoader.getConfig(
    "digital-object-report",
    (config) => { upstreamConfig = config; },
);
const UpstreamViewModel = upstreamConfig.viewModel;

ko.components.unregister("digital-object-report");
ko.components.register("digital-object-report", {
    viewModel: function (params) {
        UpstreamViewModel.call(this, params);
        this.modelFiles = ko.pureComputed(() =>
            this.files().filter((f) => {
                const ext = (f.name || "").split(".").pop().toLowerCase();
                return MODEL_EXTENSIONS.includes(ext);
            }),
        );
    },
    template: upstreamConfig.template,
});
