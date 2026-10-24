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


def markdown():
    """Markdown tables for docs/level6-theory.md (run after main())."""
    rs = list(csv.DictReader(open(os.path.join(RES, 'bounds.csv'))))
    for r in rs:
        for k in ('best', 'best_new', 'lb', 'gap', 'proven_optimal', 'count', 'cells', 'R'):
            r[k] = int(r[k])
    print('| file | cases | best (work/level6/best) | best incl. this research | lower bound | gap | proven optimal |')
    print('|---|---:|---:|---:|---:|---:|---:|')
    groups = [(k, [r for r in rs if r['file'] == k]) for k in KEYS]
    groups.append(('**scored (2+3+4)**', [r for r in rs if r['file'] != '1-small']))
    groups.append(('scored without enormous', [r for r in rs if r['file'] in ('2-medium', '3-large')]))
    for k, g in groups:
        print(f'| {k} | {len(g)} | {sum(r["best"] for r in g)} | {sum(r["best_new"] for r in g)} | '
              f'{sum(r["lb"] for r in g)} | {sum(r["gap"] for r in g)} | {sum(r["proven_optimal"] for r in g)} |')
    print()
    for k in ('2-medium', '3-large'):
        g = [r for r in rs if r['file'] == k and r['gap'] > 0 and r['first_lb'] != '' and r['rest_lb'] != '']
        fg = sum(int(r['first_best']) - int(r['first_lb']) for r in g)
        rg = sum(int(r['rest_best']) - int(r['rest_lb']) for r in g)
        print(f'{k}: {len(g)} open cases; first-copy slack (first_best - F1) = {fg}, '
              f'later-copies slack (rest_best - B(n-1)) = {rg}')
        buckets = {}
        for r in [r for r in rs if r['file'] == k]:
            b = '0' if r['gap'] == 0 else '1-2' if r['gap'] <= 2 else '3-9' if r['gap'] <= 9 else \
                '10-29' if r['gap'] <= 29 else '30+'
            buckets.setdefault(b, [0, 0])
            buckets[b][0] += 1
            buckets[b][1] += r['gap']
        print('  gap histogram (cases, summed gap):', {b: tuple(v) for b, v in sorted(buckets.items())})
    print()
    print('| file | case | R | count | cells | best | lb | gap | F1 lb / first copy in best | later copies: bound / best |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---|---|')
    for r in sorted([r for r in rs if r['file'] != '4-enormous'], key=lambda r: -r['gap'])[:25]:
        print(f'| {r["file"]} | {r["case"]} | {r["R"]} | {r["count"]} | {r["cells"]} | {r["best_new"]} | {r["lb"]} | '
              f'{r["gap"]} | {r["first_lb"]} / {r["first_best"]} | {r["rest_lb"]} / {r["rest_best"]} |')


if __name__ == '__main__' and '--md' in sys.argv:
    markdown()
