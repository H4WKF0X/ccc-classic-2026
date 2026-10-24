"""Exact window re-optimisation of known programs (Level 6).

A program's state right after its i-th detection is only the emitter configuration c_i (pattern
cleared, halo empty).  So any window "from detection i to detection j" can be replaced by the
shortest program that starts in c_i, makes exactly j-i copies, and ends (at its last detection) in
c_j -- or, for j = count, ends anywhere.  Each window is solved *exactly* with satmodel at
T = window length - 1: INFEASIBLE certifies that window optimal, FEASIBLE gives a shorter program,
which is spliced in and re-verified with the reference simulator.

usage: nice -n 10 ~/.ccc-venv/bin/python improve.py <key> --cases 50,80 [--maxlen 30] [--secs 30]
Writes improved programs to results/level6/improved/<key>_<case>.txt and a log line per window.
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
from multi_cycles import det_ticks_of
from exact import project
import satmodel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'results', 'level6', 'improved')


def window_extra(T, copies, end_cfg):
    def extra(m, V):
        m.Add(sum(V['det'][1:]) == copies)
        m.Add(V['det'][T] == 1)
        if end_cfg is not None:
            for e in range(6):
                m.Add(V['pos'][e][T][end_cfg[0][e]] == 1)
                m.Add(V['on'][e][T] == int(end_cfg[1][e]))
    return extra


def improve_case(lg, prog, count, maxlen, secs, workers, log):
    """Repeat: try every window (shortest first); splice the first improvement; until none."""
    changed = True
    while changed:
        changed = False
        st = project(lg, prog)
        if st is None:
            log(f'  not projectable (detour round the ring) - skipped')
            return prog
        ts = det_ticks_of(lg.geo, prog)[:count]
        cut = [0] + ts                      # cut[i] = tick of detection i (0 = program start)
        wins = [(cut[j] - cut[i], i, j) for i in range(count) for j in range(i + 1, count + 1)
                if cut[j] - cut[i] <= maxlen]
        for L, i, j in sorted(wins):
            if L - 1 < j - i:
                continue
            start = None if i == 0 else st[cut[i]]
            end = None if j == count else st[cut[j]]
            t0 = time.time()
            s, states = satmodel.solve(lg, L - 1, j - i, start_cfg=start, secs=secs, workers=workers,
                                       symbreak=False, extra=window_extra(L - 1, j - i, end))
            log(f'  window {i}->{j} len {L}: {s} ({time.time() - t0:.0f}s)')
            if states:
                # rebuild the window as instructions, starting from its own start state
                sub = _instructions(lg, states)
                new = prog[:cut[i]] + sub + prog[cut[j]:]
                n = simulate(lg.geo, new, count)
                if n is not None and n < len(prog):
                    log(f'  -> spliced: {len(prog)} -> {n}')
                    prog = new[:n]
                    changed = True
                    break
                log(f'  -> splice did not verify (n={n})')
    return prog


def _instructions(lg, states):
    """states[0] is the window start; emit instruction lines for ticks 1..T."""
    g = lg.geo
    inv = [{q: p for p, q in lg.arc[e].items()} for e in range(6)]
    lines = []
    for (q0, o0), (q1, o1) in zip(states, states[1:]):
        line = []
        for e in range(6):
            if o0[e] != o1[e]:
                line.append('T')
            elif q0[e] == q1[e]:
                line.append('-')
            else:
                line.append('F' if (inv[e][q0[e]] + 1) % g.P == inv[e][q1[e]] else 'B')
        lines.append(line)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('--cases', required=True)
    ap.add_argument('--maxlen', type=int, default=30)
    ap.add_argument('--secs', type=float, default=30)
    ap.add_argument('--workers', type=int, default=4)
    A = ap.parse_args()
    cases, best = load(A.key)
    os.makedirs(OUT, exist_ok=True)
    for i in [int(v) for v in A.cases.split(',')]:
        r, g, c = cases[i]
        lg = LineGeo(r, g)
        src = os.path.join(OUT, f'{A.key}_{i}.txt')
        prog = best[i]
        if os.path.exists(src):           # continue from an earlier improvement
            prog = [l.split() for l in open(src) if l.strip()]
            assert simulate(lg.geo, prog, c) == len(prog)
        b0 = len(prog)
        print(f'{A.key} case {i} R={r} n={c} start {b0} (best file {len(best[i])})', flush=True)
        new = improve_case(lg, prog, c, A.maxlen, A.secs, A.workers, lambda s: print(s, flush=True))
        if len(new) < b0:
            with open(src, 'w') as o:
                o.write('\n'.join(' '.join(l) for l in new) + '\n')
        print(f'{A.key} case {i}: {len(best[i])} -> {len(new)}', flush=True)


if __name__ == '__main__':
    main()
