"""Exact optimality proofs for Level 6 with the CP-SAT model of satmodel.py.

For every selected case:
  1. soundness check: the best known program, projected to line coordinates, must satisfy the model
     (so the model is not over-constrained on real programs).  Programs that walk an emitter round
     the back of the ring cannot be projected tick by tick; for those the model is solved at T=best
     instead and must be FEASIBLE ('ok(search)');
  2. solve "count copies within T = best-1 lines" from the real start.
     INFEASIBLE  -> the best program is provably optimal;
     FEASIBLE    -> a shorter program exists; it is simulated with cycles.simulate and written to
                    results/level6/exact_programs/<key>_<case>.txt;
     UNKNOWN     -> time cap hit, no conclusion.
usage: nice -n 10 ~/.ccc-venv/bin/python exact.py <key> [--cases all|3,4] [--secs 120] [--workers 4]
Appends one CSV row per case to results/level6/exact_<key>.csv (resumable: done cases are skipped).
"""
import argparse, csv, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
import satmodel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, 'results', 'level6')


def project(lg, prog):
    """Best program -> per-tick (q, on) in line coordinates (t = 0..T), or None if it leaves the
    [parked, arc, parked] window in a way the projection cannot represent."""
    g = lg.geo
    p = [e * lg.R for e in range(6)]
    on = [False] * 6
    out = [([lg.start_q] * 6, [False] * 6)]
    for line in prog:
        for e, a in enumerate(line):
            if a == 'F':
                p[e] = (p[e] + 1) % g.P
            elif a == 'B':
                p[e] = (p[e] - 1) % g.P
            elif a == 'T':
                on[e] = not on[e]
        q = []
        for e in range(6):
            if p[e] in lg.arc[e]:
                q.append(lg.arc[e][p[e]])
            else:   # beyond a parked position: clamp to the nearer parked one (ray empty either way)
                inv = {v: k for k, v in lg.arc[e].items()}
                d0 = min((p[e] - inv[0]) % g.P, (inv[0] - p[e]) % g.P)
                d1 = min((p[e] - inv[lg.nq - 1]) % g.P, (inv[lg.nq - 1] - p[e]) % g.P)
                q.append(0 if d0 <= d1 else lg.nq - 1)
        out.append((q, list(on)))
    for (q0, o0), (q1, o1) in zip(out, out[1:]):
        for e in range(6):
            if abs(q1[e] - q0[e]) > 1 or (o0[e] != o1[e] and q0[e] != q1[e]):
                return None
    return out


def fixed(states):
    def extra(m, V):
        for t, (q, o) in enumerate(states):
            for e in range(6):
                m.Add(V['pos'][e][t][q[e]] == 1)
                m.Add(V['on'][e][t] == int(o[e]))
    return extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('--cases', default='all')
    ap.add_argument('--secs', type=float, default=120)
    ap.add_argument('--workers', type=int, default=4)
    A = ap.parse_args()
    cases, best = load(A.key)
    idx = range(len(cases)) if A.cases == 'all' else [int(v) for v in A.cases.split(',')]
    path = os.path.join(RES, f'exact_{A.key}.csv')
    done = set()
    if os.path.exists(path):
        done = {int(r['case']) for r in csv.DictReader(open(path))}
    new = not os.path.exists(path)
    f = open(path, 'a', newline='')
    w = csv.writer(f)
    if new:
        w.writerow(['case', 'R', 'count', 'cells', 'halo', 'best', 'sound', 'T', 'status', 'secs', 'found'])
    os.makedirs(os.path.join(RES, 'exact_programs'), exist_ok=True)
    for i in idx:
        if i in done:
            continue
        r, g, c = cases[i]
        lg = LineGeo(r, g)
        b = len(best[i])
        st = project(lg, best[i])
        sound = 'n/a'
        if st is not None:
            s, _ = satmodel.solve(lg, b, c, secs=60, workers=A.workers, extra=fixed(st))
            sound = 'ok' if s == 'FEASIBLE' else 'FAIL:' + s
        else:   # program walks round the back of the ring: just check the model is feasible at T=best
            s, _ = satmodel.solve(lg, b, c, secs=60, workers=A.workers)
            sound = 'ok(search)' if s == 'FEASIBLE' else 'FAIL(search):' + s
        T = b - 1
        t0 = time.time()
        s, states = satmodel.solve(lg, T, c, secs=A.secs, workers=A.workers)
        dt = time.time() - t0
        found = ''
        if states:
            prog = program_from_states(lg, states[1:])
            n = simulate(lg.geo, prog, c)
            found = str(n)
            with open(os.path.join(RES, 'exact_programs', f'{A.key}_{i}.txt'), 'w') as o:
                o.write('\n'.join(' '.join(l) for l in prog[:n]) + '\n')
        w.writerow([i, r, c, len(lg.S), len(lg.K), b, sound, T, s, f'{dt:.1f}', found])
        f.flush()
        print(f'{A.key} case {i:3d} R={r} count={c:2d} cells={len(lg.S):3d} best={b:3d} sound={sound} '
              f'T={T}: {s} {dt:.1f}s {found}', flush=True)


if __name__ == '__main__':
    main()
