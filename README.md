# Welcome to the Arches Project!

Arches is a new, open-source, web-based, geospatial information system for cultural heritage inventory and management. Arches is purpose-built for the international cultural heritage field, and it is designed to record all types of immovable heritage, including archaeological sites, buildings and other historic structures, landscapes, and heritage ensembles or districts.

Please see the [project page](http://archesproject.org/) for more information on the Arches project.

The Arches Installation Guide and Arches User Guide are available [here](http://archesproject.org/documentation/).

# Quartz
Quartz is a demo instance of arches v8.1 beta. It has the arches for HER models installed in an alpha state as the models and package need updating to work with arches v8

# Getting Started
Follow the below instructions for how to get this instance of arches running using the Flax and Teal Arches Container Toolkit which will run the instance within Docker

## Installation

1. First create a directory for you project and navigate into it
```
mkdir quartz && cd quartz
```

2. Clone the repo
```
git clone git@github.com:flaxandteal-arches/quartz.git
```

3. Create a venv for the project, this is mainly for the initial set up of arches
```
python3 -m venv ENV
```

4. Activate the virtual environment
```
source ENV/bin/activate
```

You can check it has activate by checking
```
which python
```
You should see a path to the dir you just created


5. Navigate to the repo and intialise the submodules (arches container toolkit)
```
cd quartz &&
git submodule update --init --recursive
```

6. Build arches
```
make build
```
This will navigate to the folder that contains the make file and run the build command

7. Once the build process has completed run
```
make run
```
To start a local version of arches. Navigate to `localhost:8000` to see the site

7. Load the package with the resource models using the command
```
make manage CMD="packages -o load_package -a arches_her -db -y"
```

8. Login on localhost:8000/auth and go to http://localhost:8000/graph/. Scroll down to find the Monument resource and delete it using the dropdown

9. Run 
```
make manage CMD="packages -o import_graphs -s quartz/pkg/graphs/resource_models/Heritage\ Item.json"
```
This will load in the onotologies and resource models.

10. Download the quartz-graphs package from the latest GitHub release and extract it:
```
mkdir -p tmp
```
```
gh release download -R flaxandteal/quartz-graphs -p "*.zip" --clobber --output tmp/quartz-graphs.zip
```
```
unzip -o tmp/quartz-graphs.zip -d tmp/pkg-quartz-graphs
```

Or if you don't have gh CLI you can just go to `https://github.com/flaxandteal/quartz-graphs/releases` and download the zip for the latest release and unzip it into the `tmp` folder.


11. Load the quartz-graphs package:
```
make manage CMD="packages -o load_package -s /web_root/quartz/tmp/pkg-quartz-graphs -y"
```

## Custom Monument / Heritage Item Report

The Monument resource model (graph ID `076f9381-7b00-11e9-8d6b-80000b44d1d9`, locally renamed to **Heritage Item**) uses a custom report defined in:

- `quartz/media/js/views/components/reports/monument.js` - overrides the `arches_her` upstream; configures which sections appear in the report. Critically, `nameDataConfig` uses the node **display names** (e.g. `"heritage place names"`) not alias-derived strings -- `LabelBasedGraphV2` keys its output by display name, so alias-based lookups silently return nothing.
- `quartz/media/js/utils/report.js` - overrides the `arches_her` upstream; fixes URL generation to use the `"arches:"` Django namespace prefix (`"arches:tile"`, `"arches:resource_editor"`, `"arches:resource_report"`) which the bare names in `arches_her` do not resolve to in this project.
- `quartz/media/js/views/components/reports/scenes/resources.js` - overrides the `arches_her` upstream; adds the Condition Reports table (fetched via the related-resources API) and handles data extraction for all associated-resource sections.
- `quartz/media/js/views/components/reports/scenes/name.js` / `name.htm` - overrides the `arches_her` upstream; adds Heritage Asset References (SMR, IHR, HB, HPG numbers), Display Name flags, and the parent Heritage Place link. The template guards Knockout bindings with `$data.displayName && displayName()` to avoid `ReferenceError` if the wrong viewModel is bound.
- `quartz/media/js/views/components/reports/scenes/assessments.js` - overrides the `arches_her` upstream; adds the Issue Reports section (`issue_report` nodegroup), which `arches_her` has no code to display.
- `quartz/media/js/views/components/reports/scenes/classifications.js` - overrides the `arches_her` upstream; adds Historical Period Type and makes cultural period / producer values into clickable links to their resource reports.
- `quartz/media/js/views/components/reports/scenes/description.js` - overrides the `arches_her` upstream; adds the Designation Descriptions section (`designation_description` nodegroup).
- `quartz/media/js/views/components/reports/scenes/location.js` - overrides the `arches_her` upstream; adds Northern Ireland-specific location identifiers: BU Fusion ID, Unique Building ID, and LP Fusion ID.

**If the Monument graph is updated** (new cards added, node names or IDs changed), the files above will likely need updating:

- New cards must be added to `resourceDataConfig` and `resourcesCards` in `monument.js` before they appear in the report.
- `nameDataConfig` in `monument.js` uses node **display names** as set in the graph editor -- if any node is renamed there, the corresponding string here must be updated to match.
- Node IDs used for Condition Report field extraction are hardcoded at the top of `resources.js` -- if the Condition Report graph changes, update the `CR_*_NODE` constants there.

## Arches Search setup

Both commands need to run after `load_package` (they read graphs/resources, so
they can't be migrations). Re-run them whenever graphs or data change.

### `setup_search_report_configs`
Creates the report configs that control how a search result is displayed (the
detail/result pane). Pass `--overwrite` to replace existing configs.

### `setup_search_filter_configs`
Creates the attribute-filter config (`NodeFilterConfig`) per graph — i.e. which
nodes show up as filters in the search panel. Only `reference` nodes backed by a
controlled list are usable as filters, so that's all it seeds.

Flags:
- `--overwrite` — replace existing configs instead of skipping them.
- `--graph <slug|name>` — limit to one graph (default: all resource graphs).
- `--populated-only` — only include nodes that resources actually fill in (skips
  filters that would always be empty).
- `--max-options N` — skip nodes whose controlled list has more than N items
  (long checkbox lists are slow). Default 25, 0 = no limit.
- `--max-nodes N` — hard cap on filters per graph. Default 0 = no cap.

Duplicate labels are collapsed to one filter (the data model reuses node names
like "Association Type" across nodegroups).

Typical run:

    python manage.py setup_search_report_configs --overwrite
    python manage.py setup_search_filter_configs --overwrite --populated-only


## Production Push
To push to production the images need to be tagged with prod-{run-id}
This can be done using github cli with
```
gh workflow run "Tag images as prod" \
  -f source_tag=main-27012345678 \
  -f bid=27012345678
```
`source` pulls the image that you want to use
`bid` is the id you will tag the prod image with (this will be the same as the image)
