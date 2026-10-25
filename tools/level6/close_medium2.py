"""Decisive W_k / F_j solves with the stronger model satmodel2 (+ proven bounds as knowledge).

Questions are given as  case:kind:k:T  (kind W = k copies from any configuration, F = from the real
start), e.g.  186:W:3:18,161:F:2:15.  For each question the proven lower bounds of that case
(decomp_2-medium.csv, close_medium.jsonl, close_medium2.jsonl -- INFEASIBLE rows only) are passed
to satmodel2 as `known` (closed under superadditivity).  If they already exceed T the question is
recorded as INFEASIBLE with method 'implied' and no solve.
  INFEASIBLE -> W_k >= T+1 (resp. F_j >= T+1);
  FEASIBLE   -> replayed (F: cycles.simulate; W: the line simulator of test_satmodel2) and saved.
One JSON line per question in results/level6/close_medium2.jsonl (resumable).

usage: nice -n 10 ~/.ccc-venv/bin/python -u close_medium2.py --q 186:W:3:18 --secs 1800 --workers 4
"""
import argparse, csv, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
from test_satmodel2 import sim_lines
import satmodel2

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')
OUT = os.path.join(RES, 'close_medium2.jsonl')


def proven(case, key='2-medium', files=('close_medium.jsonl', 'close_medium2.jsonl')):
    """{'F': {j: lb}, 'W': {k: lb}} from every INFEASIBLE result recorded for this case."""
    d = {'F': {}, 'W': {}}

    def put(kind, k, lb):
        d[kind][k] = max(d[kind].get(k, 0), lb)
    p = os.path.join(RES, f'decomp_{key}.csv')
    for r in csv.DictReader(open(p)):
        if int(r['case']) == case:
            for kind in ('F', 'W'):
                for a, b in json.loads(r[kind]).items():
                    put(kind, int(a), b)
    if key == '2-medium':
        for fn in files:
            p = os.path.join(RES, fn)
            if not os.path.exists(p):
                continue
            for line in open(p):
                rr = json.loads(line)
                if rr['case'] == case and rr['status'] == 'INFEASIBLE':
                    put(rr.get('kind', 'W'), rr['k'], rr['T'] + 1)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--q', required=True, help='case:kind:k:T,...')
    ap.add_argument('--secs', type=float, default=1800)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--climb', action='store_true', help='after INFEASIBLE at T, continue with T+1')
    ap.add_argument('--redo', action='store_true')
    a = ap.parse_args()
    cases, best = load('2-medium')
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            d = json.loads(line)
            done.add((d['case'], d.get('kind', 'W'), d['k'], d['T']))
    for qs in a.q.split(','):
        case, kind, k, T = qs.split(':')
        case, k, T = int(case), int(k), int(T)
        r, g, count = cases[case]
        lg = LineGeo(r, g)
        while True:
            if (case, kind, k, T) in done and not a.redo:
                print(f'case {case} {kind}{k}@{T}: done before', flush=True)
                break
            known = proven(case)
            F, W = satmodel2.closure(known['F'], known['W'], k + 1)
            own = (W if kind == 'W' else F).get(k, 0)
            t0 = time.time()
            if own > T:
                st, states, method = 'INFEASIBLE', None, f'implied (lb {own} by superadditivity)'
            else:
                st, states = satmodel2.solve(lg, T, k, free_start=(kind == 'W'), secs=a.secs,
                                             workers=a.workers, known=known)
                method = 'satmodel2+known'
            rep = None
            if states:
                if kind == 'F':
                    prog = program_from_states(lg, states[1:])
                    rep = simulate(lg.geo, prog, k)
                    assert rep is not None and rep <= T, 'solution does not replay'
                else:
                    dets = sim_lines(lg, states)
                    assert len(dets) >= k, 'solution does not replay'
                    rep = dets
            rec = dict(case=case, kind=kind, k=k, T=T, status=st, secs=round(time.time() - t0, 1),
                       method=method, known=known, replay=rep, states=states)
            with open(OUT, 'a') as f:
                f.write(json.dumps(rec) + '\n')
            done.add((case, kind, k, T))
            print(f'case {case} {kind}{k}@{T}: {st} ({rec["secs"]}s, {method})'
                  + (f'  -> {kind}{k} >= {T + 1}' if st == 'INFEASIBLE' else ''), flush=True)
            if st == 'INFEASIBLE' and a.climb:
                T += 1
                continue
            break


if __name__ == '__main__':
    main()
