#!/bin/sh
# Progress of level-6 optimisation runs + current best per file.
cd "$(dirname "$0")/.."
for log in logs/*.log; do
  [ -f "$log" ] || continue
  echo "== $(basename "$log")  (last write $(date -r "$log" +%H:%M:%S))"
  for n in 10 210 190 140; do
    case $n in 10) f=small;; 210) f=medium;; 190) f=large;; 140) f=enormous;; esac
    last=$(grep "progress n=$n " "$log" | tail -1)
    [ -n "$last" ] && echo "   $f: $(echo "$last" | sed 's/.*progress n=[0-9]* \([0-9]*\/[0-9]*\).*(\([0-9]*s\))/\1 patterns done, \2 elapsed/')"
  done
  grep -E "out_level-6_.*(score|lines)" "$log" | tail -4 | sed 's/^/   /'
done
echo "== best so far (work/level6/best)"
python3 /tmp/claude-1000/-home-max-projects-ccc-school/05b5dedd-149d-4fa0-a839-b3d2a47a9fe4/scratchpad/l6score.py in/in_level-6_1-small.txt best/out_level-6_1-small.txt >/dev/null 2>&1
for f in 1-small 2-medium 3-large 4-enormous; do
  printf "   %-10s %s lines\n" $f "$(awk 'NF' best/out_level-6_$f.txt | wc -l)"
done
