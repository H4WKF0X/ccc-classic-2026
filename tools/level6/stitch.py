"""Stitch a full program from a W_k chain found by close_medium2.py: search a real-start prefix of
j copies in T ticks that ends (at its j-th detection, tick T) exactly in the chain's start
configuration.  Right after a detection only the configuration matters (pattern cleared, halo
empty), so prefix + chain is a program with j + k copies; it is replayed in cycles.simulate.
Any remaining copies are appended by repeating the best known program's tail is NOT attempted:
use it when j + k = count.

usage: stitch.py --case 186 --chain-k 3 --chain-T 18 --j 1 --T 8 [--secs 600] [--workers 4]
       stitch.py --case 161 --suffix --j 3 --T 22 --k 4 --Tk 28     (the other way round: take the
           recorded F_j@T solution and search k more copies in Tk ticks from its end configuration)
Writes results/level6/exact_programs/2-medium_<case>_stitched.txt when the result is shorter than best.
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
import satmodel2

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', type=int, required=True)
    ap.add_argument('--chain-k', type=int)
    ap.add_argument('--chain-T', type=int)
    ap.add_argument('--j', type=int, required=True)
    ap.add_argument('--T', type=int, required=True)
    ap.add_argument('--secs', type=float, default=600)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--suffix', action='store_true')
    ap.add_argument('--k', type=int)
    ap.add_argument('--Tk', type=int)
    a = ap.parse_args()
    cases, best = load('2-medium')
    r, g, count = cases[a.case]
    lg = LineGeo(r, g)
    if a.suffix:
        return suffix(a, lg, best, count)
    chain = None
    for line in open(os.path.join(RES, 'close_medium2.jsonl')):
        d = json.loads(line)
        if (d['case'], d['kind'], d['k'], d['T'], d['status']) == (a.case, 'W', a.chain_k, a.chain_T, 'FEASIBLE'):
            chain = d['states']
    assert chain, 'no such chain'
    q0, o0 = chain[0]

    def extra(m, V):
        m.Add(V['det'][a.T] == 1)
        m.Add(sum(V['det'][1:]) == a.j)
        for e in range(6):
            m.Add(V['pos'][e][a.T][q0[e]] == 1)
            m.Add(V['on'][e][a.T] == int(o0[e]))
    t0 = time.time()
    st, states = satmodel2.solve(lg, a.T, a.j, secs=a.secs, workers=a.workers, symbreak=False, extra=extra)
    print(f'prefix {a.j} copies in {a.T} ending in the chain start: {st} ({time.time() - t0:.0f}s)')
    if not states:
        return
    full = states + chain[1:]
    prog = program_from_states(lg, full[1:])
    n = simulate(lg.geo, prog, a.j + a.chain_k)
    print(f'stitched program: {len(prog)} lines, simulate -> {n} (best {len(best[a.case])}, count {count})')
    assert n is not None
    if a.j + a.chain_k == count and n < len(best[a.case]):
        os.makedirs(os.path.join(RES, 'exact_programs'), exist_ok=True)
        p = os.path.join(RES, 'exact_programs', f'2-medium_{a.case}_stitched.txt')
        with open(p, 'w') as f:
            f.write('\n'.join(' '.join(x) for x in prog[:n]) + '\n')
        print('SHORTER PROGRAM ->', p)


def suffix(a, lg, best, count):
    from close_medium2 import proven
    pre = None
    for line in open(os.path.join(RES, 'close_medium2.jsonl')):
        d = json.loads(line)
        if (d['case'], d['kind'], d['k'], d['T'], d['status']) == (a.case, 'F', a.j, a.T, 'FEASIBLE'):
            pre = d['states']
    assert pre, 'no such prefix'
    prog0 = program_from_states(lg, pre[1:])
    n0 = simulate(lg.geo, prog0, a.j)
    assert n0 == a.T, (n0, a.T)             # j-th detection exactly at the end of the prefix
    kn = proven(a.case)
    known = {'W': kn['W']}                  # W bounds hold from any post-detection configuration
    t0 = time.time()
    st, states = satmodel2.solve(lg, a.Tk, a.k, start_cfg=(pre[-1][0], pre[-1][1]), secs=a.secs,
                                 workers=a.workers, known=known)
    print(f'suffix {a.k} copies in {a.Tk} from the end of F{a.j}@{a.T}: {st} ({time.time() - t0:.0f}s)')
    if not states:
        return
    full = pre + states[1:]
    prog = program_from_states(lg, full[1:])
    n = simulate(lg.geo, prog, a.j + a.k)
    print(f'stitched program: {len(prog)} lines, simulate -> {n} (best {len(best[a.case])}, count {count})')
    assert n is not None
    if a.j + a.k == count and n < len(best[a.case]):
        os.makedirs(os.path.join(RES, 'exact_programs'), exist_ok=True)
        p = os.path.join(RES, 'exact_programs', f'2-medium_{a.case}_stitched.txt')
        with open(p, 'w') as f:
            f.write('\n'.join(' '.join(x) for x in prog[:n]) + '\n')
        print('SHORTER PROGRAM ->', p)


if __name__ == '__main__':
    main()
