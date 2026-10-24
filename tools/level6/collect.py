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
from lines import KEYS, LineGeo, load, simulate
from multi_cycles import det_ticks_of
from bounds import chain

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
            first = det_ticks_of(lg.geo, p)[0]
            first_lb = rest_lb = ''
            if d:
                F, W = d['F'], d['W']
                Fd = {int(k): v for k, v in json.loads(F).items()}
                Wd = {int(k): v for k, v in json.loads(W).items()}
                first_lb = Fd.get(1, '')
                rest_lb = chain(Wd, c - 1) if Wd else (0 if c == 1 else '')
                if int(d['lb_decomp']) > lb:
                    lb, how = int(d['lb_decomp']), 'decomp'
                    opt = lb == b
            found = ''
            for src in (os.path.join(RES, 'exact_programs', f'{key}_{i}.txt'),
                        os.path.join(RES, 'improved', f'{key}_{i}.txt')):
                if os.path.exists(src):
                    q = [l.split() for l in open(src) if l.strip()]
                    if simulate(lg.geo, q, c) == len(q) and len(q) < b and (found == '' or len(q) < found):
                        found = len(q)
            nb = found if found != '' else b          # best known after this research
            assert lb <= nb, (key, i, lb, nb)         # a bound above a real program = bug
            opt = lb == nb
            out.append(dict(file=key, case=i, R=r, count=c, cells=len(lg.S), halo=len(lg.K), best=b, lb=lb,
                            best_new=nb, gap=nb - lb, proven_optimal=int(opt), method=how,
                            exact_status=e['status'] if e else '', exact_secs=e['secs'] if e else '',
                            shorter_found=found, F_lb=F, W_lb=W, first_best=first,
                            first_lb=first_lb, rest_best=b - first, rest_lb=rest_lb))
    path = os.path.join(RES, 'bounds.csv')
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    hdr = f'{"file":12s} {"cases":>5s} {"best":>6s} {"new":>6s} {"lb":>6s} {"gap":>5s} {"optimal":>8s}'
    print(hdr)
    groups = [(k, [o for o in out if o['file'] == k]) for k in KEYS]
    groups.append(('scored', [o for o in out if o['file'] != '1-small']))
    for key, rs in groups:
        print(f'{key:12s} {len(rs):5d} {sum(o["best"] for o in rs):6d} {sum(o["best_new"] for o in rs):6d} '
              f'{sum(o["lb"] for o in rs):6d} {sum(o["gap"] for o in rs):5d} '
              f'{sum(o["proven_optimal"] for o in rs):8d}')
    print('largest gaps:')
    for o in sorted(out, key=lambda o: -o['gap'])[:25]:
        print(f"  {o['file']} case {o['case']:3d} R={o['R']} n={o['count']} cells={o['cells']} "
              f"best={o['best_new']} lb={o['lb']} gap={o['gap']} ({o['method']})")
    print(f'wrote {path}')


if __name__ == '__main__':
    main()
