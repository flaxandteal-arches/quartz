#!/bin/sh

CURL="curl -s -H \"Authorization: token $PAT\" https://api.github.com/repos/flaxandteal/quartz-graphs/releases"
RESPONSE=$(eval "$CURL/latest")
name=$(echo "$RESPONSE" | python3 -c "import json; import sys; assets = json.load(sys.stdin)[\"assets\"]; print([a[\"name\"] for a in assets if a[\"name\"].endswith(\".whl\")][0])")
rm -f $name
ASSET_ID=$(echo "$RESPONSE" | python3 -c "import json; import sys; print([a[\"id\"] for a in json.load(sys.stdin)[\"assets\"] if a[\"name\"] == \"$name\"][0])")
eval "$CURL/assets/$ASSET_ID -LJOH 'Accept: application/octet-stream'"
