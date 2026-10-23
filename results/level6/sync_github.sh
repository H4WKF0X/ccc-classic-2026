#!/bin/sh
# Pull the friend's latest Level 6 outputs from GitHub and merge them per case into our best.
set -e
cd "$(dirname "$0")/candidates"
sha=$(gh api repos/leddis088/CCC2026/commits/main --jq .sha | cut -c1-7)
for f in 1-small 2-medium 3-large 4-enormous; do
  [ -s "gh_${sha}_$f.txt" ] || gh api -H "Accept: application/vnd.github.raw" \
    "repos/leddis088/CCC2026/contents/classic/Level6/output/out_level-6_$f.txt" > "gh_${sha}_$f.txt"
done
echo "synced commit $sha"
cd ../../.. && cargo ccc best 6 2>&1 | grep "out_level-6"
