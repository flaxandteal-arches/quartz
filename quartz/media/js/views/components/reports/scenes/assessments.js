import _ from "underscore";
import ko from "knockout";
import arches from "arches";
import reportUtils from "utils/report";
import AssessmentsTemplate from "templates/views/components/reports/scenes/assessments.htm";
import "bindings/datatable";
import "bindings/reports";

export default ko.components.register(
    "views/components/reports/scenes/assessments",
    {
        viewModel: function (params) {
            const self = this;
            Object.assign(self, reportUtils);

            self.scientificDatesTableConfig = {
                ...this.defaultTableConfig,
                columns: Array(13).fill(null),
            };

            self.artefactConditionConfig = {
                ...this.defaultTableConfig,
                columns: Array(5).fill(null),
            };

            self.auditMetadataTableConfig = {
                ...this.defaultTableConfig,
                columns: Array(7).fill(null),
            };

            self.dataConfig = {
                scientificDate: "scientific date assignment",
                artefactConditin: undefined,
                auditMetadata: "audit metadata",
            };

            self.cards = Object.assign({}, params.cards);
            self.resource = params?.data || undefined;
            self.edit = params.editTile || self.editTile;
            self.delete = params.deleteTile || self.deleteTile;
            self.add = params.addTile || self.addNewTile;
            self.scientificDate = ko.observable();
            self.artefactCondition = ko.observableArray();
            self.auditMetadata = ko.observableArray();
            self.visible = {
                scientificDate: ko.observable(true),
                artefactCondition: ko.observable(true),
                auditMetadata: ko.observable(true),
            };
            Object.assign(self.dataConfig, params.dataConfig || {});

            if (!params?.compiled) {
                const scientificDate = self.getRawNodeValue(
                    params.data(),
                    self.dataConfig.scientificDate
                );
                if (Array.isArray(scientificDate)) {
                    self.scientificDate(
                        scientificDate.map((x) => {
                            const constructionPhase = self.getNodeValue(x, "associated construction phase");
                            const dateDeterminationQualifier = self.getNodeValue(x, "when determined", "when determined date qualifier");
                            const dateQualifier = self.getNodeValue(x, "scientific date timespan", "scientific date qualifier");
                            const datingMethod = self.getNodeValue(x, "dating method");
                            const earliestDate = self.getNodeValue(x, "scientific date timespan", "scientific date start date");
                            const endDateOfDetermination = self.getNodeValue(x, "when determined", "when determined end date");
                            const generalNote = self.getRawNodeValue(x, "notes", "note", "@display_value");
                            const laboratoryNote = self.getNodeValue(x, "laboratory references", "laboratory reference");
                            const latestDate = self.getNodeValue(x, "scientific date timespan", "scientific date end date");
                            const standardDeviation = self.getNodeValue(x, "standard deviation", "standard deviation value");
                            const standardDeviationComment = self.getRawNodeValue(x, "standard deviation", "standard deviation notes", "standard deviation note", "@display_value");
                            const startDateOfDetermination = self.getNodeValue(x, "when determined", "when determined start date");
                            const tileid = self.getTileId(x);
                            return { constructionPhase, dateDeterminationQualifier, dateQualifier, datingMethod, earliestDate, endDateOfDetermination, generalNote, laboratoryNote, latestDate, standardDeviation, standardDeviationComment, startDateOfDetermination, tileid };
                        })
                    );
                }

                const artefactConditionNode = self.getRawNodeValue(params.data(), self.dataConfig.artefactCondition);
                if (Array.isArray(artefactConditionNode)) {
                    self.artefactCondition(
                        artefactConditionNode.map((x) => {
                            const type = self.getNodeValue(x, "condition state", "condition type");
                            const file = self.getNodeValue(x, "condition state", "digital file(s)");
                            const startDate = self.getNodeValue(x, "condition timespan", "date of assessment start");
                            const endDate = self.getNodeValue(x, "condition timespan", "date of assessment end");
                            const tileid = self.getTileId(x);
                            return { type, file, endDate, startDate, tileid };
                        })
                    );
                }

                if (self.dataConfig.auditMetadata) {
                    const auditMetadataNode = self.getRawNodeValue(
                        params.data(),
                        self.dataConfig.auditMetadata
                    );
                    if (auditMetadataNode) {
                        const createdBy = self.getNodeValue(auditMetadataNode, "audit creation", "creator", "creator names", "creator name");
                        const creationDate = self.getNodeValue(auditMetadataNode, "audit creation", "creation timespan", "creation date");
                        const updatedBy = self.getNodeValue(auditMetadataNode, "audit update", "updater", "updater names", "updater name");
                        const updateDate = self.getNodeValue(auditMetadataNode, "audit update", "update timespan", "date of last update");
                        const validationStatus = self.getNodeValue(auditMetadataNode, "validation");
                        const auditNote = self.getNodeValue(auditMetadataNode, "audit notes", "audit note");
                        const tileid = self.getTileId(auditMetadataNode);
                        self.auditMetadata([
                            { createdBy, creationDate, updatedBy, updateDate, validationStatus, auditNote, tileid },
                        ]);
                    }
                }
            }
        },
        template: AssessmentsTemplate,
    }
);
