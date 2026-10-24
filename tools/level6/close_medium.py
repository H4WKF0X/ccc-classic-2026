"""Close the remaining medium gaps with decisive W_k solves.

W_k = fewest ticks for k consecutive copies starting from ANY emitter configuration (pattern + halo
empty).  For each open case and k we ask CP-SAT: "k copies in T = W_k_ub - 1 ticks, possible?"
  * INFEASIBLE -> W_k >= W_k_ub: the lower bound rises.  Plugged into the decomposition
    OPT >= F_j + B(n-j) this can prove our program optimal.
  * FEASIBLE   -> a cheaper k-copy chain exists: the template for a shorter program.
Each result is appended as one JSON line to results/level6/close_medium.jsonl (resumable).

usage: nice -n 10 ~/.ccc-venv/bin/python -u close_medium.py --cases 50,58 --ks 2,3,4 --secs 1800 --workers 4
"""
import argparse, csv, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load
import satmodel

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')


def decomp_row(case):
    for r in csv.DictReader(open(f'{RES}/decomp_2-medium.csv')):
        if r['case'] == str(case):
            return r
    raise KeyError(case)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', required=True)
    ap.add_argument('--ks', default='2,3,4')
    ap.add_argument('--secs', type=float, default=1800)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--climb', action='store_true', help='ask T = lb, lb+1, ... upwards (cheap refutations first)')
    a = ap.parse_args()
    cases, best = load('2-medium')
    out = f'{RES}/close_medium.jsonl'
    done = set()
    if os.path.exists(out):
        for line in open(out):
            d = json.loads(line); done.add((d['case'], d['k'], d['T']))
    for case in [int(c) for c in a.cases.split(',')]:
        r, g, count = cases[case]
        lg = LineGeo(r, g)
        row = decomp_row(case)
        wub = {int(k): v for k, v in json.loads(row['Wub']).items()}
        wlb = {int(k): v for k, v in json.loads(row['W']).items()}
        for k in [int(x) for x in a.ks.split(',')]:
            if k not in wub or k > count - 1:
                continue
            Ts = range(wlb.get(k, 0), wub[k]) if a.climb else [wub[k] - 1]
            for T in Ts:
                if (case, k, T) in done:
                    continue
                t0 = time.time()
                st, states = satmodel.solve(lg, T, k, free_start=True, secs=a.secs, workers=a.workers)
                rec = dict(case=case, k=k, T=T, status=st, secs=round(time.time() - t0, 1),
                           states=states if states else None)
                with open(out, 'a') as f:
                    f.write(json.dumps(rec) + '\n')
                print(f'case {case} W{k} at T={T}: {st} ({rec["secs"]}s)'
                      + ('  -> W_k >= %d' % (T + 1) if st == 'INFEASIBLE' else ''), flush=True)
                if st != 'INFEASIBLE':
                    break


if __name__ == '__main__':
    main()
