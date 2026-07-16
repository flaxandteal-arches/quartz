import $ from "jquery";
import _ from "underscore";
import ko from "knockout";
import arches from "arches";
import resourceUtils from "utils/resource";
import reportUtils from "utils/report";
import MonumentTemplate from "templates/views/components/reports/monument.htm";
import "views/components/reports/scenes/name";
import "views/components/reports/scenes/json";
import "views/components/reports/scenes/people";
import "views/components/reports/scenes/protection";
import "views/components/reports/scenes/resources";
import "bindings/reports";

export default ko.components.register("monument-report", {
    viewModel: function (params) {
        var self = this;
        params.configKeys = ["tabs", "activeTabIndex"];
        this.configForm = params.configForm || false;
        this.configType = params.configType || "header";

        Object.assign(self, reportUtils);
        self.sections = [
            { id: "name", title: "Names and Identifiers" },
            { id: "description", title: "Descriptions and Citations" },
            { id: "classifications", title: "Classifications and Dating" },
            { id: "location", title: "Location Data" },
            { id: "protection", title: "Designation and Protection Status" },
            { id: "assessments", title: "Assessments" },
            { id: "images", title: "Images" },
            { id: "people", title: "Associated People and Organizations" },
            { id: "resources", title: "Associated Resources" },
            { id: "json", title: "JSON" },
        ];

        self.reportMetadata = ko.observable(params.report?.report_json);
        self.resource = ko.observable(self.reportMetadata()?.resource);
        self.displayname = ko.observable(
            ko.unwrap(self.reportMetadata)?.displayname
        );
        self.activeSection = ko.observable("name");

        self.nameDataConfig = {
            name: "heritage place names",
            nameChildren: "heritage item",
            parent: "parent heritage place or area",
            versioning: "versioning",
        };

        self.classificationDataConfig = {
            production: "construction phases",
            components: "components",
            usePhase: "use phases",
            recordType: "record type",
            heritagePlaceMetatype: "heritage place metatype",
        };

        self.descriptionDataConfig = {
            citation: "bibliographic source citation",
        };

        self.resourceDataConfig = {
            files: "digital file(s)",
            activities: "associated activities",
            consultations: "associated consultations",
            assets: "associated monuments, areas and artefacts",
            period: undefined,
            actors: undefined,
            archive: "associated archives",
            // Flag to enable reverse-lookup of Condition Reports linked to this Heritage Item
            conditionReports: true,
            resourceinstanceid: ko.unwrap(self.reportMetadata)
                ?.resourceinstanceid,
        };

        self.nameCards = {};
        self.descriptionCards = {};
        self.classificationCards = {};
        self.scientificDateCards = {};
        self.assessmentCards = {};
        self.imagesCards = {};
        self.locationCards = {};
        self.protectionCards = {};
        self.peopleCards = {};
        self.resourcesCards = {};
        self.summary = params.summary;
        self.cards = {};

        if (params.report.cards) {
            const cards = params.report.cards;

            self.cards = self.createCardDictionary(cards);

            self.nameCards = {
                name: self.cards?.["heritage place names"],
                externalCrossReferences:
                    self.cards?.["external cross references"],
                systemReferenceNumbers:
                    self.cards?.["system reference numbers"],
                parent: self.cards?.["parent heritage place or area"],
                versioning: self.cards?.["versioning"],
            };

            self.descriptionCards = {
                descriptions: self.cards?.["descriptions"],
                citation: self.cards?.["bibliographic source citation"],
            };

            self.classificationCards = {
                production: self.cards?.["construction phases"],
                components: self.cards?.["components"],
                usePhase: self.cards?.["use phase"],
                recordType: self.cards?.["record type"],
                heritagePlaceMetatype: self.cards?.["heritage place metatype"],
            };

            self.assessmentCards = {
                scientificDate: self.cards?.["scientific date assignment"],
                auditMetadata: self.cards?.["audit metadata"],
            };

            self.imagesCards = {
                images: self.cards?.["photographs"],
            };

            self.peopleCards = {
                people: self.cards?.["associated people and organizations"],
            };

            self.resourcesCards = {
                activities: self.cards?.["associated activities"],
                archive: self.cards?.["associated archives"],
                consultations: self.cards?.["associated consultations"],
                files: self.cards?.["associated digital file(s)"],
                assets: self.cards?.[
                    "associated monuments, areas and artefacts"
                ],
            };

            self.locationCards = {
                location: {
                    card: self.cards?.["location data"],
                    subCards: {
                        addresses: "addresses",
                        nationalGrid: "national grid references",
                        administrativeAreas: "localities/administrative areas",
                        locationDescriptions: "location descriptions",
                        areaAssignment: "area assignments",
                        landUse: "land use classification assignment",
                        locationGeometry: "geometry",
                        namedLocations: "named locations",
                    },
                },
            };

            self.protectionCards = {
                designations:
                    self.cards?.["designation and protection assignment"],
            };

            Object.assign(self.protectionCards, self.locationCards);
        }
    },
    template: MonumentTemplate,
});
