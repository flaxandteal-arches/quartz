import _ from "underscore";
import ko from "knockout";
import reportUtils from "utils/report";
import ResourcesTemplate from "templates/views/components/reports/scenes/resources.htm";
import "bindings/datatable";
import "bindings/reports";
import { generateArchesURL } from "@/arches/utils/generate-arches-url.ts";

// Condition Report graph and node IDs
const CONDITION_REPORT_GRAPH_ID = "9fccd932-8e8f-4595-89bd-3cb04ddfecae";
const CR_DATE_NODE         = "a15e9d62-742b-49d1-a6ae-8548828d852f";
const CR_SUMMARY_TYPE_NODE = "ae79686f-ec19-4e02-93b5-9ebe3a42bc70";
const CR_SUMMARY_NODE      = "1fdb8dc3-ac7e-4d62-87da-6d60d5b105b7";
const CR_OFFICER_NODE      = "768abdbb-10b6-408e-96a5-65767e1e5d45";
const CR_CONDITION_NODE    = "fa209d71-a371-4ef8-8589-a9fa2d93e6de";
const CR_OCCUPANCY_NODE    = "9f196994-68b6-4971-a528-6e6e923cdb0b";
const CR_MAINTENANCE_NODE  = "9cbe0f0d-e6e5-4999-b3cd-5d85cdaceb43";

/** Pull a node value out of a tiles array by node ID. */
function getNodeFromTiles(tiles, nodeId) {
    for (const tile of (tiles || [])) {
        if (nodeId in (tile.data || {})) {
            return tile.data[nodeId];
        }
    }
    return null;
}

/** Get the English prefLabel from a concept array (controlled-list format). */
function conceptLabel(val) {
    if (!Array.isArray(val) || !val.length) return "";
    const labels = val[0]?.labels || [];
    const hit = labels.find(l => l.valuetype_id === "prefLabel" && l.language_id === "en");
    return hit?.value || labels.find(l => l.valuetype_id === "prefLabel")?.value || "";
}

/** Get the English string from an i18n object `{en: {value: "..."}, ...}`. */
function i18nString(val) {
    if (!val || typeof val !== "object") return "";
    return val["en"]?.value || Object.values(val)[0]?.value || "";
}

export default ko.components.register(
    "views/components/reports/scenes/resources",
    {
        viewModel: function (params) {
            const self = this;
            Object.assign(self, reportUtils);

            //Related Resource 2 column table configuration
            self.relatedResourceTwoColumnTableConfig = {
                ...self.defaultTableConfig,
                paging: true,
                searching: true,
                columns: Array(2).fill(null),
            };

            self.archiveHolderTableConfig = {
                ...self.defaultTableConfig,
                paging: true,
                searching: true,
                columns: Array(4).fill(null),
            };

            self.relatedResourceThreeColumnTableConfig = {
                ...self.defaultTableConfig,
                paging: true,
                searching: true,
                columns: Array(3).fill(null),
            };

            self.applicationAreaTableConfig = {
                ...self.defaultTableConfig,
                paging: true,
                searching: true,
                columns: Array(2).fill(null),
            };

            // 7 columns: Date, Summary Type, Summary, Officer, Condition, Occupancy, Maintenance
            self.conditionReportTableConfig = {
                ...self.defaultTableConfig,
                paging: true,
                searching: true,
                order: [[0, "desc"]], // sort by Date descending by default
                columns: Array(7).fill(null),
            };

            self.dataConfig = {
                activities: "associated activities",
                consultations: "associated consultations",
                files: "associated files",
                assets: "associated monuments, areas and artefacts",
                archive: "associated archives",
                actors: "associated actors",
            };

            self.cards = Object.assign({}, params.cards);
            self.resource = params?.data || undefined;
            self.edit = params.editTile || self.editTile;
            self.delete = params.deleteTile || self.deleteTile;
            self.add = params.addTile || self.addNewTile;
            self.activities = ko.observableArray();
            self.consultations = ko.observableArray();
            self.consultations_message = ko.observable(null);
            self.files = ko.observableArray();
            self.archive = ko.observableArray();
            self.actors = ko.observableArray();
            self.assets = ko.observableArray();
            self.translation = ko.observableArray();
            self.applicationArea = ko.observableArray();
            self.period = ko.observableArray();
            self.conditionReports = ko.observableArray();
            self.visible = {
                period: ko.observable(true),
                archive: ko.observable(true),
                activities: ko.observable(true),
                consultations: ko.observable(true),
                files: ko.observable(true),
                actors: ko.observable(true),
                assets: ko.observable(true),
                applicationArea: ko.observable(true),
                translation: ko.observable(true),
                conditionReports: ko.observable(true),
            };
            Object.assign(self.dataConfig, params.dataConfig || {});

            if (!(params?.compiled)) {
                const associatedActivitiesNode = self.getRawNodeValue(
                    params.data(),
                    self.dataConfig.activities,
                    "instance_details"
                );
                if (Array.isArray(associatedActivitiesNode)) {
                    const tileid = self.getTileId(
                        self.getRawNodeValue(
                            params.data(),
                            self.dataConfig.activities
                        )
                    );
                    self.activities(
                        associatedActivitiesNode.map((x) => {
                            const activity = self.getNodeValue(x);
                            const resourceUrl = self.getResourceLink(x);
                            return { activity, resourceUrl, tileid };
                        })
                    );
                }

                const associatedConsultationsNode = self.getRawNodeValue(
                    params.data(),
                    self.dataConfig.consultations,
                    "instance_details"
                );
                if (Array.isArray(associatedConsultationsNode)) {
                    const tileid = self.getTileId(
                        self.getRawNodeValue(
                            params.data(),
                            self.dataConfig.consultations
                        )
                    );
                    self.consultations(
                        associatedConsultationsNode.map((x) => {
                            const consultation = self.getNodeValue(x);
                            const resourceUrl = self.getResourceLink(x);
                            return { consultation, resourceUrl, tileid };
                        })
                    );
                }

                const userAvailableConsultationCards = () => {
                    return $.ajax({
                        url: generateArchesURL("arches:api_card", { resourceid: self.dataConfig.resourceinstanceid }),
                        context: this,
                    })
                        .done(function (response) { return response; })
                        .fail(function () { return false; });
                };

                if (self.dataConfig.resourceinstanceid) {
                    userAvailableConsultationCards().then(function (cards_response) {
                        if (cards_response !== false) {
                            var card_names = [];
                            for (const card in cards_response.cards) {
                                card_names.push(cards_response.cards[card].name);
                            }
                            if (card_names.includes("Associated Consultations")) {
                                self.consultations_message("No consultations for this resource");
                            } else {
                                self.consultations_message("You do not have permission to see this information");
                            }
                        } else {
                            self.consultations_message("There was an issue checking for associated consultations.");
                        }
                    });
                } else {
                    self.consultations_message("There was an issue checking for associated consultations.");
                }

                const associatedArchiveNode = self.getRawNodeValue(params.data(), self.dataConfig.archive);
                if (Array.isArray(associatedArchiveNode)) {
                    let key = "Associated Archive Objects";
                    if (!(key in associatedArchiveNode[0])) key = undefined;
                    self.archive(
                        associatedArchiveNode.map((x) => {
                            const archiveHolders = [];
                            var reference, title, tileid, holders;
                            if (key) {
                                reference = self.getNodeValue(x, key, "archive object references", "archive object reference");
                                title = self.getNodeValue(x, key, "archive object titles", "archive object title");
                                tileid = self.getTileId(x);
                                holders = self.getRawNodeValue(x, key, "archive holder", "instance_details");
                            } else {
                                reference = self.getNodeValue(x, "archive object references", "archive object reference");
                                title = self.getNodeValue(x, "archive object titles", "archive object title");
                                tileid = self.getTileId(x);
                                holders = self.getRawNodeValue(x, "archive holder", "instance_details");
                            }
                            holders?.forEach((element) => {
                                archiveHolders.push({
                                    holder: self.getNodeValue(element),
                                    holderLink: self.getResourceLink(element),
                                });
                            });
                            return { archiveHolders, reference, title, tileid };
                        })
                    );
                }

                const associatedFilesNode = self.getRawNodeValue(params.data(), self.dataConfig.files, "instance_details");
                if (Array.isArray(associatedFilesNode)) {
                    const tileid = self.getTileId(self.getRawNodeValue(params.data(), self.dataConfig.files));
                    self.files(
                        associatedFilesNode.map((x) => {
                            const file = self.getNodeValue(x);
                            const resourceUrl = self.getResourceLink(x);
                            return { file, resourceUrl, tileid };
                        })
                    );
                }

                const associatedArtifactsNode = self.getRawNodeValue(params.data(), self.dataConfig.assets);
                if (associatedArtifactsNode) {
                    if (Array.isArray(associatedArtifactsNode)) {
                        let key = "Monument, Area or Artefact";
                        if (!(key in associatedArtifactsNode[0])) key = "Associated Monument, Area or Artefact";
                        self.assets(
                            associatedArtifactsNode.map((x) => {
                                var resource = [];
                                for (const element of (x[key]?.["instance_details"] || [])) {                                                                                                                                     
                                    if (element) {
                                        resource.push({
                                            resourceName: self.getNodeValue(element),
                                            resourceUrl: self.getResourceLink(element),
                                        });
                                    }
                                }
                                const association = self.getNodeValue(x, "association type");
                                const tileid = self.getTileId(x);
                                return { resource, association, tileid };
                            })
                        );
                    } else {
                        const instanceDetails = self.getRawNodeValue(associatedArtifactsNode, "instance_details");
                        if (Array.isArray(instanceDetails)) {
                            const tileid = self.getTileId(associatedArtifactsNode);
                            self.assets(
                                instanceDetails.map((x) => {
                                    const resourceName = self.getNodeValue(x);
                                    const resourceUrl = self.getResourceLink(x);
                                    return { resource: [{ resourceName, resourceUrl }], association: "--", tileid };
                                })
                            );
                        }
                    }
                }

                const associatedActorsNode = self.getRawNodeValue(params.data(), self.dataConfig.actors);
                if (associatedActorsNode && Array.isArray(associatedActorsNode)) {
                    self.actors(
                        associatedActorsNode.map((x) => {
                            const associatedActors = [];
                            const actorInstances = self.getRawNodeValue(x, {
                                testPaths: [["associated actor", "actor", "instance_details"]],
                            });
                            actorInstances?.forEach((element) => {
                                associatedActors.push({
                                    actor: self.getNodeValue(element),
                                    actorLink: self.getResourceLink(element),
                                });
                            });
                            const tileid = self.getTileId(x);
                            return { associatedActors, tileid };
                        })
                    );
                }

                const relatedApplicationArea = self.getRawNodeValue(
                    params.data(), self.dataConfig.relatedApplicationArea,
                    "geometry", "related application area", "instance_details"
                );
                if (Array.isArray(relatedApplicationArea)) {
                    const tileid = self.getTileId(
                        self.getRawNodeValue(params.data(), self.dataConfig.relatedApplicationArea, "geometry", "related application area")
                    );
                    self.applicationArea(
                        relatedApplicationArea.map((x) => {
                            const resource = self.getNodeValue(x);
                            const resourceLink = self.getResourceLink(x);
                            return { resource, resourceLink, tileid };
                        })
                    );
                }

                const translationNode = self.getRawNodeValue(params.data(), self.dataConfig.translation, "instance_details");
                if (Array.isArray(translationNode)) {
                    self.translation(
                        translationNode.map((x) => {
                            const resource = self.getNodeValue(x);
                            const resourceLink = self.getResourceLink(self.getRawNodeValue(x));
                            const tileid = self.getTileId(x);
                            return { resource, resourceLink, tileid };
                        })
                    );
                }

                if (self.dataConfig.period) {
                    const rawPeriodNode = self.getRawNodeValue(params.data(), self.dataConfig.period);
                    if (rawPeriodNode) {
                        const periodNode = Array.isArray(rawPeriodNode) ? rawPeriodNode : [rawPeriodNode];
                        self.period(
                            periodNode.map((x) => {
                                var resource = [];
                                for (const element of x["instance_details"]) {
                                    if (element) {
                                        resource.push({
                                            resourceName: self.getNodeValue(element),
                                            resourceUrl: self.getResourceLink(element),
                                        });
                                    }
                                }
                                const tileid = self.getTileId(x);
                                return { resource, tileid };
                            })
                        );
                    }
                }

                // ─── Condition Reports (reverse relationship) ──────────────────────
                // Condition Reports link TO this Heritage Item via their
                // "Associated Monument / Heritage Item" node, so we query the
                // related-resources API and filter by Condition Report graph ID.
                if (self.dataConfig.conditionReports && self.dataConfig.resourceinstanceid) {
                    const relatedUrl = generateArchesURL("arches:related_resources", { resourceid: self.dataConfig.resourceinstanceid }) + "?paginate=false";
                    $.ajax({ url: relatedUrl })
                        .done(function (response) {
                            const related = Array.isArray(response.related_resources)
                                ? response.related_resources
                                : [];

                            const reports = related
                                .filter(r => r.graph_id === CONDITION_REPORT_GRAPH_ID)
                                .map(r => {
                                    const tiles = r.tiles || [];

                                    // Date - already formatted as "YYYY-MM-DD" in tile data
                                    const date = getNodeFromTiles(tiles, CR_DATE_NODE) || "";

                                    // Summary Type - controlled-list concept
                                    const summaryType = conceptLabel(
                                        getNodeFromTiles(tiles, CR_SUMMARY_TYPE_NODE)
                                    );

                                    // Summary - i18n text
                                    const summary = i18nString(
                                        getNodeFromTiles(tiles, CR_SUMMARY_NODE)
                                    );

                                    // Officer / Report Author - i18n text
                                    const officer = i18nString(
                                        getNodeFromTiles(tiles, CR_OFFICER_NODE)
                                    );

                                    // Condition rating - controlled-list concept
                                    const condition = conceptLabel(
                                        getNodeFromTiles(tiles, CR_CONDITION_NODE)
                                    );

                                    // Occupancy - controlled-list concept
                                    const occupancy = conceptLabel(
                                        getNodeFromTiles(tiles, CR_OCCUPANCY_NODE)
                                    );

                                    // Maintenance - controlled-list concept
                                    const maintenance = conceptLabel(
                                        getNodeFromTiles(tiles, CR_MAINTENANCE_NODE)
                                    );

                                    // Link to the Condition Report
                                    let resourceUrl;
                                    try {
                                        resourceUrl = generateArchesURL("arches:resource_report", {
                                            resourceid: r.resourceinstanceid,
                                        });
                                    } catch (e) {
                                        resourceUrl = `/report/${r.resourceinstanceid}`;
                                    }

                                    return { date, summaryType, summary, officer, condition, occupancy, maintenance, resourceUrl };
                                });

                            self.conditionReports(reports);
                        })
                        .fail(function (xhr, status, error) {
                            console.error("[CR] fetch FAILED:", xhr.status, status, error, relatedUrl);
                        });
                }
            }
        },
        template: ResourcesTemplate,
    }
);
