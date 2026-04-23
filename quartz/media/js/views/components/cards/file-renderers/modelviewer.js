import ko from 'knockout';
import createVueApplication from 'arches/arches/app/media/js/utils/create-vue-application';
import ModelViewer from '@/quartz/file-renderers/ModelViewer.vue';
import modelViewerTemplate from 'templates/views/components/cards/file-renderers/modelviewer.htm';

ko.bindingHandlers.modelViewer = {
    init: function (element, valueAccessor) {
        const model = ko.unwrap(valueAccessor());
        if (!model || !model.url || !model.name) return;

        // url/name come from the card's in-memory file state (not an API),
        // so initialProps is the documented escape hatch here.
        let vueApp = null;
        createVueApplication(ModelViewer, undefined, {
            url: model.url,
            name: model.name,
        })
            .then((app) => {
                vueApp = app;
                vueApp.mount(element);
            })
            .catch(console.error);

        ko.utils.domNodeDisposal.addDisposeCallback(element, () => {
            if (vueApp) vueApp.unmount();
        });
    },
};

export default ko.components.register('modelviewer', {
    viewModel: function (params) {
        this.params = params;
        const displayContent = ko.unwrap(params.displayContent);
        this.model = displayContent
            ? { url: displayContent.url, name: displayContent.name }
            : null;
    },
    template: modelViewerTemplate,
});
