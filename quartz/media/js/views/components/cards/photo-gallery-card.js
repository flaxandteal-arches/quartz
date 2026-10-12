import ko from "knockout";
import koMapping from "knockout-mapping";
import _ from "underscore";
import arches from "arches";
import Dropzone from "dropzone";
import uuid from "uuid";
import CardComponentViewModel from "viewmodels/card-component";
import WorkbenchComponentViewModel from "views/components/workbench";
import PhotoGallery from "viewmodels/photo-gallery";
import photoGalleryCardTemplate from "templates/views/components/cards/photo-gallery-card.htm";
import AlertViewModel from "viewmodels/alert";
import "bindings/slide";
import "bindings/fadeVisible";
import "bindings/dropzone";
import "bindings/gallery";


const viewModel = function(params) {

    params.configKeys = ['acceptedFiles', 'maxFilesize'];
    var self = this;
    CardComponentViewModel.apply(this, [params]);
    WorkbenchComponentViewModel.apply(this, [params]);
    if (this.card && this.card.activeTab) {
        self.activeTab(this.card.activeTab);
    }

    this.photoGallery = new PhotoGallery();
    this.lastSelected = 0;
    this.selected = ko.observable();
    self.activeTab.subscribe(function(val){self.card.activeTab = val;});
    self.card.tiles.subscribe(function(val){
        if (val.length === 0) {
            self.activeTab(null);
        }
    });

    var getfileListNode = function(){
        var fileListNodeId;
        var fileListNodes = params.card.model.nodes().filter(
            function(val){
                if (val.datatype() === 'file-list' && self.card.nodegroupid == val.nodeGroupId())
                    return val;
            });
        if (fileListNodes.length) {
            fileListNodeId = fileListNodes[0].nodeid;
        }
        return fileListNodeId;
    };

    this.fileListNodeId = getfileListNode();

    this.maxFilesize = ko.computed(function(){
        var mfs = "Missing maxFilesize";
        self.card.widgets().forEach(function(widget){
            if (widget.node_id() === self.fileListNodeId) {
                mfs = widget.config.maxFilesize() || "--";
            }
        });
        return mfs;
    });

    this.acceptedFiles = ko.computed(function(){
        return self.card.widgets().find(widget=>widget.node_id() === self.fileListNodeId)?.config.acceptedFiles() || arches.translations.allFormatsAccepted;
    });

    this.cleanUrl = function(url) {
        const httpRegex = /^https?:\/\//;
        return !url || httpRegex.test(url) || url.startsWith(arches.urls.url_subpath) ? url :
            (arches.urls.url_subpath + url).replace('//', '/');
    };

    this.iiifUrl = function(name, size) {
        if (size !== 'max') size = size + ','
        return arches.urls.url_subpath + '/iiifserver/iiif/2/' + name + '/full/' + size + '/0/default.jpg';
    }

    this.getUrl = function(tile, size){
        var url = '';
        var name = '';
        var val = ko.unwrap(tile.data[this.fileListNodeId]);
        if (val && val.length == 1) {
            {
                url = self.cleanUrl(ko.unwrap(val[0].url)) || ko.unwrap(val[0].content);
                name = ko.unwrap(val[0].name);
                if (url && name){
                    url = self.iiifUrl(name, size || 'max');
                }
            }
        }
        return {url: url, name: name};
    };

    this.uniqueId = uuid.generate();
    this.uniqueidClass = ko.computed(function() {
        return "unique_id_" + self.uniqueId;
    });

    this.showThumbnails = ko.observable(false);

    this.selectDefault = function(){
        var self = this;
        return function() {
            var selectedIndex = self.card.tiles.indexOf(self.selected());
            if(self.card.tiles().length > 0 && selectedIndex === -1) {
                selectedIndex = 0;
            }
            self.card.tiles()[selectedIndex];
            self.photoGallery.selectItem(self.card.tiles()[selectedIndex]);
        };
    };
    this.defaultSelector = this.selectDefault();

    this.displayContent = ko.pureComputed(function(){
        var photo;
        var selected = this.card.tiles().find(
            function(tile){
                return tile.selected() === true;
            });
        if (selected) {
            this.selected(selected);
            photo = this.getUrl(selected).url;
        }
        else {
            this.selected(undefined);
        }
        return photo;
    }, this);

    if (this.displayContent() === undefined) {
        var selectedIndex = 0;
        if (
            this.card.tiles().length > 0 &&
            this.form &&
            (ko.unwrap(this.form.selection) && this.form.selection() !== 'root') ||
            (this.form && !ko.unwrap(this.form.selection))) {
            this.photoGallery.selectItem(this.card.tiles()[selectedIndex]);
        }
    }

    this.removeTile = function(val){
        //TODO: Upon deletion select the tile to the left of the deleted tile
        //If the deleted tile is the first tile, then select the tile to the right
        // var tileCount = this.parent.tiles().length;
        // var index = this.parent.tiles.indexOf(val);
        val.deleteTile();
        setTimeout(self.defaultSelector, 150);
    };

    this.moveTile = function(tile, position) {
        var tiles = self.card.tiles().slice();
        var from = tiles.indexOf(tile);
        var to = Math.min(Math.max(parseInt(position, 10) - 1, 0), tiles.length - 1);
        if (from === -1 || isNaN(to) || from === to) {
            return;
        }
        if (!self.savedOrder()) {
            self.savedOrder(tiles.slice());
        }
        tiles.splice(from, 1);
        tiles.splice(to, 0, tile);
        self.card.tiles(tiles);
    };

    this.moveUp = function(tile) {
        self.moveTile(tile, self.card.tiles.indexOf(tile));
    };

    this.moveDown = function(tile) {
        self.moveTile(tile, self.card.tiles.indexOf(tile) + 2);
    };

    this.moveFirst = function(tile) {
        self.moveTile(tile, 1);
    };

    this.moveLast = function(tile) {
        self.moveTile(tile, self.card.tiles().length);
    };

    this.positionChange = function(tile, e) {
        self.moveTile(tile, e.target.value);
    };

    this.positionKeydown = function(tile, e) {
        if (e.key === 'Enter') {
            e.target.blur();
        } else if (e.key === 'ArrowUp') {
            self.moveUp(tile);
            return false;
        } else if (e.key === 'ArrowDown') {
            self.moveDown(tile);
            return false;
        }
        return true;
    };

    this.savedOrder = ko.observable(null);

    this.positionChanged = function(tile) {
        var saved = self.savedOrder();
        return !!saved && saved.indexOf(tile) !== self.card.tiles.indexOf(tile);
    };

    this.orderChanged = ko.pureComputed(function() {
        return self.card.tiles().some(self.positionChanged);
    });

    // Tree drag-and-drop also lands here and saves the whole current order, pending moves included.
    // Core only updates tile.sortorder once the request completes, and every tile save posts its
    // sortorder, so a save sent in between would write the old position back.
    var reorderTiles = self.card.reorderTiles;
    self.card.reorderTiles = function() {
        self.card.tiles().forEach(function(tile, index) {
            tile.sortorder = index;
        });
        self.savedOrder(null);
        return reorderTiles.apply(this, arguments);
    };

    this.saveOrder = function() {
        if (self.orderChanged()) {
            self.card.reorderTiles();
        }
        self.savedOrder(null);
    };

    this.resetOrder = function() {
        var saved = self.savedOrder();
        if (!saved) {
            return;
        }
        // tiles uploaded or deleted since the first move keep the current list's membership
        var rank = function(tile) {
            var i = saved.indexOf(tile);
            return i === -1 ? saved.length : i;
        };
        self.card.tiles(self.card.tiles().slice().sort(function(a, b) { return rank(a) - rank(b); }));
        self.savedOrder(null);
    };

    // order first, so the tile save below already carries the new sortorder
    this.saveTileAndOrder = function(tile) {
        self.saveOrder();
        if (tile.dirty()) {
            tile.save();
        }
    };

    this.resetTileAndOrder = function(tile) {
        tile.reset();
        self.resetOrder();
    };

    if (this.form && ko.unwrap(this.form.resourceId)) {
        this.card.resourceinstanceid = ko.unwrap(this.form.resourceId);
    } else if (this.card.resourceinstanceid === undefined && this.card.tiles().length === 0) {
        this.card.resourceinstanceid = uuid.generate();
    }

    function sleep(milliseconds) {
        var start = new Date().getTime();
        for (var i = 0; i < 1e7; i++) {
            if ((new Date().getTime() - start) > milliseconds){
                break;
            }
        }
    }

    this.addTile = function(file){
        var acceptedFileFormats;
        var loadFile;
        acceptedFileFormats = ((ko.unwrap(self.acceptedFiles)).split(',').map(item=>item.trim())).map(format => format.replace('.', ''));
        if(ko.unwrap(self.acceptedFiles) != arches.translations.allFormatsAccepted && acceptedFileFormats !== undefined && acceptedFileFormats.length > 0){
            var fileType = file.name.split('.').pop().toLowerCase();
            if(acceptedFileFormats.includes(fileType)){
                loadFile = true;
            }
            else{
                loadFile = false;
            }
        }
        else{
            loadFile = true;
        }

        if (loadFile === true) {
            var newtile;
            newtile = self.card.getNewTile();
            var emptyStr = function() {
                return {[arches.activeLanguage]: {
                    direction: arches.languages.find(lang => lang.code == arches.activeLanguage).default_direction,
                    value: '',
                }};
            };
            var tilevalue = {
                name: file.name,
                accepted: true,
                height: file.height,
                lastModified: file.lastModified,
                size: file.size,
                status: file.status,
                type: file.type,
                width: file.width,
                url: null,
                file_id: null,
                index: 0,
                content: window.URL.createObjectURL(file),
                error: file.error,
                altText: emptyStr(),
                title: emptyStr(),
                attribution: emptyStr(),
                description: emptyStr()
            };
            newtile.data[self.fileListNodeId]([tilevalue]);
            newtile.formData.append('file-list_' + self.fileListNodeId, file, file.name);
            newtile.resourceinstance_id = self.card.resourceinstanceid;
            if (self.card.tiles().length === 0) {
                sleep(50);
            }
            newtile.save();
            self.card.newTile = undefined;
        }
        else{
            params.pageVm.alert(new AlertViewModel(
                'ep-alert-red',
                arches.translations.incorrectFileFormat,
                arches.translations.fileFormatNotAccepted(ko.unwrap(self.acceptedFiles)),
                null,
                function(){}
            ));
        }
    };

    this.dropzoneOptions = {
        url: "arches.urls.root",
        dictDefaultMessage: '',
        autoProcessQueue: false,
        uploadMultiple: true,
        autoQueue: false,
        clickable: ".fileinput-button." + this.uniqueidClass(),
        previewsContainer: '#hidden-dz-previews',
        init: function() {
            self.dropzone = this;
            this.on("addedfile", self.addTile, self);
            this.on("error", function(file, error) {
                file.error = error;
            });
        }
    };
};

export default ko.components.register('photo-gallery-card', {
    viewModel: viewModel,
    template: photoGalleryCardTemplate,
});
