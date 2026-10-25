"""Follow a `measure` output file and print each program that is shorter than our current best.

usage: ~/.ccc-venv/bin/python -u tools/level6/watch_wins.py work/level6/measure/w500k_out.txt
Also prints "progress: N done" every 10 finished attempts.  Wins are written to
results/level6/improved/<key>_<case>.txt (merge with merge_improved.py).
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate

path = sys.argv[1]
data = {k: load(k) for k in ('2-medium', '3-large', '4-enormous')}
RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')
seen = 0
while True:
    lines = open(path).read().splitlines() if os.path.exists(path) else []
    for line in lines[seen:]:
        k, c, w, secs, *p = line.split()
        c = int(c); seen += 1
        if seen % 10 == 0:
            print(f'progress: {seen} done', flush=True)
        if not p:
            continue
        prog = [list(l) for l in p[0].split(';')]
        cases, best = data[k]
        imp = f'{RES}/improved/{k}_{c}.txt'
        cur = len(best[c])
        if os.path.exists(imp):
            cur = min(cur, sum(1 for l in open(imp) if l.strip()))
        if len(prog) < cur:
            r, g, n = cases[c]
            if simulate(LineGeo(r, g).geo, prog, n) == len(prog):
                with open(imp, 'w') as o:
                    o.write('\n'.join(' '.join(l) for l in prog) + '\n')
                print(f'WIN {k} case {c}: {cur} -> {len(prog)} (width {w}, {secs}s)', flush=True)
    time.sleep(30)
