"""Tight-chain search: decide whether a case has a program of exactly lb lines when
lb = F1 + (n-1) * W1 (first copy as short as possible, every later copy as short as possible).

A program of that length must have its first detection exactly at tick F1 and every later one
exactly W1 ticks after the previous (each segment is at least its proven bound and the sum is
tight).  Right after a detection the pattern is cleared and the halo is empty, so the state is
only the emitter configuration.  Hence, layer by layer:
    L1 = all configurations in which a first copy can end at tick F1 (from the real start),
    L(i+1) = all configurations reachable from some c in L(i) by one copy in exactly W1 ticks.
L(n) empty  -> no program of lb lines: the best (lb+1) is optimal.
L(n) found  -> a program of lb lines (rebuilt from the stored segments and replayed).
Each step is a small exact model (satmodel2, one copy, 7-10 ticks, fixed start); all end
configurations are enumerated by re-solving with a blocking clause per configuration found.
If any enumeration hits its time limit the result is not a proof (reported).

usage: nice -n 10 ~/.ccc-venv/bin/python -u tight.py 2-medium 161 [--procs 16] [--secs 600]
Progress per layer in the log; results in results/level6/tight_<key>_<case>.json.
"""
import argparse, json, multiprocessing as mp, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate
from improve import _instructions
import bounds2, satmodel2
from ortools.sat.python import cp_model


class Built(Exception):
    def __init__(self, m, V):
        self.m, self.V = m, V


def build(lg, T, start, known):
    """The model 'one copy, detection exactly at T, from start (None = real start)'."""
    def extra(m, V):
        m.Add(sum(V['det'][1:]) == 1)
        m.Add(V['det'][T] == 1)
        raise Built(m, V)
    try:
        satmodel2.solve(lg, T, 1, start_cfg=start, symbreak=False, known=known, extra=extra)
    except Built as b:
        return b.m, b.V
    raise RuntimeError('model was not built')


def enum_ends(args):
    """All end configurations of one copy in exactly T ticks from `start`.
    Returns (start, [(end_cfg, states)], complete, seconds)."""
    key, case, T, start, known, secs = args
    r, g, _ = load(key)[0][case]
    lg = LineGeo(r, g)
    m, V = build(lg, T, start, known)
    nq = len(V['pos'][0][0])
    out = []; t0 = time.time(); complete = True
    while True:
        left = secs - (time.time() - t0)
        if left <= 1:
            complete = False; break
        sol = cp_model.CpSolver()
        sol.parameters.max_time_in_seconds = left
        sol.parameters.num_workers = 1
        st = sol.Solve(m)
        if st == cp_model.INFEASIBLE:
            break
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            complete = False; break
        states = []
        for t in range(T + 1):
            q = [next(j for j in range(nq) if sol.Value(V['pos'][e][t][j])) for e in range(6)]
            states.append((q, [bool(sol.Value(V['on'][e][t])) for e in range(6)]))
        end = states[T]
        out.append((end, states))
        if len(out) % 100 == 0:
            print(f'    enumeration from {"real start" if start is None else "a config"}: '
                  f'{len(out)} end configs so far, {time.time() - t0:.0f}s', flush=True)
        # block this end configuration
        m.AddBoolOr([V['pos'][e][T][end[0][e]].Not() for e in range(6)] +
                    [V['on'][e][T].Not() if end[1][e] else V['on'][e][T] for e in range(6)])
    return start, out, complete, time.time() - t0


def cfg_key(c):
    return (tuple(c[0]), tuple(c[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('case', type=int)
    ap.add_argument('--procs', type=int, default=16)
    ap.add_argument('--secs', type=float, default=600, help='time limit per enumeration')
    a = ap.parse_args()
    cases, best = load(a.key)
    r, g, n = cases[a.case]
    lg = LineGeo(r, g)
    kb = bounds2.known_bounds(a.key)[a.case]
    F, W = satmodel2.closure(kb['F'], kb['W'], n)
    f1, w1 = F[1], W[1]
    target = f1 + (n - 1) * w1
    print(f'{a.key} case {a.case}: n={n} best={len(best[a.case])} F1={f1} W1={w1} -> tight target {target}', flush=True)
    assert target < len(best[a.case]), 'nothing to decide'
    known = {'F': kb['F'], 'W': kb['W']}
    res_path = f'{bounds2.RES}/tight_{a.key}_{a.case}.json'
    parent = {}            # layer i config -> (layer i-1 config, segment states)
    layer = [None]         # layer 0: the real start
    complete_all = True
    pool = mp.Pool(a.procs)
    for i in range(1, n + 1):
        T = f1 if i == 1 else w1
        t0 = time.time()
        jobs = [(a.key, a.case, T, s, known, a.secs) for s in layer]
        nxt = {}; incomplete = 0; done = 0
        last = i == n
        for start, ends, complete, secs in pool.imap_unordered(enum_ends, jobs):
            done += 1
            incomplete += not complete
            for end, states in ends:
                k = cfg_key(end)
                if k not in nxt:
                    nxt[k] = end
                    parent[(i, k)] = (start, states)
            if done % 50 == 0 or done == len(jobs):
                print(f'  layer {i}: {done}/{len(jobs)} starts done, {len(nxt)} end configs, '
                      f'{incomplete} incomplete, {time.time() - t0:.0f}s', flush=True)
            if last and nxt:
                break
        complete_all &= incomplete == 0
        print(f'layer {i} (copy {i}, {T} ticks): {len(nxt)} configurations'
              f'{"" if incomplete == 0 else f" (NOT complete: {incomplete} enumerations timed out)"} '
              f'[{time.time() - t0:.0f}s]', flush=True)
        if not nxt:
            verdict = 'OPTIMAL' if complete_all else 'UNDECIDED'
            msg = (f'{a.key} case {a.case}: no program with {target} lines -> {len(best[a.case])} is optimal'
                   if verdict == 'OPTIMAL' else
                   f'{a.key} case {a.case}: layer {i} empty but some enumerations timed out (no proof)')
            print(msg, flush=True)
            json.dump(dict(verdict=verdict, layer=i, target=target), open(res_path, 'w'))
            if verdict == 'OPTIMAL':
                with open(f'{bounds2.RES}/close2_{a.key}.jsonl', 'a') as f:
                    f.write(json.dumps(dict(case=a.case, kind='F', k=n, T=target, status='INFEASIBLE',
                                            method='tight-chain')) + '\n')
                bounds2.post('win', msg)
            pool.terminate()
            return
        layer = list(nxt.values())
    # a full chain exists: rebuild the program from the last layer backwards
    k = cfg_key(layer[0])
    segs = []
    for i in range(n, 0, -1):
        start, states = parent[(i, k)]
        segs.append(states)
        k = cfg_key(start) if start is not None else None
    prog = []
    for states in reversed(segs):
        prog += _instructions(lg, states)
    m = simulate(lg.geo, prog, n)
    print(f'{a.key} case {a.case}: FOUND a program, replay -> {m} lines', flush=True)
    assert m is not None and m <= target
    with open(f'{bounds2.RES}/improved/{a.key}_{a.case}.txt', 'w') as o:
        o.write('\n'.join(' '.join(l) for l in prog[:m]) + '\n')
    json.dump(dict(verdict='FOUND', target=target, lines=m), open(res_path, 'w'))
    bounds2.post('win', f'{a.key} case {a.case}: {len(best[a.case])} -> {m} lines (tight-chain search, not merged yet)')
    pool.terminate()


if __name__ == '__main__':
    main()
