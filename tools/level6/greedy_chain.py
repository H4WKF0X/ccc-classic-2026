"""Greedy chaining (heuristic, for finding programs -- proves nothing): start from a recorded
F_j@T solution (close_medium2.jsonl) and repeatedly append one copy in `step` ticks from the current
end configuration (satmodel2 with start_cfg), until `count` copies.  Replayed in cycles.simulate.
usage: greedy_chain.py --case 161 --j 3 --T 22 --step 7 [--look 2] [--secs 300] [--workers 4]"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
import satmodel2
RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')
ap = argparse.ArgumentParser()
for n in ('case', 'j', 'T', 'step'):
    ap.add_argument('--' + n, type=int, required=True)
ap.add_argument('--secs', type=float, default=300)
ap.add_argument('--look', type=int, default=1, help='solve this many copies ahead, keep the first')
ap.add_argument('--workers', type=int, default=4)
a = ap.parse_args()
cases, best = load('2-medium')
r, g, count = cases[a.case]
lg = LineGeo(r, g)
pre = None
for line in open(os.path.join(RES, 'close_medium2.jsonl')):
    d = json.loads(line)
    if (d['case'], d['kind'], d['k'], d['T'], d['status']) == (a.case, 'F', a.j, a.T, 'FEASIBLE'):
        pre = d['states']
full = list(pre)
got = a.j
while got < count:
    t0 = time.time()
    look = min(a.look, count - got)
    st, states = satmodel2.solve(lg, a.step * look, look, start_cfg=(full[-1][0], full[-1][1]), secs=a.secs,
                                 workers=a.workers, known={'W': {1: a.step}})
    if states:
        states = states[:a.step + 1]
    print(f'copy {got + 1}: {st} ({time.time() - t0:.0f}s)', flush=True)
    if not states:
        break
    full += states[1:]
    got += 1
prog = program_from_states(lg, full[1:])
n = simulate(lg.geo, prog, got)
print(f'{got} copies in {len(prog)} lines (simulate -> {n}); best {len(best[a.case])} for {count}')
if got == count and n < len(best[a.case]):
    p = os.path.join(RES, 'exact_programs', f'2-medium_{a.case}_greedy.txt')
    with open(p, 'w') as f:
        f.write('\n'.join(' '.join(x) for x in prog[:n]) + '\n')
    print('SHORTER PROGRAM ->', p)
