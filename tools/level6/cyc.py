"""Exact shortest cycles for multi-copy cases: program = prefix + (n-1) x cycle.

Right after a detection the matter is empty, so the state is just the emitter configuration.  A
k-copy cycle is a configuration c and L ticks from c that make exactly k copies and end (at the
k-th detection) in c again; it can be repeated as often as needed.  For each case:
  1. climb L upwards from the proven bound (k * W1) to the shortest cycle (satmodel2, free start,
     extra constraint: end configuration = start configuration);
  2. shortest prefix from the real start that makes the first copy and ends in c (exact climb);
  3. program = prefix + cycle repeated; for n-1 not divisible by k the remainder is the first
     copies of the cycle (it is cut at the n-th detection anyway);
  4. kept if the reference simulator confirms it and it is shorter than the best.
Wins go to results/level6/improved/<key>_<case>.txt (merge with merge_improved.py) + dashboard.

usage: nice -n 10 ~/.ccc-venv/bin/python -u cyc.py 3-large [--cases 102,54] [--ks 1,2] [--secs 300]
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate
from multi_cycles import det_ticks_of
from improve import _instructions
import bounds2, satmodel2


def same_cfg(T, copies, start_eq_end=True, end_cfg=None):
    def extra(m, V):
        m.Add(sum(V['det'][1:]) == copies)
        m.Add(V['det'][T] == 1)
        for e in range(6):
            if start_eq_end:
                for q in range(len(V['pos'][e][0])):
                    m.Add(V['pos'][e][0][q] == V['pos'][e][T][q])
                m.Add(V['on'][e][0] == V['on'][e][T])
            if end_cfg is not None:
                m.Add(V['pos'][e][T][end_cfg[0][e]] == 1)
                m.Add(V['on'][e][T] == int(end_cfg[1][e]))
    return extra


def shortest(lg, lo, hi, solve_at, secs, log, label):
    """Shortest T in [lo, hi] with a solution found by descending from hi (finding a solution is
    much cheaper than proving there is none); stops at the first T without one."""
    found = (None, None)
    for T in range(hi, lo - 1, -1):
        t0 = time.time()
        s, states = solve_at(T, secs)
        log(f'  {label}@{T}: {s} ({time.time() - t0:.0f}s)')
        if s != 'FEASIBLE':
            break
        found = (T, states)
    return found


def try_case(key, c, lg, n, prog, ks, secs, workers, log):
    kb = bounds2.known_bounds(key).get(c, {'F': {}, 'W': {}})
    F, W = satmodel2.closure(kb['F'], kb['W'], max(ks) + 1)
    ts = det_ticks_of(lg.geo, prog)[:n]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    best_len = len(prog); out = None
    for k in ks:
        if k > n - 1:
            continue
        # a k-cycle only helps if it beats the current per-copy cost
        cur = sum(gaps) / len(gaps) * k
        hi = int(cur - 1e-9) if cur == int(cur) else int(cur)
        hi = min(hi, int(cur) - (1 if cur == int(cur) else 0))
        lo = max(W.get(k, k), k)
        if lo > hi:
            log(f'  k={k}: no room (bound {lo} >= current {cur:.1f})')
            continue
        L, cyc = shortest(lg, lo, hi, lambda T, s: satmodel2.solve(
            lg, T, k, free_start=True, symbreak=False, secs=s, workers=workers,
            extra=same_cfg(T, k)), secs, log, f'cycle{k}')
        if L is None:
            continue
        cfg = cyc[0]
        # prefix: first copy (j = 1) from the real start ending in cfg; also j = 0 (travel only)
        for j in (1, 0):
            reps = -(-(n - j) // k)
            budget = best_len - 1 - (n - j) // k * L      # prefix must be shorter than this
            lo_p = F.get(j, j) if j else 1
            if budget < lo_p:
                log(f'  k={k} j={j}: prefix would need <= {budget} ticks (bound {lo_p})')
                continue
            P, pre = shortest(lg, lo_p, budget, lambda T, s, j=j: satmodel2.solve(
                lg, T, j, secs=s, workers=workers, symbreak=False,
                extra=same_cfg(T, j, start_eq_end=False, end_cfg=cfg) if j else _travel(T, cfg)),
                secs, log, f'prefix{j}')
            if P is None:
                continue
            new = _instructions(lg, pre) + _instructions(lg, cyc) * reps
            m = simulate(lg.geo, new, n)
            log(f'  k={k} j={j}: prefix {P} + cycle {L} x {reps} -> {m}')
            if m is not None and m < best_len:
                best_len, out = m, new[:m]
    return out


def _travel(T, cfg):
    """No detection, end in cfg (and nothing left on the board: the cycle starts from empty)."""
    def extra(m, V):
        m.Add(sum(V['det'][1:]) == 0)
        for e in range(6):
            m.Add(V['pos'][e][T][cfg[0][e]] == 1)
            m.Add(V['on'][e][T] == int(cfg[1][e]))
        for (t, i), v in V['mt'].items():
            if t == T:
                m.Add(v == 0)
    return extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('--cases', default='auto')
    ap.add_argument('--ks', default='1,2')
    ap.add_argument('--secs', type=float, default=300)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--part', default='0/1')
    a = ap.parse_args()
    ks = [int(x) for x in a.ks.split(',')]
    cases, best = load(a.key)
    lbs = bounds2.summarize(a.key, cases, best)
    if a.cases == 'auto':
        # multi-copy open cases, most later-copy lines first ... but small patterns decide fastest
        idx = sorted((c for c in range(len(cases)) if cases[c][2] >= 3 and lbs[c] < len(best[c])),
                     key=lambda c: (len(LineGeo(*cases[c][:2]).S), c))
    else:
        idx = [int(v) for v in a.cases.split(',')]
    p, N = map(int, a.part.split('/'))
    for c in idx[p::N]:
        r, g, n = cases[c]
        lg = LineGeo(r, g)
        print(f'{a.key} case {c} R={r} n={n} cells={len(lg.S)} best={len(best[c])}', flush=True)
        new = try_case(a.key, c, lg, n, best[c], ks, a.secs, a.workers, lambda s: print(s, flush=True))
        if new:
            with open(f'{bounds2.RES}/improved/{a.key}_{c}.txt', 'w') as o:
                o.write('\n'.join(' '.join(l) for l in new) + '\n')
            print(f'  -> spliced: {len(best[c])} -> {len(new)}', flush=True)
            bounds2.post('win', f'{a.key} case {c}: {len(best[c])} -> {len(new)} lines (exact cycle, not merged yet)')
        print(f'{a.key} case {c}: {len(best[c])} -> {len(new) if new else len(best[c])}', flush=True)


if __name__ == '__main__':
    main()
