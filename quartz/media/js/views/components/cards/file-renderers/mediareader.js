import ko from 'knockout';
import createVueApplication from 'arches/arches/app/media/js/utils/create-vue-application';
import MediaViewer from '@/quartz/file-renderers/MediaViewer.vue';
import mediaReaderTemplate from 'templates/views/components/cards/file-renderers/mediareader.htm';

ko.bindingHandlers.mediaViewer = {
    init: function (element, valueAccessor) {
        const media = ko.unwrap(valueAccessor());
        if (!media || !media.url) return;

        let vueApp = null;
        createVueApplication(MediaViewer, undefined, {
            url: media.url,
            name: media.name,
            type: media.type,
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

function viewModel(params) {
    this.params = params;
    const displayContent = ko.unwrap(params.displayContent);
    this.model = displayContent
        ? { url: displayContent.url, name: displayContent.name, type: displayContent.type }
        : null;
}

// One module registers both renderer names; video/audio only differ by RENDERERS type.
ko.components.register('videoreader', { viewModel, template: mediaReaderTemplate });
ko.components.register('audioreader', { viewModel, template: mediaReaderTemplate });

export default { videoreader: 'videoreader', audioreader: 'audioreader' };
