#!/bin/sh
# Every 2 min for 90 min: pull new friend commits / Actions artifacts, merge per case, submit if better.
L6=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$L6/../.." && pwd); CAND="$L6/candidates"
last_sha=""; seen="$L6/logs/seen_artifacts.txt"; touch "$seen"
end=$(( $(date +%s) + 5400 ))
while [ "$(date +%s)" -lt "$end" ]; do
  new=0
  sha=$(gh api repos/leddis088/CCC2026/commits/main --jq .sha 2>/dev/null | cut -c1-7)
  if [ -n "$sha" ] && [ "$sha" != "$last_sha" ]; then
    for f in 1-small 2-medium 3-large 4-enormous; do
      [ -s "$CAND/gh_${sha}_$f.txt" ] && continue
      gh api -H "Accept: application/vnd.github.raw" "repos/leddis088/CCC2026/contents/classic/Level6/output/out_level-6_$f.txt" > "$CAND/gh_${sha}_$f.txt" 2>/dev/null && new=1
    done
    last_sha=$sha
  fi
  for id in $(gh api repos/leddis088/CCC2026/actions/artifacts --jq '.artifacts[] | select(.expired==false) | .id' 2>/dev/null); do
    grep -qx "$id" "$seen" && continue
    tmp=$(mktemp -d)
    if gh api "repos/leddis088/CCC2026/actions/artifacts/$id/zip" > "$tmp/a.zip" 2>/dev/null; then
      python3 - "$tmp/a.zip" "$CAND" "$id" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
for i in z.infolist():
    n = i.filename.split('/')[-1]
    if n.startswith('out_level-6_') and n.endswith('.txt') and '0-example' not in n:
        open(f"{sys.argv[2]}/art_{sys.argv[3]}_{n}", 'wb').write(z.read(i)); print("  artifact file", n)
PY
      echo "$id" >> "$seen"; new=1
    fi
    rm -rf "$tmp"
  done
  if [ "$new" = 1 ]; then
    echo "$(date +%H:%M:%S) new data (commit $sha) -> merging"
    cd "$REPO" && cargo ccc best 6 2>&1 | grep "out_level-6"
    cargo ccc submit 6 --yes 2>&1 | grep -E "CORRECT|WRONG|unchanged|rror" | sed 's/,"level".*optimizationScore/ … optimizationScore/'
  else
    echo "$(date +%H:%M:%S) nothing new (commit $sha)"
  fi
  sleep 120
done
echo "$(date +%H:%M:%S) watcher finished"
