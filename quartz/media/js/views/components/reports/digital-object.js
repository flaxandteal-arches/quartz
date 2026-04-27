// Project-level extension of arches-her's digital-object report.
// We do NOT edit arches-her; we let it self-register, then swap in a
// wrapped viewmodel that composes the upstream one and adds modelFiles.
import "arches_her/arches_her/media/js/views/components/reports/digital-object";
import "views/components/cards/file-renderers/modelviewer";
import fileRenderers from "file-renderers";
import ko from "knockout";

const MODEL_VIEWER_COMPONENT = "views/components/cards/file-renderers/modelviewer";

function getModelExtensions() {
    const renderer = Object.values(fileRenderers).find(
        (r) => r.component === MODEL_VIEWER_COMPONENT,
    );
    return (renderer?.ext || "")
        .split(",")
        .map((e) => e.trim().toLowerCase())
        .filter(Boolean);
}

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
        const modelExtensions = getModelExtensions();
        this.modelFiles = ko.pureComputed(() =>
            this.files().filter((f) => {
                const ext = (f.name || "").split(".").pop().toLowerCase();
                return modelExtensions.includes(ext);
            }),
        );
    },
    template: upstreamConfig.template,
});
