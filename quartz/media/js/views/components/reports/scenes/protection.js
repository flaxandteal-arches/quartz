import ko from "knockout";
import reportUtils from "utils/report";
import ProtectionTemplate from "templates/views/components/reports/scenes/protection.htm";
import "bindings/datatable";
import "bindings/reports";
import "views/components/reports/scenes/map";

export default ko.components.register(
    "views/components/reports/scenes/protection",
    {
        viewModel: function (params) {
            const self = this;
            Object.assign(self, reportUtils);

            self.dataConfig = {
                location: ["location data"],
                protection: "designation and protection assignment",
                landUse: "land use classification assignment",
                areaAssignment: ["area assignments", "area assignment"],
            };

            self.cards = params.cards || {};
            self.selectedGeometry = params.selectedGeometry || ko.observable();
            self.edit = params.editTile || self.editTile;
            self.delete = params.deleteTile || self.deleteTile;
            self.add = params.addTile || self.addNewTile;
            self.visible = {
                geospatial: ko.observable(true),
                designations: ko.observable(true),
                map: ko.observable(true),
                areaAssignment: ko.observable(true),
                landUse: ko.observable(true),
            };
            Object.assign(self.dataConfig, params.dataConfig || {});

            self.areaAssignmentsTableConfig = {
                ...self.defaultTableConfig,
                columns: Array(8).fill(null),
            };

            self.landUseTableConfig = {
                ...self.defaultTableConfig,
                columns: Array(7).fill(null),
            };

            self.designationTableConfig = {
                ...self.defaultTableConfig,
                columns: Array(14).fill(null),
            };

            self.currentDesignation = ko.observable();
            self.selectedGeometry = ko.observable();
            self.locationRoot = undefined;
            self.coordinateData = ko.observable();

            self.geojson = ko.observable();
            self.areaAssignment = ko.observableArray();
            self.landUseClassification = ko.observableArray();
            self.designations = ko.observableArray();

            self.jumpToDesignationGeometry = (row) => {
                self.selectedGeometry(row.geometry);
            };

            const setupCards = (tileid) => {
                if (self.cards.location) {
                    const subCards = self.cards.location.subCards;
                    const rootCard = self.locationRoot;
                    const tileCards = self.createCardDictionary(
                        rootCard
                            .tiles()
                            .find((rootTile) => rootTile.tileid == tileid)
                            ?.cards
                    );
                    if (tileCards) {
                        tileCards.landUse = tileCards?.[subCards.landUse];
                        tileCards.areaAssignment =
                            tileCards?.[subCards.areaAssignment];
                        Object.assign(self.cards, tileCards);
                    }
                }
            };

            // if params.compiled is set and true, the user has compiled their own data.  Use as is.
            if (!params?.compiled) {
                const protectionNode = self.getRawNodeValue(
                    params.data(),
                    self.dataConfig.protection
                );
                if (protectionNode?.length) {
                    self.designations(
                        protectionNode.map((x) => {
                            const name = self.getNodeValue(
                                x,
                                "designation names",
                                "designation name"
                            );
                            const nameUseType = self.getNodeValue(
                                x,
                                "designation names",
                                "designation name use type"
                            );
                            const protectionType = self.getNodeValue(
                                x,
                                "designation or protection type"
                            );
                            const startDate = self.getNodeValue(
                                x,
                                "designation and protection timespan",
                                "designation start date"
                            );
                            const endDate = self.getNodeValue(
                                x,
                                "designation and protection timespan",
                                "designation end date"
                            );
                            const grade = self.getNodeValue(x, "grade");
                            const risk = self.getNodeValue(x, "risk status");
                            const amendmentDate = self.getNodeValue(
                                x,
                                "designation and protection timespan",
                                "designation amendment date"
                            );
                            const displayDate = self.getNodeValue(
                                x,
                                "designation and protection timespan",
                                "display date"
                            );
                            const reference = self.getNodeValue(
                                x,
                                "reference url",
                                "url"
                            );
                            const localHeritageListCriteriaType = self.getNodeValue(
                                x,
                                "local heritage list criteria type"
                            );
                            const description = self.getNodeValue(
                                x,
                                "description",
                                0
                            );
                            const digitalFileNode = self.getRawNodeValue(
                                x,
                                "digital file(s)"
                            );
                            const digitalFile = self.getNodeValue(digitalFileNode);
                            const digitalFileLink = self.getResourceLink(digitalFileNode);
                            const tileid = self.getTileId(x);
                            const geometry = self.getNodeValue(
                                x,
                                "designation mapping",
                                "designation geometry"
                            );
                            return {
                                amendmentDate,
                                description,
                                digitalFile,
                                digitalFileLink,
                                displayDate,
                                endDate,
                                geometry,
                                grade,
                                localHeritageListCriteriaType,
                                name,
                                nameUseType,
                                protectionType,
                                reference,
                                risk,
                                startDate,
                                tileid,
                            };
                        })
                    );

                    self.geojson(
                        self.designations().reduce(
                            (geojson, currentJson) => {
                                const tileId = currentJson.tileid;
                                if (currentJson.geometry.features) {
                                    const jsonWithTileId =
                                        currentJson.geometry.features.map(
                                            (x) => {
                                                x.properties.tileId = tileId;
                                                return x;
                                            }
                                        );
                                    geojson.features = [
                                        ...geojson.features,
                                        ...jsonWithTileId,
                                    ];
                                }
                                return geojson;
                            },
                            { features: [], type: "FeatureCollection" }
                        )
                    );
                }
                const locationNode = self.getRawNodeValue(
                    params.data(),
                    ...self.dataConfig.location
                );

                if (self.cards?.location?.card) {
                    self.locationRoot = self.cards?.location?.card;
                }

                if (locationNode) {
                    setupCards(self.getTileId(locationNode));
                }

                if (self.dataConfig.areaAssignment) {
                    const areaAssignmentsNode = self.getRawNodeValue(
                        locationNode,
                        ...self.dataConfig.areaAssignment
                    );
                    if (Array.isArray(areaAssignmentsNode)) {
                        self.areaAssignment(
                            areaAssignmentsNode.map((x) => {
                                const endDate = self.getNodeValue(
                                    x,
                                    "area status timespan",
                                    "area status end date"
                                );
                                const ownership = self.getNodeValue(
                                    x,
                                    "ownership"
                                );
                                const reference = self.getNodeValue(
                                    x,
                                    "area reference",
                                    "area reference value"
                                );
                                const shineForm = self.getNodeValue(
                                    x,
                                    "shine - form"
                                );
                                const shineSignificance = self.getNodeValue(
                                    x,
                                    "shine - significance"
                                );
                                const startDate = self.getNodeValue(
                                    x,
                                    "area status timespan",
                                    "area status start date"
                                );
                                const status = self.getNodeValue(
                                    x,
                                    "area status"
                                );
                                const tileid = self.getTileId(x);
                                return {
                                    endDate,
                                    ownership,
                                    reference,
                                    shineForm,
                                    shineSignificance,
                                    startDate,
                                    status,
                                    tileid,
                                };
                            })
                        );
                    }
                }

                let landUseClassificationNode = self.getRawNodeValue(
                    locationNode,
                    self.dataConfig.landUse
                );
                if (landUseClassificationNode) {
                    if (!Array.isArray(landUseClassificationNode)) {
                        landUseClassificationNode = [landUseClassificationNode];
                    }
                    self.landUseClassification(
                        landUseClassificationNode.map((x) => {
                            const classification = self.getNodeValue(
                                x,
                                "land use classification"
                            );
                            const endDate = self.getNodeValue(
                                x,
                                "land use assessment timespan",
                                "land use assessment end date"
                            );
                            const geology = self.getNodeValue(x, "geology");
                            const reference = self.getNodeValue(
                                x,
                                "land use notes",
                                "land use notes value"
                            );
                            const startDate = self.getNodeValue(
                                x,
                                "land use assessment timespan",
                                "land use assessment start date"
                            );
                            const subSoil = self.getNodeValue(x, "sub-soil");
                            const tileid = self.getTileId(x);
                            return {
                                classification,
                                endDate,
                                geology,
                                reference,
                                startDate,
                                subSoil,
                                tileid,
                            };
                        })
                    );
                }
            }
        },
        template: ProtectionTemplate,
    }
);
