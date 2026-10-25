"""Direct attack: is there a whole program with best-1 lines?  (satmodel2, real start, all copies)

For each open case (best > proven lb) one solve of F_n at T = best-1, with every proven bound as
`known` and the current best program as a solution hint:
  FEASIBLE   -> a shorter program: replayed, saved to results/level6/improved/<key>_<case>.txt
                (merge with merge_improved.py) and asked again at the new best-1;
  INFEASIBLE -> the best program is optimal (recorded in close2_<key>.jsonl, so bounds2 sees it);
  UNKNOWN    -> next case.
Smallest patterns first: that is where the exact model can still decide.

usage: nice -n 10 ~/.ccc-venv/bin/python -u attack.py 3-large [--part 0/2] [--secs 600] [--workers 3]
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
from exact import project
import bounds2, satmodel2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('--cases', default='open')
    ap.add_argument('--part', default='0/1')
    ap.add_argument('--secs', type=float, default=600)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--max-cells', type=int, default=10 ** 9, help='skip bigger patterns')
    a = ap.parse_args()
    cases, best = load(a.key)
    lbs = bounds2.summarize(a.key, cases, best)
    if a.cases == 'open':
        idx = sorted((c for c in range(len(cases)) if lbs[c] < len(best[c])),
                     key=lambda c: (len(LineGeo(*cases[c][:2]).S), c))
    else:
        idx = [int(v) for v in a.cases.split(',')]
    p, N = map(int, a.part.split('/'))
    idx = idx[p::N]
    print(f'{a.key}: {len(idx)} cases in this part', flush=True)
    for c in idx:
        r, g, n = cases[c]
        lg = LineGeo(r, g)
        if len(lg.S) > a.max_cells:
            continue
        prog = best[c]
        src = f'{bounds2.RES}/improved/{a.key}_{c}.txt'
        if os.path.exists(src):
            p2 = [l.split() for l in open(src) if l.strip()]
            if simulate(lg.geo, p2, n) == len(p2) and len(p2) < len(prog):
                prog = p2
        while True:
            b = len(prog)
            kn = bounds2.known_bounds(a.key).get(c, {'F': {}, 'W': {}})
            lb, _, _ = bounds2.case_lb(kn, n)
            if max(lb, lbs[c]) >= b:
                print(f'{a.key} case {c}: optimal at {b} (bound)', flush=True)
                break
            st = project(lg, prog)
            hint = [(e, t, st[t][0][e]) for t in range(1, b) for e in range(6)] if st else None
            t0 = time.time()
            s, states = satmodel2.solve(lg, b - 1, n, secs=a.secs, workers=a.workers, hint=hint,
                                        known={'F': kn['F'], 'W': kn['W']}, opts=bounds2.F_OPTS)
            dt = time.time() - t0
            with open(f'{bounds2.RES}/close2_{a.key}.jsonl', 'a') as f:
                f.write(json.dumps(dict(case=c, kind='F', k=n, T=b - 1, status=s, secs=round(dt, 1),
                                        method='attack')) + '\n')
            print(f'{a.key} case {c} R={r} n={n} cells={len(lg.S)} best={b} lb={lb}: F{n}@{b - 1} {s} ({dt:.0f}s)', flush=True)
            if s == 'INFEASIBLE':
                bounds2.post('win', f'{a.key} case {c}: {b} lines proven optimal (no program with {b - 1})')
                break
            if s != 'FEASIBLE':
                break
            new = program_from_states(lg, states[1:])
            m = simulate(lg.geo, new, n)
            assert m is not None and m < b, 'solution does not replay'
            prog = new[:m]
            with open(src, 'w') as o:
                o.write('\n'.join(' '.join(l) for l in prog) + '\n')
            print(f'  -> spliced: {b} -> {m}', flush=True)
            bounds2.post('win', f'{a.key} case {c}: {b} -> {m} lines (exact solver, not merged yet)')


if __name__ == '__main__':
    main()
