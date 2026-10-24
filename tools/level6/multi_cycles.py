"""Multi-copy cycles: a closed walk of L ticks containing k copies (detections at chosen ticks, emitter states
free in between). Searches only cycles with fewer ticks per copy than the current best program.
usage: ~/.ccc-venv/bin/python -u cycle2.py <key> [--workers 8] [--secs 10] [--maxk 3] [--cases all|1,2]
Writes candidates/cycle2_<time>_<key>.txt after every win (best file + improved cases)."""
import sys, os, time, argparse
from multiprocessing import Pool
from ortools.sat.python import cp_model
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cycles import Geo, parse_in, parse_out, simulate, L6

def find_cycle(geo, L, dets, secs):
    """dets: sorted tick indices (last must be L-1) at which a copy is detected."""
    m = cp_model.CpModel(); P = geo.P; U = geo.S + geo.K
    x = [[[m.NewBoolVar('') for p in range(P)] for t in range(L)] for e in range(6)]
    a = [[m.NewBoolVar('') for t in range(L)] for e in range(6)]
    acts = [[None] * L for e in range(6)]
    for e in range(6):
        for t in range(L):
            m.AddExactlyOne(x[e][t]); t1 = (t + 1) % L
            nop, tg, f, b = (m.NewBoolVar('') for _ in range(4))
            m.AddExactlyOne([nop, tg, f, b]); acts[e][t] = (nop, tg, f, b)
            for p in range(P):
                m.Add(x[e][t1][p] == x[e][t][p]).OnlyEnforceIf(nop)
                m.Add(x[e][t1][p] == x[e][t][p]).OnlyEnforceIf(tg)
                m.Add(x[e][t1][(p + 1) % P] == x[e][t][p]).OnlyEnforceIf(f)
                m.Add(x[e][t1][(p - 1) % P] == x[e][t][p]).OnlyEnforceIf(b)
            m.Add(a[e][t1] != a[e][t]).OnlyEnforceIf(tg); m.Add(a[e][t1] == a[e][t]).OnlyEnforceIf(tg.Not())
    cover = {u: [] for u in U}
    for e in range(6):
        for t in range(L):
            for p in range(P):
                rc = [u for u in geo.ray[e][p] if u in cover]
                if not rc: continue
                y = m.NewBoolVar(''); m.AddImplication(y, x[e][t][p]); m.AddImplication(y, a[e][t])
                m.AddBoolOr([x[e][t][p].Not(), a[e][t].Not(), y])
                for u in rc: cover[u].append((t, y))
    dset = set(dets); mt = {}
    for t in range(L):
        fresh = (t == 0) or ((t - 1) in dset)          # pattern area empty before this tick
        for u in U:
            h = sum(y for (tt, y) in cover[u] if tt == t)
            two, three = m.NewBoolVar(''), m.NewBoolVar('')
            if isinstance(h, int): m.Add(two == 0); m.Add(three == 0)
            else:
                m.Add(h == 2).OnlyEnforceIf(two); m.Add(h != 2).OnlyEnforceIf(two.Not())
                m.Add(h >= 3).OnlyEnforceIf(three); m.Add(h <= 2).OnlyEnforceIf(three.Not())
            if fresh: mt[t, u] = two
            else:
                keep, mu = m.NewBoolVar(''), m.NewBoolVar('')
                m.AddBoolAnd([mt[t - 1, u], three.Not()]).OnlyEnforceIf(keep)
                m.AddBoolOr([mt[t - 1, u].Not(), three]).OnlyEnforceIf(keep.Not())
                m.AddBoolOr([two, keep]).OnlyEnforceIf(mu); m.AddBoolAnd([two.Not(), keep.Not()]).OnlyEnforceIf(mu.Not())
                mt[t, u] = mu
        if t in dset:
            for u in geo.S: m.Add(mt[t, u] == 1)
            for u in geo.K: m.Add(mt[t, u] == 0)
        else:
            m.AddBoolOr([mt[t, u].Not() for u in geo.S] + [mt[t, u] for u in geo.K])
    sol = cp_model.CpSolver(); sol.parameters.max_time_in_seconds = secs; sol.parameters.num_workers = 2
    st = sol.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return None, sol.StatusName(st)
    pos = [[next(p for p in range(P) if sol.Value(x[e][t][p])) for t in range(L)] for e in range(6)]
    on = [[bool(sol.Value(a[e][t])) for t in range(L)] for e in range(6)]
    act = [['-TFB'[[sol.Value(v) for v in acts[e][t]].index(1)] for t in range(L)] for e in range(6)]
    return (pos, on, act), 'OK'

def build_program(geo, cyc, count):
    pos, on, act = cyc; L = len(pos[0]); P = geo.P; start = [e * geo.r for e in range(6)]
    moves = []
    for e in range(6):
        d = (pos[e][L - 1] - start[e]) % P
        moves.append(['F'] * d if d <= P - d else ['B'] * (P - d))
    D = max(len(mv) for mv in moves)
    prog = [[moves[e][t] if t < len(moves[e]) else '-' for e in range(6)] for t in range(D)]
    if any(on[e][L - 1] for e in range(6)): prog.append(['T' if on[e][L - 1] else '-' for e in range(6)])
    lap = [[act[e][(t - 1) % L] for e in range(6)] for t in range(L)]
    while len(prog) < D + 1 + L * (count + 1): prog += lap
    n = simulate(geo, prog, count)
    return prog[:n] if n else None

def det_ticks_of(geo, prog):
    pos = [e * geo.r for e in range(6)]; act = [False] * 6; M = set(); S = set(geo.S); K = set(geo.K); ts = []
    for t, line in enumerate(prog):
        for e, a_ in enumerate(line):
            if a_ == 'F': pos[e] = (pos[e] + 1) % geo.P
            elif a_ == 'B': pos[e] = (pos[e] - 1) % geo.P
            elif a_ == 'T': act[e] = not act[e]
        hit = {}
        for e in range(6):
            if act[e]:
                for u in geo.ray[e][pos[e]]: hit[u] = hit.get(u, 0) + 1
        for u, h in hit.items():
            if h == 2: M.add(u)
            elif h >= 3: M.discard(u)
        if S <= M and not (K & M): M -= S; ts.append(t + 1)
    return ts

def job(args):
    i, (r, g, c), cur_prog, secs, maxk = args
    geo = Geo(r, g); cur = len(cur_prog); t0 = time.time()
    ts = det_ticks_of(geo, cur_prog); gaps = [b - a for a, b in zip(ts, ts[1:])]
    if c < 3 or not gaps: return i, cur, None, 'skip', 0
    per = sum(gaps) / len(gaps); tried = []
    best = None
    for k in range(2, maxk + 1):
        for L in range(2 * k, int(per * k - 1e-9) + 1):          # strictly fewer ticks per copy than now
            if L / k >= per - 1e-9: break
            # segment lengths >= 2 summing to L, first segment the shortest (rotation symmetry)
            def splits(rem, parts, mn):
                if parts == 1:
                    if rem >= mn: yield [rem]
                    return
                for s in range(mn, rem - mn * (parts - 1) + 1): 
                    for rest in splits(rem - s, parts - 1, mn): yield [s] + rest
            done = False
            for seg in splits(L, k, 2):
                if seg[0] != min(seg): continue
                dets = []; acc = 0
                for s in seg: acc += s; dets.append(acc - 1)
                cyc, st = find_cycle(geo, L, dets, secs); tried.append(f'k{k}L{L}{seg}:{st[:4]}')
                if cyc:
                    prog = build_program(geo, cyc, c)
                    if prog and len(prog) < cur and (best is None or len(prog) < len(best)): best = prog
                    done = True; break
                if time.time() - t0 > 6 * secs: break
            if done or time.time() - t0 > 6 * secs: break
    return i, cur, best, f'per-copy {per:.2f} tried ' + ' '.join(tried[-4:]), time.time() - t0

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('key'); ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--secs', type=float, default=10); ap.add_argument('--maxk', type=int, default=3); ap.add_argument('--cases', default='all')
    A = ap.parse_args()
    cases = parse_in(f'{L6}/in/in_level-6_{A.key}.txt'); best = parse_out(f'{L6}/best/out_level-6_{A.key}.txt')
    idx = list(range(len(cases))) if A.cases == 'all' else [int(v) for v in A.cases.split(',')]
    cand = f'{L6}/candidates/cycle2_{time.strftime("%H%M%S")}_{A.key}.txt'; wins = {}; t0 = time.time(); n = 0
    print(f'{A.key}: {len(idx)} cases, workers={A.workers} secs={A.secs} maxk={A.maxk}', flush=True)
    with Pool(A.workers) as pool:
        for i, cur, prog, msg, dt in pool.imap_unordered(job, [(i, cases[i], best[i], A.secs, A.maxk) for i in idx]):
            n += 1
            line = f'[{n}/{len(idx)} {time.time()-t0:.0f}s] case {i:3d} best {cur:3d}: {msg} ({dt:.0f}s)'
            if prog is not None:
                wins[i] = prog; line += f' -> {len(prog)} WIN -{cur-len(prog)}'
                with open(cand, 'w') as o:
                    for j, p in enumerate(best): o.write('\n'.join(' '.join(l) for l in wins.get(j, p)) + '\n\n')
            print(line, flush=True)
    print(f'DONE: {len(wins)} wins, saved {sum(len(best[i]) - len(p) for i, p in wins.items())} lines', flush=True)
