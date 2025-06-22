#!/usr/bin/env bash
set -euo pipefail
curl -f https://www.vierdaagsefeesten.nl/api/all -o all.json
python index.py all.json ~/public/4d_2025_all.xml
python index.py all.json ~/public/4d_2025_valkhof.xml --only-interesting --name "Vierdaagsefeesten 2025 (valkhof)"
~/public/sync.sh
