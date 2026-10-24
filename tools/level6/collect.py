"""Merge the per-file results of exact.py (exact_<key>.csv) and bounds.py (decomp_<key>.csv) into
results/level6/bounds.csv and print per-file totals and the cases with the largest gap.

lb per case = max of
  * count                       (every copy needs >= 1 line -- trivial),
  * best  if exact.py proved INFEASIBLE at best-1 (=> proven optimal),
  * lb_decomp from bounds.py    (F_j + chained W_k decomposition, see bounds.py),
  * T+1 for any exact INFEASIBLE at T.
Every lb is checked to be <= best (a violation would mean a bug in the model).
usage: python3 collect.py
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import KEYS, LineGeo, load

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, 'results', 'level6')


def read(path):
    if not os.path.exists(path):
        return {}
    rows = {}
    for r in csv.DictReader(open(path)):
        rows[int(r['case'])] = r          # later rows (re-runs) win
    return rows


def main():
    out = []
    for key in KEYS:
        cases, best = load(key)
        ex = read(os.path.join(RES, f'exact_{key}.csv'))
        de = read(os.path.join(RES, f'decomp_{key}.csv'))
        for i, ((r, g, c), p) in enumerate(zip(cases, best)):
            lg = LineGeo(r, g)
            b = len(p)
            lb, how, opt = c, 'trivial', False
            e = ex.get(i)
            if e and e['status'] == 'INFEASIBLE' and int(e['T']) + 1 > lb:
                lb, how = int(e['T']) + 1, 'exact'
                opt = lb == b
            d = de.get(i)
            F = W = ''
            if d:
                F, W = d['F'], d['W']
                if int(d['lb_decomp']) > lb:
                    lb, how = int(d['lb_decomp']), 'decomp'
                    opt = lb == b
            assert lb <= b, (key, i, lb, b)
            found = e['found'] if e and e['found'] else ''
            out.append(dict(file=key, case=i, R=r, count=c, cells=len(lg.S), halo=len(lg.K), best=b, lb=lb,
                            gap=b - lb, proven_optimal=int(opt), method=how,
                            exact_status=e['status'] if e else '', exact_secs=e['secs'] if e else '',
                            shorter_found=found, F_lb=F, W_lb=W))
    path = os.path.join(RES, 'bounds.csv')
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f'{"file":12s} {"cases":>5s} {"best":>6s} {"lb":>6s} {"gap":>5s} {"optimal":>8s}')
    for key in KEYS:
        rs = [o for o in out if o['file'] == key]
        print(f'{key:12s} {len(rs):5d} {sum(o["best"] for o in rs):6d} {sum(o["lb"] for o in rs):6d} '
              f'{sum(o["gap"] for o in rs):5d} {sum(o["proven_optimal"] for o in rs):8d}')
    sc = [o for o in out if o['file'] != '1-small']
    print(f'{"scored":12s} {len(sc):5d} {sum(o["best"] for o in sc):6d} {sum(o["lb"] for o in sc):6d} '
          f'{sum(o["gap"] for o in sc):5d} {sum(o["proven_optimal"] for o in sc):8d}')
    print('largest gaps:')
    for o in sorted(out, key=lambda o: -o['gap'])[:25]:
        print(f"  {o['file']} case {o['case']:3d} R={o['R']} n={o['count']} cells={o['cells']} "
              f"best={o['best']} lb={o['lb']} gap={o['gap']} ({o['method']})")
    print(f'wrote {path}')


if __name__ == '__main__':
    main()
