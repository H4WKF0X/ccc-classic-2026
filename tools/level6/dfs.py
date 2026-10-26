"""Depth-first search for ONE short chain of copies: a program of at most `target` lines (default best-1).

Tight case (target = F1 + (n-1) W1, see tight.py): every copy has its minimal length.  With slack, a
copy may be longer: each node tries lengths from the minimum upwards, as long as the remaining copies
still fit (each later copy needs at least W1).  Dead ends are (configuration, copies left, ticks left).

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
    """[(copies_left, budget_left, canonical key)]: from that configuration no chain of that many
    copies fits into that many ticks (so neither into fewer)."""
    dead = []
    if os.path.exists(path):
        for line in open(path):
            k, bud, key = json.loads(line)
            dead.append((k, bud, tuple(map(tuple, key))))
    return dead


def dead_keys(dead, k, budget):
    return {key for (kk, bud, key) in dead if kk == k and bud >= budget}


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


def worker(wid, a, n, f1, w1, target, known, deadline, dead_path, stop_path):
    rnd = random.Random(1000 + wid)
    cases, _ = load(a.key)
    r, g, _ = cases[a.case]
    lg = LineGeo(r, g)
    # node = [config (None = real start), segment states that led here, ticks used so far,
    #         current copy length L being tried, {L: canonical end keys tried with that L}, clean]
    stack = [[None, None, 0, f1, {}, True]]
    best_depth = 0; solves = 0
    while time.time() < deadline and not os.path.exists(stop_path):
        depth = len(stack) - 1
        node = stack[-1]
        cfg, _, used, L, tried, clean = node
        left = n - depth                                   # copies still to make
        budget = target - used                             # ticks still allowed
        lmax = budget - (left - 1) * w1                    # longest this copy may be
        if L > lmax:
            # every length failed: dead for `left` copies within `budget` ticks, if proven
            if clean and depth > 0:
                with open(dead_path, 'a') as f:
                    f.write(json.dumps([left, budget, [list(x) for x in cfg_key(canon(cfg))]]) + '\n')
            if depth == 0:
                print(f'worker {wid}: {"no chain exists" if clean else "root exhausted (not proven)"}', flush=True)
                if clean and not os.path.exists(stop_path):
                    # exhaustive and every dead end proven: no program of `target` lines exists
                    open(stop_path, 'w').write('none')
                    with open(f'{bounds2.RES}/close2_{a.key}.jsonl', 'a') as f:
                        f.write(json.dumps(dict(case=a.case, kind='F', k=n, T=target, status='INFEASIBLE',
                                                method='dfs-exhaustive')) + '\n')
                    bounds2.post('win', f'{a.key} case {a.case}: no program with {target} lines '
                                        f'(exhaustive chain search) -> {target + 1} is optimal')
                return
            stack.pop()
            if not clean:
                stack[-1][5] = False
            continue
        tr = tried.setdefault(L, set())
        dead = read_dead(dead_path)
        excl = tr | dead_keys(dead, left - 1, budget - L)
        s, states = one_copy(lg, L, cfg, known, excl, a.secs, rnd.randrange(1 << 30))
        solves += 1
        if s == 'FEASIBLE':
            end = states[L]
            tr.add(cfg_key(canon(end)))
            stack.append([end, states, used + L, w1, {}, True])
            if len(stack) - 1 > best_depth:
                best_depth = len(stack) - 1
                print(f'worker {wid}: reached copy {best_depth}/{n} at tick {used + L} ({solves} solves)', flush=True)
            if len(stack) - 1 == n:
                prog = []
                for nd in stack[1:]:
                    prog += _instructions(lg, nd[1])
                m = simulate(lg.geo, prog, n)
                print(f'worker {wid}: FOUND chain, replay -> {m} lines', flush=True)
                if m is not None and m <= target:
                    with open(f'{bounds2.RES}/improved/{a.key}_{a.case}.txt', 'w') as o:
                        o.write('\n'.join(' '.join(l) for l in prog[:m]) + '\n')
                    open(stop_path, 'w').write(str(m))
                    bounds2.post('win', f'{a.key} case {a.case}: {m} lines (depth-first chain search, not merged yet)')
                    return
                stack.pop()
            continue
        if s == 'INFEASIBLE':
            # no (live) copy of exactly L ticks: was every excluded child a proven dead end?
            if not tr <= dead_keys(read_dead(dead_path), left - 1, budget - L):
                node[5] = False
            node[3] = L + 1
            continue
        # UNKNOWN: give up this length here (not proven)
        node[5] = False
        node[3] = L + 1
    print(f'worker {wid}: stopped, deepest copy {best_depth}/{n}, {solves} solves', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key')
    ap.add_argument('case', type=int)
    ap.add_argument('--procs', type=int, default=14)
    ap.add_argument('--secs', type=float, default=120, help='time limit per solve')
    ap.add_argument('--minutes', type=float, default=60)
    ap.add_argument('--target', type=int, default=None, help='program length to look for (default best-1)')
    a = ap.parse_args()
    cases, best = load(a.key)
    n = cases[a.case][2]
    kb = bounds2.known_bounds(a.key)[a.case]
    F, W = satmodel2.closure(kb['F'], kb['W'], n)
    f1, w1 = F.get(1, 1), W.get(1, 1)
    target = a.target or len(best[a.case]) - 1
    slack = target - (f1 + (n - 1) * w1)
    print(f'{a.key} case {a.case}: n={n} best={len(best[a.case])} looking for a program of {target} lines '
          f'(bound {f1} + {n - 1} x {w1}, slack {slack}), {a.procs} workers, {a.minutes} min', flush=True)
    if slack < 0:
        print('target is below the proven bound: nothing to search', flush=True)
        return
    os.makedirs(WORK, exist_ok=True)
    dead_path = f'{WORK}/dfs_{a.key}_{a.case}_dead2.jsonl'
    stop_path = f'{WORK}/dfs_{a.key}_{a.case}.stop'
    if os.path.exists(stop_path):
        os.remove(stop_path)
    known = {'F': kb['F'], 'W': kb['W']}
    deadline = time.time() + a.minutes * 60
    ps = [mp.Process(target=worker, args=(w, a, n, f1, w1, target, known, deadline, dead_path, stop_path))
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
            for k, _, _ in d:
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
