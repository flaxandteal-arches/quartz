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

## Custom Monument / Heritage Item Report

The Monument resource model (graph ID `076f9381-7b00-11e9-8d6b-80000b44d1d9`, locally renamed to **Heritage Item**) uses a custom report defined in:

- `quartz/media/js/views/components/reports/monument.js` - overrides the `arches_her` upstream; configures which sections appear in the Resources tab, including a reverse-lookup for linked Condition Reports
- `quartz/media/js/views/components/reports/scenes/resources.js` - overrides the `arches_her` upstream; adds the Condition Reports table (fetched via the related-resources API) and handles data extraction for all associated-resource sections

**If the Monument graph is updated** (new cards added, node names or IDs changed), both files above will likely need updating:

- New cards must be added to `resourceDataConfig` and `resourcesCards` in `monument.js` before they appear in the report
- Node IDs used for Condition Report field extraction are hardcoded at the top of `resources.js` - if the Condition Report graph changes, update the `CR_*_NODE` constants there

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
