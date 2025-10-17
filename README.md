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
cd quartz && 
make build
```
This will navigate to the folder that contains the make file and run the build command

7. Once the build process has completed run
```
make run
```
To start a local version of arches. Navigate to `localhost:8000` to see the site


