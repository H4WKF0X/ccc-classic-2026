"""Splice segments between detections across ALL candidate programs per case (state after a detection = emitter
config only). DP: cheapest walk of exactly `count` segments from the start config. Verified by simulation.
usage: python3 splice.py <key> ...   -> writes candidates/splice_<time>_<key>.txt if anything improves"""
import sys, os, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cycles import Geo, parse_in, parse_out, simulate, L6

def segments(geo, prog, edges):
    pos = [e * geo.r for e in range(6)]; act = [False] * 6; M = set(); S = set(geo.S); K = set(geo.K)
    frm = (tuple(pos), tuple(act)); start = 0
    for t, line in enumerate(prog):
        if len(line) != 6: return
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
            M -= S; to = (tuple(pos), tuple(act)); seg = prog[start:t + 1]
            if (frm, to) not in edges or len(seg) < len(edges[frm, to]): edges[frm, to] = seg
            frm = to; start = t + 1

def splice_case(geo, progs, count):
    edges = {}
    for p in progs: segments(geo, p, edges)
    startcfg = (tuple(e * geo.r for e in range(6)), (False,) * 6)
    out = {}
    for (a, b), seg in edges.items(): out.setdefault(a, []).append((b, seg))
    dist = {startcfg: (0, None)}; layers = [dist]
    for k in range(count):
        nd = {}
        for a, (d, _) in layers[-1].items():
            for b, seg in out.get(a, []):
                if b not in nd or d + len(seg) < nd[b][0]: nd[b] = (d + len(seg), (a, seg))
        if not nd: return None
        layers.append(nd)
    end = min(layers[-1], key=lambda c: layers[-1][c][0])
    prog = []; c = end
    for k in range(count, 0, -1):
        _, (a, seg) = layers[k][c]; prog = seg + prog; c = a
    return prog

if __name__ == '__main__':
    for key in sys.argv[1:]:
        cases = parse_in(f'{L6}/in/in_level-6_{key}.txt'); best = parse_out(f'{L6}/best/out_level-6_{key}.txt')
        files = glob.glob(f'{L6}/pool/**/*{key}*', recursive=True) + glob.glob(f'{L6}/candidates/*{key}*')
        pool = [best] + [ps for ps in (parse_out(f) for f in files) if len(ps) == len(cases)]
        t0 = time.time(); wins = {}
        for i, (r, g, c) in enumerate(cases):
            geo = Geo(r, g); prog = splice_case(geo, [ps[i] for ps in pool], c)
            if prog and len(prog) < len(best[i]):
                n = simulate(geo, prog, c)
                if n is not None and n < len(best[i]): wins[i] = prog[:n]
        saved = sum(len(best[i]) - len(p) for i, p in wins.items())
        print(f'{key}: {len(pool)} sources, {len(wins)} spliced wins, saved {saved} lines ({time.time()-t0:.0f}s)', flush=True)
        if wins:
            path = f'{L6}/candidates/splice_{time.strftime("%H%M%S")}_{key}.txt'
            with open(path, 'w') as o:
                for j, p in enumerate(best): o.write('\n'.join(' '.join(l) for l in wins.get(j, p)) + '\n\n')
