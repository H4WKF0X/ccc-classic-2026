"""Decomposition lower bounds for Level 6 (CP-SAT model of satmodel.py, line coordinates of lines.py).

Quantities (all "minimum number of lines"):
  F_j = j copies starting from the real start configuration (F_count = the case's optimum),
  W_k = k copies starting from ANY emitter configuration with pattern + halo empty.
Right after a detection the pattern is cleared and the halo is empty (that is the detection
condition), so the rest of the program is a W-type problem.  Hence for a case with n copies
      OPT >= F_j + B(n - j)   for every j,     B(m) = max_{k <= m} ( W_k + B(m - k) ),  B(0) = 0,
(B uses superadditivity: m consecutive later copies split into chunks of k copies, each chunk
needs >= W_k lines).  Each F_j / W_k is pinned by a search over T: INFEASIBLE at T proves value
>= T+1 (feasibility is monotone in T), a FEASIBLE T is an upper bound.  When a solve times out the
proven lower bound is kept, so every number written is a valid bound even if the search is cut.

usage: nice -n 10 ~/.ccc-venv/bin/python bounds.py <key> [--cases all|1,2] [--secs 30] [--workers 4]
           [--fmax 2] [--wmax 3]
Appends rows to results/level6/decomp_<key>.csv (resumable).
"""
import argparse, csv, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate
from multi_cycles import det_ticks_of
import satmodel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, 'results', 'level6')


def pin(lg, k, free, lo, ub, secs, workers, log):
    """Bracket min T for (k copies, free/fixed start).  lo: known lower bound, ub: known feasible T.
    Returns (lb, ub): lb proven (all T < lb infeasible), ub feasible."""
    cap = ub            # smallest T known to be feasible or undecided: only T < cap is tested
    descend = True      # first walk down from ub (one INFEASIBLE proves ub optimal), then bisect
    while lo < cap:
        T = cap - 1 if descend else (lo + cap - 1) // 2
        t0 = time.time()
        st, _ = satmodel.solve(lg, T, k, free_start=free, secs=secs, workers=workers)
        log.append(f"{'W' if free else 'F'}{k}@{T}:{st[:3]}({time.time() - t0:.0f}s)")
        if st == 'INFEASIBLE':
            lo = T + 1
        elif st == 'FEASIBLE':
            ub = cap = T
        else:
            cap = T
            descend = False
    return lo, ub


def chain(W, m):
    """B(m): lower bound for m consecutive later copies from per-chunk bounds W[k] (k = 1..)."""
    B = [0] * (m + 1)
    for x in range(1, m + 1):
        B[x] = max(W[k] + B[x - k] for k in W if k <= x)
    return B[m]


def case_bounds(lg, prog, count, secs, workers, fmax, wmax):
    ts = det_ticks_of(lg.geo, prog)[:count]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    log = []
    W, Wub, F, Fub = {}, {}, {}, {}
    for k in range(1, min(wmax, count - 1) + 1):
        ub = min(sum(gaps[s:s + k]) for s in range(len(gaps) - k + 1))
        lo = max([k] + [W[j] + W[k - j] for j in range(1, k)])
        W[k], Wub[k] = pin(lg, k, True, lo, ub, secs, workers, log)
    for j in range(1, min(fmax, count) + 1):
        ub = ts[j - 1]
        lo = max([j] + [F[j - 1] + W.get(1, 1)] if j > 1 else [j])
        F[j], Fub[j] = pin(lg, j, False, lo, ub, secs, workers, log)
    lb = 0
    for j in range(0, len(F) + 1):
        fj = F[j] if j else 0
        lb = max(lb, fj + (chain(W, count - j) if W else count - j))
    return dict(F=F, Fub=Fub, W=W, Wub=Wub, lb=lb, first=ts[0], gaps=gaps, log=' '.join(log))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('--cases', default='all')
    ap.add_argument('--secs', type=float, default=30)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--fmax', type=int, default=2)
    ap.add_argument('--wmax', type=int, default=3)
    A = ap.parse_args()
    cases, best = load(A.key)
    idx = range(len(cases)) if A.cases == 'all' else [int(v) for v in A.cases.split(',')]
    path = os.path.join(RES, f'decomp_{A.key}.csv')
    done = set()
    if os.path.exists(path):
        done = {int(r['case']) for r in csv.DictReader(open(path))}
    new = not os.path.exists(path)
    f = open(path, 'a', newline='')
    w = csv.writer(f)
    if new:
        w.writerow(['case', 'R', 'count', 'cells', 'halo', 'best', 'first_best', 'F', 'Fub', 'W', 'Wub',
                    'lb_decomp', 'secs', 'log'])
    for i in idx:
        if i in done:
            continue
        r, g, c = cases[i]
        lg = LineGeo(r, g)
        t0 = time.time()
        res = case_bounds(lg, best[i], c, A.secs, A.workers, A.fmax, A.wmax)
        assert res['lb'] <= len(best[i]), (i, res)       # a bound above a real program = bug
        w.writerow([i, r, c, len(lg.S), len(lg.K), len(best[i]), res['first'], json.dumps(res['F']),
                    json.dumps(res['Fub']), json.dumps(res['W']), json.dumps(res['Wub']), res['lb'],
                    f'{time.time() - t0:.0f}', res['log']])
        f.flush()
        print(f"{A.key} case {i:3d} R={r} n={c} cells={len(lg.S)} best={len(best[i])} first={res['first']} "
              f"F={res['F']} W={res['W']} lb={res['lb']} [{res['log']}]", flush=True)


if __name__ == '__main__':
    main()
