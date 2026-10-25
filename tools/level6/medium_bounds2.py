"""Recompute the medium decomposition bounds from every proven result, including satmodel2's.

For each medium case in decomp_2-medium.csv: F_j / W_k lower bounds from decomp_2-medium.csv,
close_medium.jsonl and close_medium2.jsonl (INFEASIBLE rows), closed under superadditivity, then
    lb = max_j  F_j + B(n - j)        (section 3 of docs/level6-theory.md)
together with exact whole-program results (exact_2-medium.csv INFEASIBLE rows, close_medium2 F_n
rows).  Upper bounds: Wub/Fub from decomp and FEASIBLE rows.  Prints a table of the open cases and
writes results/level6/bounds_medium2.csv.
usage: medium_bounds2.py
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import load
from close_medium2 import proven
from bounds import chain
import satmodel2

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')


def main():
    cases, best = load('2-medium')
    rows = {int(r['case']): r for r in csv.DictReader(open(os.path.join(RES, 'decomp_2-medium.csv')))}
    exact = {}
    for r in csv.DictReader(open(os.path.join(RES, 'exact_2-medium.csv'))):
        if r['status'] == 'INFEASIBLE':
            exact[int(r['case'])] = int(r['T']) + 1
    ub = {}
    for fn in ('close_medium.jsonl', 'close_medium2.jsonl'):
        p = os.path.join(RES, fn)
        if os.path.exists(p):
            for line in open(p):
                d = json.loads(line)
                if d['status'] == 'FEASIBLE':
                    key = (d['case'], d.get('kind', 'W'), d['k'])
                    ub[key] = min(ub.get(key, 99999), d['T'])
    out = []
    for c in sorted(rows):
        r = rows[c]
        n = cases[c][2]
        kn = proven(c)
        F, W = satmodel2.closure(kn['F'], kn['W'], n)
        lb = 0
        for j in [0] + sorted(F):
            if j > n:
                continue
            fj = F[j] if j else 0
            lb = max(lb, fj + (chain(W, n - j) if W and n - j > 0 else (n - j)))
        lb = max(lb, exact.get(c, 0), F.get(n, 0))
        Wub = {int(a): b for a, b in json.loads(r['Wub']).items()}
        Fub = {int(a): b for a, b in json.loads(r['Fub']).items()}
        for (cc, kind, k), T in ub.items():
            if cc == c:
                (Wub if kind == 'W' else Fub)[k] = min((Wub if kind == 'W' else Fub).get(k, 99999), T)
        b = len(best[c])
        assert lb <= b, (c, lb, b)          # a bound above a real program = bug
        out.append(dict(case=c, count=n, best=b, lb=lb, gap=b - lb, F=F, W=W, Fub=Fub, Wub=Wub,
                        lb_old=int(r['lb_decomp'])))
    with open(os.path.join(RES, 'bounds_medium2.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['case', 'count', 'best', 'lb_old', 'lb', 'gap', 'F_lb', 'F_ub', 'W_lb', 'W_ub'])
        for d in out:
            w.writerow([d['case'], d['count'], d['best'], d['lb_old'], d['lb'], d['gap'],
                        json.dumps(d['F']), json.dumps(d['Fub']), json.dumps(d['W']), json.dumps(d['Wub'])])
    print(f"{'case':>4} {'n':>3} {'best':>4} {'lb_old':>6} {'lb':>4} {'gap':>3}  F_lb / W_lb (W_ub)")
    for d in out:
        if d['gap'] or d['lb'] != d['lb_old']:
            print(f"{d['case']:4d} {d['count']:3d} {d['best']:4d} {d['lb_old']:6d} {d['lb']:4d} {d['gap']:3d}  "
                  f"F={d['F']} W={d['W']} Wub={d['Wub']}")
    print('open cases:', sum(1 for d in out if d['gap']), ' total gap:', sum(d['gap'] for d in out))


if __name__ == '__main__':
    main()
