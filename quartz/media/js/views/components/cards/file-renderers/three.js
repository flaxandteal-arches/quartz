import ko from 'knockout';
import threeTemplate from 'templates/views/components/cards/file-renderers/three.htm';

ko.bindingHandlers.online3dViewer = {
    init: function (element, valueAccessor) {
        const model = ko.unwrap(valueAccessor());
        if (!model || !model.url || !model.name) return;
        let viewer = null;
        import('online-3d-viewer').then((OV) => {
            viewer = new OV.EmbeddedViewer(element, {
                backgroundColor: new OV.RGBAColor(255, 255, 255, 255),
                defaultColor: new OV.RGBColor(200, 200, 200),
            });
            fetch(model.url)
                .then((r) => r.blob())
                .then((blob) => {
                    const file = new File([blob], model.name, { type: blob.type || 'application/octet-stream' });
                    viewer.LoadModelFromFileList([file]);
                });
        });
        ko.utils.domNodeDisposal.addDisposeCallback(element, () => {
            if (viewer && typeof viewer.Destroy === 'function') viewer.Destroy();
        });
    },
};

export default ko.components.register('three', {
    viewModel: function (params) {
        this.params = params;
        const displayContent = ko.unwrap(params.displayContent);
        this.model = displayContent
            ? { url: displayContent.url, name: displayContent.name }
            : null;
    },
    template: threeTemplate,
});
