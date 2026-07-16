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
- `quartz/media/js/views/components/reports/scenes/name.js` / `name.htm` - overrides the `arches_her` upstream
- `quartz/media/js/views/components/reports/scenes/assessments.js` - overrides the `arches_her`
- `quartz/media/js/views/components/reports/scenes/classifications.js` - overrides the `arches_her` upstream
- `quartz/media/js/views/components/reports/scenes/description.js` - overrides the `arches_her` upstream
- `quartz/media/js/views/components/reports/scenes/location.js` - overrides the `arches_her` upstream
- `quartz/media/js/views/components/reports/scenes/people.js` / `people.htm` - overrides the `arches_her` upstream; adds the Association Type, Role Type, and association start/end/display date/qualifier columns to the "Associated People and Organizations" tab
- `quartz/media/js/views/components/reports/scenes/protection.js` / `protection.htm` - overrides the `arches_her` upstream; adds Designation Name Use Type, Local Heritage List Criteria Type, and Digital File(s) columns to the "Designation/Protection Details" table

**Overriding an `arches_her` scene requires two things, not just dropping the file in place:**
1. An explicit `import "views/components/reports/scenes/<name>";` in `monument.js` (see the list at the top of that file). Scene components with no `arches_her` equivalent (e.g. `location`, `classifications`, `description`, `assessments`) are picked up automatically; scenes that also exist upstream (e.g. `people`, `protection`, `resources`, `name`, `json`) need the static import to reliably win the module-registration race against the upstream copy. Without it, the *template* still resolves to quartz's override (template lookup always prefers the project app), but the *viewModel* can end up being whichever copy's `ko.components.register` call happened to run, silently mismatching data shapes.
2. After adding a **new** static import to `monument.js`, clear the stale webpack filesystem cache before rebuilding (`rm -rf node_modules/.cache/webpack node_modules/.cache/babel-loader`), since the build can otherwise silently fail to re-link the dependency graph and the whole report breaks with `Unknown component 'monument-report'`. `CleanWebpackPlugin` only cleans the output directory, not this cache.

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



## Docker settings

All runtime configuration is driven from a single file, `docker/.env`. It is
loaded once and injected into every arches container (`arches`, `arches_api`,
`arches_worker` and `cantaloupe`) via a shared `env_file` anchor in
`docker/docker-compose.yml`, so any variable you add there applies across all
containers without editing the compose file. Values may reference earlier ones
with `${VAR}` — this is how Cantaloupe reuses the Azure account settings.

`docker/.env` is gitignored (it holds credentials). The minimum setup for
running locally is just a couple of values:

```bash
# Minimum local setup
UPLOADED_FILES_DIR=uploadedfiles
MAPBOX_API_KEY=add mapbox key
```

To develop against a local, editable copy of arches (mounted from `../arches`)
rather than the packaged version, also set `EDITABLE_BASE=True` — the image
build then installs that checkout as an editable dependency. (Likewise
`USE_LOCAL_APPS=true` uses the local `../arches_apps` checkouts.)

To back uploads with Azure blob storage instead of the local disk, see
**Cantaloupe setup → Azure blob storage** below.

## Cantaloupe setup

Cantaloupe is the IIIF image server. It starts automatically as a Docker service
(`cantaloupe`, port `8182`) — there are no manual steps to run it. It can serve
images from two backends, chosen with `CANTALOUPE_SOURCE_STATIC`.

### Azure blob storage (shared / deployed environments)

We store uploaded images in an Azure storage account, and Cantaloupe reads from
the same container. Set the following in `docker/.env`:

- `AZURE_ACCOUNT_NAME`, `AZURE_ACCOUNT_KEY`, `AZURE_CONTAINER` — the storage
  account and container Django writes uploads to.
- `AZURE_URL_EXPIRATION_SECS` — signed-URL lifetime in seconds (default `3600`).
- `USE_LOCAL_STORAGE=False` — the default; Django uploads to Azure whenever the
  `AZURE_*` credentials are present. You only need to set this to `True` to
  force local storage while credentials are configured.
- `CANTALOUPE_SOURCE_STATIC=AzureStorageSource` and the four
  `CANTALOUPE_AZURESTORAGESOURCE_*` keys, which reuse the `AZURE_*` values via
  `${...}` (see the example below).

Example `docker/.env` block:

```bash
# Azure account — the single source of truth
AZURE_ACCOUNT_NAME=add account name
AZURE_ACCOUNT_KEY=add account key
AZURE_CONTAINER=add account container
AZURE_URL_EXPIRATION_SECS=3600

# Cantaloupe Azure source — reuses the values above
USE_LOCAL_STORAGE=False
CANTALOUPE_SOURCE_STATIC=AzureStorageSource
CANTALOUPE_AZURESTORAGESOURCE_ACCOUNT_NAME=${AZURE_ACCOUNT_NAME}
CANTALOUPE_AZURESTORAGESOURCE_ACCOUNT_KEY=${AZURE_ACCOUNT_KEY}
CANTALOUPE_AZURESTORAGESOURCE_CONTAINER_NAME=${AZURE_CONTAINER}
CANTALOUPE_AZURESTORAGESOURCE_LOOKUP_STRATEGY=BasicLookupStrategy
```

### Local filesystem (running entirely locally)

Azure does **not** have to be configured to run locally — leave the `AZURE_*`
keys unset and images are served straight from disk. In this mode:

- With no `AZURE_*` credentials set, Django falls back to local disk storage
  automatically. (If your `.env` *does* carry Azure credentials but you want
  local storage, set `USE_LOCAL_STORAGE=True`.)
- `CANTALOUPE_SOURCE_STATIC=FilesystemSource` — this is the default, so it can
  also be omitted.
- `UPLOADED_FILES_DIR=uploadedfiles` — uploads must land in the `uploadedfiles`
  directory, which is the host folder Cantaloupe serves (bind-mounted into the
  container at `/imageroot`). If this doesn't point at `uploadedfiles`, images
  upload but won't display. 
  **This needs to remain as an empty string `""` in quartz/settings.py, this is a limitation of file routing when using the Azure Storage**

In short: **local development needs no Azure configuration** — but you need to set `USE_LOCAL_STORAGE=True`. This defaults to `False` so that no changes are needed in staging and production environments.


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
