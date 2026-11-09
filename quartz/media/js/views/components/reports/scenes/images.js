import _ from "underscore";
import ko from "knockout";
import arches from "arches";
import reportUtils from "utils/report";
import imageMetadata from "utils/image-metadata";
import ImagesTemplate from "templates/views/components/reports/scenes/images.htm";
import "bindings/datatable";
import "bindings/reports";

export default ko.components.register(
    "views/components/reports/scenes/images",
    {
        viewModel: function (params) {
            const self = this;
            Object.assign(self, reportUtils);

            self.copyrightTableConfig = {
                ...self.defaultTableConfig,
                columns: Array(3).fill(null),
            };

            self.dataConfig = {
                images: "images",
            };

            self.loadMetadata = function (image) {
                if (image.loaded()) return;
                image.loaded(true);
                imageMetadata.fetchImageMetadata(image.fileId).then((data) => {
                    image.metadata(data.fields);
                });
            };

            self.cards = Object.assign({}, params.cards);
            self.resource = params?.data || undefined;
            self.edit = params.editTile || self.editTile;
            self.delete = params.deleteTile || self.deleteTile;
            self.add = params.addTile || self.addNewTile;
            self.images = ko.observableArray();
            self.copyright = ko.observableArray();
            self.visible = {
                copyright: ko.observable(true),
                images: ko.observable(true),
            };
            Object.assign(self.dataConfig, params.dataConfig || {});

            // if params.compiled is set and true, the user has compiled their own data.  Use as is.
            if (params?.compiled) {
            } else {
                const imagesNode = self.getRawNodeValue(
                    params.data(),
                    self.dataConfig.images
                );
                if (imagesNode?.length) {
                    this.images(
                        imagesNode.map((x) => {
                            const caption = self.getNodeValue(x, {
                                testPaths: [
                                    ["captions", "caption"],
                                    ["captions", "captiion"],
                                    [
                                        "caption notes",
                                        "caption note",
                                        "@display_value",
                                    ],
                                ],
                            });
                            const copyrightNote = self.getNodeValue(
                                x,
                                "copyright",
                                "copyright note",
                                "copyright note text"
                            );
                            const path = self.getNodeValue(x);
                            const fileDetails =
                                self.getRawNodeValue(x)?.file_details?.[0];
                            const fileName =
                                fileDetails?.name || self.getFileName(x);
                            const fileId =
                                fileDetails?.file_id ||
                                (path ? path.split("/").pop() : null);
                            const tileid = self.getTileId(x);

                            return {
                                caption,
                                copyrightNote,
                                path,
                                tileid,
                                fileName,
                                fileId,
                                metadata: ko.observableArray(),
                                loaded: ko.observable(false),
                            };
                        })
                    );
                }

                const copyrightNode = self.getRawNodeValue(
                    params.data(),
                    self.dataConfig.copyright
                );
                if (copyrightNode?.length) {
                    self.copyright(
                        copyrightNode.map((x) => {
                            const copyrightStatement = self.getNodeValue(
                                x,
                                "copyright statement"
                            );
                            const copyrightType = self.getNodeValue(
                                x,
                                "copyright type"
                            );
                            const tileid = self.getTileId(x);

                            return {
                                copyrightStatement,
                                copyrightType,
                                tileid,
                            };
                        })
                    );
                }
            }
        },
        template: ImagesTemplate,
    }
);
