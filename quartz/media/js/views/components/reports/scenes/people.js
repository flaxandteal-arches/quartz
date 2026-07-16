import ko from "knockout";
import reportUtils from "utils/report";
import PeopleTemplate from "templates/views/components/reports/scenes/people.htm";
import "bindings/datatable";
import "bindings/reports";

export default ko.components.register(
    "views/components/reports/scenes/people",
    {
        viewModel: function (params) {
            const self = this;
            Object.assign(self, reportUtils);

            self.dataConfig = {
                people: "associated actors",
            };
            Object.assign(self.dataConfig, params.dataConfig || {});

            self.cards = Object.assign({}, params.cards);
            self.resource = params?.data || undefined;
            self.edit = params.editTile || self.editTile;
            self.delete = params.deleteTile || self.deleteTile;
            self.add = params.addTile || self.addNewTile;

            self.visible = {
                people: ko.observable(true),
            };

            self.peopleTableConfig = {
                ...self.defaultTableConfig,
                paging: true,
                searching: true,
                columns: Array(7).fill(null),
            };

            self.people = ko.observableArray();

            if (!params?.compiled) {
                const associatedPeopleNode = self.getRawNodeValue(params.data(), self.dataConfig.people);
                if (associatedPeopleNode && Array.isArray(associatedPeopleNode)) {
                    self.people(
                        associatedPeopleNode.map((x) => {
                            const actorNode = self.getRawNodeValue(x, "associated actor", "actor");
                            const actor = self.getNodeValue(actorNode);
                            // When multiple people/organizations are selected on a single
                            // association, Arches' label-based graph only exposes one
                            // resourceId for the whole (comma-joined) display value, so a
                            // link built from it points at an arbitrary/wrong entry. Only
                            // link when there's a single actor.
                            const actorLink = actor && actor.includes(", ") ? undefined : self.getResourceLink(actorNode);
                            const associationType = self.getNodeValue(x, "association type");
                            const role = self.getNodeValue(x, "associated actor", "role type");
                            const startOfRole = self.getNodeValue(x, "associated actor", "associated actor timespan", "associated actor start date");
                            const endOfRole = self.getNodeValue(x, "associated actor", "associated actor timespan", "associated actor end date");
                            const displayDate = self.getNodeValue(x, "associated actor", "associated actor timespan", "associated actor display date");
                            const dateQualifier = self.getNodeValue(x, "associated actor", "associated actor timespan", "associated actor date qualifier");
                            const tileid = self.getTileId(x);
                            return { actor, actorLink, associationType, role, startOfRole, endOfRole, displayDate, dateQualifier, tileid };
                        })
                    );
                }
            }
        },
        template: PeopleTemplate,
    }
);
