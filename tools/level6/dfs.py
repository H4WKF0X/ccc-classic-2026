"""Depth-first search for ONE tight chain (see tight.py): a program of exactly lb = F1 + (n-1) W1 lines.

Instead of enumerating every configuration of every layer, each worker walks one chain: from the
current configuration it asks for *one* copy of exactly the tight length (first copy F1 ticks from the
real start, later copies W1 ticks), excluding end configurations already known to be dead ends.
  FEASIBLE   -> go one copy deeper;
  INFEASIBLE -> no (live) continuation: this configuration is dead for that many remaining copies
                (written to a shared file, so all workers skip it); backtrack one copy;
  UNKNOWN    -> give up on this configuration for this worker only; backtrack.
Workers differ by their random seed (different solutions -> different chains).  The first worker
that reaches n copies rebuilds the program, replays it and saves it; all workers then stop.
Only finds programs: if there is none, the search never proves it (use tight.py for proofs).

usage: nice -n 10 ~/.ccc-venv/bin/python -u dfs.py 2-medium 161 [--procs 14] [--secs 120] [--minutes 60]
"""
import argparse, json, multiprocessing as mp, os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate
from improve import _instructions
from tight import build, canon, cfg_key, swap, SWAPS
import bounds2, satmodel2
from ortools.sat.python import cp_model

WORK = os.path.join(bounds2.ROOT, 'work', 'level6', 'bounds2')


def read_dead(path):
    dead = set()
    if os.path.exists(path):
        for line in open(path):
            k, key = json.loads(line)
            dead.add((k, tuple(map(tuple, key))))
    return dead


def one_copy(lg, T, start, known, exclude, secs, seed):
    """One copy in exactly T ticks from `start`, ending outside `exclude` (canonical keys)."""
    m, V = build(lg, T, start, known)
    for key in exclude:
        for ax in SWAPS:
            q, on = swap((list(key[0]), list(key[1])), ax)
            m.AddBoolOr([V['pos'][e][T][q[e]].Not() for e in range(6)] +
                        [V['on'][e][T].Not() if on[e] else V['on'][e][T] for e in range(6)])
    sol = cp_model.CpSolver()
    sol.parameters.max_time_in_seconds = secs
    sol.parameters.num_workers = 1
    sol.parameters.random_seed = seed
    sol.parameters.randomize_search = True
    st = sol.Solve(m)
    if st == cp_model.INFEASIBLE:
        return 'INFEASIBLE', None
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return 'UNKNOWN', None
    nq = len(V['pos'][0][0])
    states = [([next(j for j in range(nq) if sol.Value(V['pos'][e][t][j])) for e in range(6)],
               [bool(sol.Value(V['on'][e][t])) for e in range(6)]) for t in range(T + 1)]
    return 'FEASIBLE', states


def worker(wid, a, n, f1, w1, known, deadline, dead_path, stop_path):
    rnd = random.Random(1000 + wid)
    cases, _ = load(a.key)
    r, g, _ = cases[a.case]
    lg = LineGeo(r, g)
    # stack[i] = (config after i copies (None = real start), segment states that led there,
    #             canonical end keys already tried from here)
    stack = [(None, None, set())]
    best_depth = 0; solves = 0
    while time.time() < deadline and not os.path.exists(stop_path):
        depth = len(stack) - 1
        cfg, _, tried = stack[-1]
        remaining = n - depth
        dead = read_dead(dead_path)
        # children that are dead for (remaining - 1) further copies are excluded too
        excl = set(tried) | {key for (k, key) in dead if k == remaining - 1}
        T = f1 if depth == 0 else w1
        s, states = one_copy(lg, T, cfg, known, excl, a.secs, rnd.randrange(1 << 30))
        solves += 1
        if s == 'FEASIBLE':
            end = states[T]
            tried.add(cfg_key(canon(end)))
            stack.append((end, states, set()))
            if len(stack) - 1 > best_depth:
                best_depth = len(stack) - 1
                print(f'worker {wid}: reached copy {best_depth}/{n} ({solves} solves)', flush=True)
            if len(stack) - 1 == n:
                prog = []
                for _, seg, _ in stack[1:]:
                    prog += _instructions(lg, seg)
                m = simulate(lg.geo, prog, n)
                print(f'worker {wid}: FOUND chain, replay -> {m} lines', flush=True)
                if m is not None and m <= f1 + (n - 1) * w1:
                    with open(f'{bounds2.RES}/improved/{a.key}_{a.case}.txt', 'w') as o:
                        o.write('\n'.join(' '.join(l) for l in prog[:m]) + '\n')
                    open(stop_path, 'w').write(str(m))
                    bounds2.post('win', f'{a.key} case {a.case}: {m} lines (depth-first chain search, not merged yet)')
                    return
                stack.pop()     # does not replay (should not happen): treat as dead end
            continue
        proven_dead_children = {key for (k, key) in read_dead(dead_path) if k == remaining - 1}
        if s == 'INFEASIBLE' and depth > 0 and tried <= proven_dead_children:
            # no continuation except proven dead ends: this configuration is dead with `remaining`
            # copies left (children abandoned after a timeout are not proven, so then no mark)
            with open(dead_path, 'a') as f:
                f.write(json.dumps([remaining, [list(x) for x in cfg_key(canon(cfg))]]) + '\n')
        if depth == 0:
            if s == 'INFEASIBLE':
                print(f'worker {wid}: every first copy is a dead end -> no chain exists', flush=True)
                open(stop_path, 'w').write('none')
                return
            continue        # UNKNOWN at the root: just try again with another seed
        stack.pop()         # backtrack (the child key stays in the parent's `tried`)
    print(f'worker {wid}: stopped, deepest copy {best_depth}/{n}, {solves} solves', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('case', type=int)
    ap.add_argument('--procs', type=int, default=14)
    ap.add_argument('--secs', type=float, default=120, help='time limit per solve')
    ap.add_argument('--minutes', type=float, default=60)
    a = ap.parse_args()
    cases, best = load(a.key)
    n = cases[a.case][2]
    kb = bounds2.known_bounds(a.key)[a.case]
    F, W = satmodel2.closure(kb['F'], kb['W'], n)
    f1, w1 = F[1], W[1]
    print(f'{a.key} case {a.case}: n={n} best={len(best[a.case])} looking for a chain of '
          f'{f1} + {n - 1} x {w1} = {f1 + (n - 1) * w1} lines, {a.procs} workers, {a.minutes} min', flush=True)
    os.makedirs(WORK, exist_ok=True)
    dead_path = f'{WORK}/dfs_{a.key}_{a.case}_dead.jsonl'
    stop_path = f'{WORK}/dfs_{a.key}_{a.case}.stop'
    if os.path.exists(stop_path):
        os.remove(stop_path)
    known = {'F': kb['F'], 'W': kb['W']}
    deadline = time.time() + a.minutes * 60
    ps = [mp.Process(target=worker, args=(w, a, n, f1, w1, known, deadline, dead_path, stop_path))
          for w in range(a.procs)]
    for p in ps:
        p.start()
    last = 0
    while any(p.is_alive() for p in ps):
        time.sleep(5)
        if time.time() - last > 300:
            last = time.time()
            d = read_dead(dead_path)
            by_k = {}
            for k, _ in d:
                by_k[k] = by_k.get(k, 0) + 1
            print(f'status: {len(d)} dead configurations known (by copies left: {dict(sorted(by_k.items()))})', flush=True)
        if os.path.exists(stop_path):
            time.sleep(2)
            for p in ps:
                p.terminate()
            break
    res = open(stop_path).read() if os.path.exists(stop_path) else 'not found in time'
    print(f'done: {res}', flush=True)


if __name__ == '__main__':
    main()
