"""Inner-copy windows (large neighbourhood search) for Level 6.

improve.py re-solves whole stretches between two detections; for long copies (enormous: mostly one
copy of 25-100 ticks) that model is too big.  Here we keep the program and free only a short span
of f consecutive ticks inside one copy window, everything before and after the span fixed to the
current program's emitter states, and ask the exact model (satmodel2) for the same window in one
tick less:

    window ticks 1..L  ->  new ticks 1..L-1:
        t <  a       state = old state t          (fixed prefix)
        a <= t < b   free                         (the span a..b, f = b-a+1 old ticks, now f-1)
        t >= b       state = old state t+1        (fixed suffix, shifted by one)

The model simulates the matter of every pattern/halo cell over the whole window, so a solution is
exactly valid (same copies, same end configuration); it is spliced in and re-verified with the
reference simulator.  INFEASIBLE proves only that this span cannot shrink with the rest fixed.

usage: nice -n 10 ~/.ccc-venv/bin/python -u inner.py <key> --cases 3,17 [--spans 4,6,8,10,12,14] [--secs 20]
Wins go to results/level6/improved/<key>_<case>.txt (merge with merge_improved.py) and the dashboard.
"""
import argparse, hashlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate
from multi_cycles import det_ticks_of
from exact import project
from improve import OUT, _instructions
import satmodel2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASH = os.path.join(ROOT, 'work', 'dashboard')


def post(kind, text):
    os.makedirs(DASH, exist_ok=True)
    with open(f'{DASH}/events.jsonl', 'a') as f:
        f.write(json.dumps(dict(id=f'e{int(time.time() * 1000)}', t=int(time.time()), agent='inner-window',
                                kind=kind, text=text)) + '\n')


def span_extra(T, copies, end_cfg, fixed):
    """fixed: {new tick t: (q[6], on[6])}."""
    def extra(m, V):
        m.Add(sum(V['det'][1:]) == copies)
        m.Add(V['det'][T] == 1)
        if end_cfg is not None:
            for e in range(6):
                m.Add(V['pos'][e][T][end_cfg[0][e]] == 1)
                m.Add(V['on'][e][T] == int(end_cfg[1][e]))
        for t, (q, on) in fixed.items():
            for e in range(6):
                m.Add(V['pos'][e][t][q[e]] == 1)
                m.Add(V['on'][e][t] == int(on[e]))
    return extra


def spans(L, sizes):
    """(a, b) spans of the window ticks 1..L, small spans first, overlapping by half."""
    out = []
    for f in sizes:
        if f > L:
            continue
        step = max(1, f // 2)
        starts = list(range(1, L - f + 2, step))
        if starts[-1] != L - f + 1:
            starts.append(L - f + 1)
        out += [(a, a + f - 1) for a in starts]
    return out


def improve_case(lg, prog, count, sizes, secs, workers, log, on_improve=None):
    proven = set()
    changed = True
    stats = dict(INFEASIBLE=0, FEASIBLE=0, UNKNOWN=0, secs=0.0)
    while changed:
        changed = False
        st = project(lg, prog)
        if st is None:
            log('  not projectable (detour round the ring) - skipped')
            return prog, stats
        cut = [0] + det_ticks_of(lg.geo, prog)[:count]
        # longest copy windows first: that is where the slack is
        for i in sorted(range(count), key=lambda i: cut[i] - cut[i + 1]):
            j = i + 1; L = cut[j] - cut[i]
            start = None if i == 0 else st[cut[i]]
            end = None if j == count else st[cut[j]]
            ctx = hashlib.md5(repr((start, st[cut[i]:cut[j] + 1], end)).encode()).hexdigest()
            for a, b in spans(L, sizes):
                if (ctx, a, b) in proven:
                    continue
                fixed = {t: st[cut[i] + t] for t in range(1, a)}
                fixed.update({t: st[cut[i] + t + 1] for t in range(b, L)})
                t0 = time.time()
                s, states = satmodel2.solve(lg, L - 1, 1, start_cfg=start, secs=secs, workers=workers,
                                            symbreak=False, extra=span_extra(L - 1, 1, end, fixed))
                dt = time.time() - t0; stats[s if s in stats else 'UNKNOWN'] += 1; stats['secs'] += dt
                log(f'  copy {i + 1} (len {L}) ticks {a}..{b}: {s} ({dt:.1f}s)')
                if s == 'INFEASIBLE':
                    proven.add((ctx, a, b))
                if states is None:
                    continue
                new = prog[:cut[i]] + _instructions(lg, states) + prog[cut[j]:]
                n = simulate(lg.geo, new, count)
                if n is not None and n < len(prog):
                    log(f'  copy {i + 1} (len {L}) ticks {a}..{b}: FEASIBLE ({dt:.1f}s) -> spliced: {len(prog)} -> {n}')
                    prog = new[:n]
                    if on_improve:
                        on_improve(prog)
                    changed = True
                    break
                log(f'  copy {i + 1} ticks {a}..{b}: splice did not verify (n={n})')
            if changed:
                break
    return prog, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('--cases', required=True)
    ap.add_argument('--spans', default='4,6,8,10,12,14')
    ap.add_argument('--secs', type=float, default=20)
    ap.add_argument('--workers', type=int, default=1)
    A = ap.parse_args()
    sizes = [int(x) for x in A.spans.split(',')]
    cases, best = load(A.key)
    os.makedirs(OUT, exist_ok=True)
    for ci in [int(v) for v in A.cases.split(',')]:
        r, g, c = cases[ci]
        lg = LineGeo(r, g)
        src = os.path.join(OUT, f'{A.key}_{ci}.txt')
        prog = best[ci]
        if os.path.exists(src):
            p2 = [l.split() for l in open(src) if l.strip()]
            if simulate(lg.geo, p2, c) == len(p2) and len(p2) < len(prog):
                prog = p2
        b0 = len(best[ci])
        print(f'{A.key} case {ci} R={r} n={c} start {len(prog)} (best file {b0})', flush=True)

        def save(p, src=src, ci=ci):
            with open(src, 'w') as o:
                o.write('\n'.join(' '.join(l) for l in p) + '\n')
            post('win', f'{A.key} case {ci}: {b0} -> {len(p)} (inner-copy window, not merged yet)')
        new, stats = improve_case(lg, prog, c, sizes, A.secs, A.workers, lambda s: print(s, flush=True), save)
        print(f'  spans: {stats["INFEASIBLE"]} infeasible, {stats["FEASIBLE"]} feasible, '
              f'{stats["UNKNOWN"]} unknown, {stats["secs"]:.0f}s', flush=True)
        print(f'{A.key} case {ci}: {b0} -> {len(new)}', flush=True)


if __name__ == '__main__':
    main()
