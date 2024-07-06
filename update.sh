#!/usr/bin/env bash
set -euo pipefail
curl -f https://www.vierdaagsefeesten.nl/api/all -o all.json
python index.py all.json ~/public/4d_all.xml
python index.py all.json ~/public/4d_valkhof.xml --only-interesting
~/public/sync.sh
