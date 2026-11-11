#!/usr/bin/env bash
# Reload the Heritage Item Type list with comma categories built as parents.
# Values on the dropped flat "Category,Type" items are remapped by 0004.
set -euo pipefail

python manage.py packages -o import_controlled_lists \
    -s scripts/data_fixes/0002_heritage_item_type.xml -ow overwrite
