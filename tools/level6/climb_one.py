"""Climb one W_k bound of one case from a given T upwards (stop at the first non-INFEASIBLE).
usage: nice -n 10 ~/.ccc-venv/bin/python -u climb_one.py <key> <case> <k> <T_from> <T_to> [--secs 1800] [--workers 4]
Appends results to results/level6/close_medium.jsonl (same format as close_medium.py)."""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load
import satmodel
from close_medium import RES

ap = argparse.ArgumentParser()
for name in ('key', 'case', 'k', 't_from', 't_to'):
    ap.add_argument(name)
ap.add_argument('--secs', type=float, default=1800)
ap.add_argument('--workers', type=int, default=4)
a = ap.parse_args()
cases, _ = load(a.key)
r, g, count = cases[int(a.case)]
lg = LineGeo(r, g)
for T in range(int(a.t_from), int(a.t_to) + 1):
    t0 = time.time()
    st, states = satmodel.solve(lg, T, int(a.k), free_start=True, secs=a.secs, workers=a.workers)
    with open(f'{RES}/close_medium.jsonl', 'a') as f:
        f.write(json.dumps(dict(case=int(a.case), k=int(a.k), T=T, status=st,
                                secs=round(time.time() - t0, 1), states=states)) + '\n')
    print(f'case {a.case} W{a.k} at T={T}: {st} ({time.time() - t0:.1f}s)'
          + ('  -> W_k >= %d' % (T + 1) if st == 'INFEASIBLE' else ''), flush=True)
    if st != 'INFEASIBLE':
        break
