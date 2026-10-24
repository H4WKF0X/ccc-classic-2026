"""Level 6 cycle finder: per pattern, the shortest repeating lap of emitter configurations that rebuilds
the pattern once per lap (CP-SAT), then program = travel (beams off) + switch on + laps.
usage: ~/.ccc-venv/bin/python cycle.py <file-key e.g. 2-medium> <cases e.g. 3,17 | worst:N> [max_secs_per_solve]
Writes candidates/cycle_<time>_<key>.txt (best file with improved cases replaced) when anything improves."""
import sys, time, os
from ortools.sat.python import cp_model
L6 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'work', 'level6')
DIRS = {1: (0, 2), 2: (1, 1), 3: (1, -1), 4: (0, -2), 5: (-1, -1), 6: (-1, 1)}
NB = [(0, 2), (0, -2), (1, 1), (1, -1), (-1, 1), (-1, -1)]

def tok(r, i, j): return (i, abs(i - r) + 2 * j)
def ring(r):
    last = lambda i: 2 * r - abs(i - r)
    v = [tok(r, i, 0) for i in range(r, 0, -1)] + [tok(r, 0, j) for j in range(r)]
    v += [tok(r, i, last(i)) for i in range(2 * r)] + [tok(r, 2 * r, j) for j in range(r, 0, -1)]
    v += [tok(r, i, 0) for i in range(2 * r, r, -1)]
    return v
def parse_in(path):
    L = [l.strip() for l in open(path) if l.strip()]
    n = int(L[0]); i = 1; cases = []
    for _ in range(n):
        r, rows, cols, c = map(int, L[i].split()); g = L[i + 1:i + 1 + rows]; i += 1 + rows; cases.append((r, g, c))
    return cases
def parse_out(path):
    progs = [[]]
    for l in open(path):
        l = l.strip()
        if not l: progs.append([])
        else: progs[-1].append(l.split())
    return [p for p in progs if p]

class Geo:
    def __init__(s, r, g):
        s.r = r; s.rows = len(g); s.cols = len(g[0]); s.rg = ring(r); s.P = len(s.rg)
        s.cells = {(y, x) for y in range(s.rows) for x in range(s.cols) if g[y][x] in 'OM'}
        s.S = sorted(p for p in s.cells if g[p[0]][p[1]] == 'M')
        s.K = sorted({(y + dy, x + dx) for (y, x) in s.S for dy, dx in NB} & s.cells - set(s.S))
        s.ray = [[s._ray(p, e) for p in range(s.P)] for e in range(6)]
    def _ray(s, p, e):
        (y, x) = s.rg[p]; dy, dx = DIRS[e + 1]; out = []; y += dy; x += dx
        while 0 <= y < s.rows and 0 <= x < s.cols:
            if (y, x) in s.cells: out.append((y, x))
            y += dy; x += dx
        return out

def simulate(geo, prog, count):
    """Number of lines until `count` detections (None if never)."""
    pos = [e * geo.r for e in range(6)]; act = [False] * 6; M = set(); got = 0; S = set(geo.S); K = set(geo.K)
    for t, line in enumerate(prog):
        for e, a in enumerate(line):
            if a == 'F': pos[e] = (pos[e] + 1) % geo.P
            elif a == 'B': pos[e] = (pos[e] - 1) % geo.P
            elif a == 'T': act[e] = not act[e]
        hit = {}
        for e in range(6):
            if act[e]:
                for u in geo.ray[e][pos[e]]: hit[u] = hit.get(u, 0) + 1
        for u, h in hit.items():
            if h == 2: M.add(u)
            elif h >= 3: M.discard(u)
        if S <= M and not (K & M):
            M -= S; got += 1
            if got >= count: return t + 1
    return None

def find_cycle(geo, L, secs):
    m = cp_model.CpModel(); P = geo.P; U = geo.S + geo.K
    x = [[[m.NewBoolVar('') for p in range(P)] for t in range(L)] for e in range(6)]
    a = [[m.NewBoolVar('') for t in range(L)] for e in range(6)]
    acts = [[None] * L for e in range(6)]
    for e in range(6):
        for t in range(L):
            m.AddExactlyOne(x[e][t])
            t1 = (t + 1) % L
            nop, tg, f, b = (m.NewBoolVar('') for _ in range(4))
            m.AddExactlyOne([nop, tg, f, b]); acts[e][t] = (nop, tg, f, b)
            for p in range(P):
                m.Add(x[e][t1][p] == x[e][t][p]).OnlyEnforceIf(nop)
                m.Add(x[e][t1][p] == x[e][t][p]).OnlyEnforceIf(tg)
                m.Add(x[e][t1][(p + 1) % P] == x[e][t][p]).OnlyEnforceIf(f)
                m.Add(x[e][t1][(p - 1) % P] == x[e][t][p]).OnlyEnforceIf(b)
            m.Add(a[e][t1] != a[e][t]).OnlyEnforceIf(tg)
            m.Add(a[e][t1] == a[e][t]).OnlyEnforceIf(tg.Not())
    # y = emitter e on at position p in tick t; only positions whose ray touches U matter
    cover = {u: [] for u in U}
    for e in range(6):
        for t in range(L):
            for p in range(P):
                rc = [u for u in geo.ray[e][p] if u in cover]
                if not rc: continue
                y = m.NewBoolVar(''); m.AddImplication(y, x[e][t][p]); m.AddImplication(y, a[e][t])
                m.AddBoolOr([x[e][t][p].Not(), a[e][t].Not(), y])
                for u in rc: cover[u].append((t, y))
    mt = {}
    for t in range(L):
        for u in U:
            h = sum(y for (tt, y) in cover[u] if tt == t)
            two, three = m.NewBoolVar(''), m.NewBoolVar('')
            if isinstance(h, int):
                m.Add(two == 0); m.Add(three == 0)
            else:
                m.Add(h == 2).OnlyEnforceIf(two); m.Add(h != 2).OnlyEnforceIf(two.Not())
                m.Add(h >= 3).OnlyEnforceIf(three); m.Add(h <= 2).OnlyEnforceIf(three.Not())
            if t == 0:
                mt[t, u] = two
            else:
                keep, mu = m.NewBoolVar(''), m.NewBoolVar('')
                m.AddBoolAnd([mt[t - 1, u], three.Not()]).OnlyEnforceIf(keep)
                m.AddBoolOr([mt[t - 1, u].Not(), three]).OnlyEnforceIf(keep.Not())
                m.AddBoolOr([two, keep]).OnlyEnforceIf(mu)
                m.AddBoolAnd([two.Not(), keep.Not()]).OnlyEnforceIf(mu.Not())
                mt[t, u] = mu
    for u in geo.S: m.Add(mt[L - 1, u] == 1)
    for u in geo.K: m.Add(mt[L - 1, u] == 0)
    for t in range(L - 1):
        m.AddBoolOr([mt[t, u].Not() for u in geo.S] + [mt[t, u] for u in geo.K])
    sol = cp_model.CpSolver(); sol.parameters.max_time_in_seconds = secs; sol.parameters.num_workers = 4
    st = sol.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, sol.StatusName(st)
    pos = [[next(p for p in range(P) if sol.Value(x[e][t][p])) for t in range(L)] for e in range(6)]
    on = [[bool(sol.Value(a[e][t])) for t in range(L)] for e in range(6)]
    act = [['-TFB'[[sol.Value(v) for v in acts[e][t]].index(1)] for t in range(L)] for e in range(6)]
    return (pos, on, act), 'OK'

def build_program(geo, cyc, count):
    pos, on, act = cyc; L = len(pos[0]); P = geo.P
    start = [e * geo.r for e in range(6)]
    moves = []
    for e in range(6):
        d = (pos[e][L - 1] - start[e]) % P
        moves.append(['F'] * d if d <= P - d else ['B'] * (P - d))
    D = max(len(mv) for mv in moves)
    prog = [[moves[e][t] if t < len(moves[e]) else '-' for e in range(6)] for t in range(D)]
    if any(on[e][L - 1] for e in range(6)):
        prog.append(['T' if on[e][L - 1] else '-' for e in range(6)])
    lap = [[act[e][(t - 1) % L] for e in range(6)] for t in range(L)]
    while len(prog) < D + 1 + L * (count + 1):
        prog += lap
    n = simulate(geo, prog, count)
    return prog[:n] if n else None

if __name__ == '__main__':
    key = sys.argv[1]; secs = float(sys.argv[3]) if len(sys.argv) > 3 else 10
    cases = parse_in(f'{L6}/in/in_level-6_{key}.txt'); best = parse_out(f'{L6}/best/out_level-6_{key}.txt')
    sel = sys.argv[2]
    if sel.startswith('worst:'):
        k = int(sel.split(':')[1])
        idx = sorted(range(len(cases)), key=lambda i: -len(best[i]) / max(cases[i][2], 1))[:k]
    else:
        idx = [int(v) for v in sel.split(',')]
    improved = dict(); t0 = time.time()
    for i in idx:
        r, g, c = cases[i]; geo = Geo(r, g); cur = len(best[i])
        line = f'case {i:3d} r={r} cells={len(geo.S)} skirt={len(geo.K)} count={c} best={cur}:'
        for L in range(1, int(os.environ.get("MAXL", "4")) + 1):
            t1 = time.time(); cyc, st = find_cycle(geo, L, secs)
            line += f' L{L}={st}({time.time()-t1:.0f}s)'
            if cyc:
                prog = build_program(geo, cyc, c)
                if prog:
                    line += f' -> {len(prog)} lines'
                    if len(prog) < cur: improved[i] = prog; line += ' BETTER'
                break
        print(line, flush=True)
    if improved:
        out = [improved.get(i, p) for i, p in enumerate(best)]
        path = f'{L6}/candidates/cycle_{time.strftime("%H%M%S")}_{key}.txt'
        with open(path, 'w') as o:
            for p in out: o.write('\n'.join(' '.join(l) for l in p) + '\n\n')
        print(f'improved {len(improved)} cases, saved {sum(len(best[i]) - len(p) for i, p in improved.items())} lines -> {path}')
    print(f'done in {time.time()-t0:.0f}s')
