"""Differential test satmodel2 vs satmodel (safeguard 3) on questions satmodel has decided.

Instances (all 2-medium):
  * regression list: hard decisions satmodel needed minutes for (close_medium.jsonl, INFEASIBLE);
  * whole-program proofs: a sample of the INFEASIBLE rows of exact_2-medium.csv (real start, T=best-1);
  * FEASIBLE ones: real programs at T=best (exact sample), and every FEA probe in the decomposition
    logs (decomp_2-medium.csv), plus the INF probes there.
Each instance is solved with satmodel2 'pure' (no knowledge) and 'known' (proven bounds of smaller
questions plus the own question's bound capped at T, so the answer is never implied for free).
A disagreement (INFEASIBLE vs FEASIBLE) is a bug: it is printed as DISAGREE and the run stops.
FEASIBLE answers are replayed (real start: cycles.simulate, free start: line simulator).
One JSON line per instance and variant in results/level6/diff_satmodel2.jsonl (resumable).

usage: diff_satmodel2.py --set regression|exact|decomp [--sample 40] [--secs 900] [--workers 4]
"""
import argparse, csv, json, os, random, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
from test_satmodel2 import sim_lines
from close_medium2 import proven
import satmodel2

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')
OUT = os.path.join(RES, 'diff_satmodel2.jsonl')
KEY = '2-medium'


def instances(which, sample, seed):
    cases, best = load(KEY)
    out = []        # (case, kind, k, T, old_status, old_secs, source)
    if which == 'regression':
        for line in open(os.path.join(RES, 'close_medium.jsonl')):
            d = json.loads(line)
            if d['status'] in ('INFEASIBLE', 'FEASIBLE'):
                out.append((d['case'], 'W', d['k'], d['T'], d['status'], d['secs'], 'close_medium'))
    elif which == 'exact':
        rows = [r for r in csv.DictReader(open(os.path.join(RES, f'exact_{KEY}.csv')))
                if r['status'] == 'INFEASIBLE']
        last = {}
        for r in rows:
            last[int(r['case'])] = r
        rows = sorted(last.values(), key=lambda r: int(r['case']))
        rnd = random.Random(seed)
        pick = rnd.sample(rows, min(sample, len(rows)))
        # bias towards the slower proofs: always include the 10 slowest
        slow = sorted(rows, key=lambda r: -float(r['secs']))[:10]
        seen = set()
        for r in slow + pick:
            c = int(r['case'])
            if c in seen:
                continue
            seen.add(c)
            out.append((c, 'F', cases[c][2], int(r['T']), 'INFEASIBLE', float(r['secs']), 'exact'))
            out.append((c, 'F', cases[c][2], int(r['T']) + 1, 'FEASIBLE', None, 'exact(best program)'))
    elif which == 'decomp':
        for r in csv.DictReader(open(os.path.join(RES, f'decomp_{KEY}.csv'))):
            c = int(r['case'])
            for kind, k, T, st, secs in re.findall(r'([WF])(\d+)@(\d+):(INF|FEA)\((\d+)s\)', r['log']):
                out.append((c, kind, int(k), int(T), 'INFEASIBLE' if st == 'INF' else 'FEASIBLE',
                            float(secs), 'decomp'))
        out = sorted(set(out))
        if sample and len(out) > sample:
            rnd = random.Random(seed)
            out = rnd.sample(out, sample)
    return out


def known_for(case, kind, k, T):
    """Bounds proven by satmodel (decomp + close_medium) for *other, smaller* questions only:
    W_k' for k' < k (and k' <= k for an F question), F_j' for j' < k, and for the own question only
    probes at a smaller horizon T' < T.  So nothing derived from the instance under test is used."""
    p = proven(case, files=('close_medium.jsonl',))
    kn = {'F': {}, 'W': {}}
    for kk, lb in p['W'].items():
        if kk < k or (kind == 'F' and kk == k):
            kn['W'][kk] = lb
    if kind == 'F':
        for kk, lb in p['F'].items():
            if kk < k:
                kn['F'][kk] = lb
    # own question: only probes at a smaller horizon T' < T (different instances) count
    own_lb = 0
    for r in csv.DictReader(open(os.path.join(RES, f'decomp_{KEY}.csv'))):
        if int(r['case']) == case:
            for kd, kk, TT, st, _ in re.findall(r'([WF])(\d+)@(\d+):(INF|FEA)\((\d+)s\)', r['log']):
                if kd == kind and int(kk) == k and st == 'INF' and int(TT) < T:
                    own_lb = max(own_lb, int(TT) + 1)
    for line in open(os.path.join(RES, 'close_medium.jsonl')):
        d = json.loads(line)
        if d['case'] == case and kind == 'W' and d['k'] == k and d['status'] == 'INFEASIBLE' and d['T'] < T:
            own_lb = max(own_lb, d['T'] + 1)
    if own_lb:
        kn[kind][k] = own_lb
    F, W = satmodel2.closure(kn['F'], kn['W'], k + 1)
    own = (W if kind == 'W' else F).get(k, 0)
    return kn, own


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', required=True, choices=['regression', 'exact', 'decomp'])
    ap.add_argument('--sample', type=int, default=40)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--secs', type=float, default=900)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--variants', default='pure,known')
    ap.add_argument('--cases', default='', help='restrict to these cases')
    a = ap.parse_args()
    cases, best = load(KEY)
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            d = json.loads(line)
            done.add((d['case'], d['kind'], d['k'], d['T'], d['variant']))
    inst = instances(a.set, a.sample, a.seed)
    if a.cases:
        cs = {int(x) for x in a.cases.split(',')}
        inst = [x for x in inst if x[0] in cs]
    print(f'{len(inst)} instances', flush=True)
    for case, kind, k, T, old, old_secs, src in inst:
        r, g, count = cases[case]
        lg = LineGeo(r, g)
        for var in a.variants.split(','):
            if (case, kind, k, T, var) in done:
                continue
            known = None
            if var == 'known':
                known, own = known_for(case, kind, k, T)
                if not any(known.values()):
                    continue            # nothing known: identical to 'pure'
                if own > T:
                    if old == 'FEASIBLE':
                        print(f'DISAGREE bounds {known} exclude FEASIBLE case {case} {kind}{k}@{T}', flush=True)
                        sys.exit(1)
                    continue            # answer implied by smaller questions: not a test
            t0 = time.time()
            st, states = satmodel2.solve(lg, T, k, free_start=(kind == 'W'), secs=a.secs,
                                         workers=a.workers, known=known)
            dt = time.time() - t0
            rep = None
            if states:
                if kind == 'F':
                    rep = simulate(lg.geo, program_from_states(lg, states[1:]), k)
                    assert rep is not None and rep <= T, 'solution does not replay'
                else:
                    rep = sim_lines(lg, states)
                    assert len(rep) >= k, 'solution does not replay'
            bad = {st, old} == {'INFEASIBLE', 'FEASIBLE'}
            rec = dict(case=case, kind=kind, k=k, T=T, variant=var, status=st, secs=round(dt, 1),
                       old=old, old_secs=old_secs, source=src, known=known, replay=rep, agree=not bad)
            with open(OUT, 'a') as f:
                f.write(json.dumps(rec) + '\n')
            print(f"case {case:3d} {kind}{k}@{T} {var:5s}: {st} {dt:.1f}s   old: {old} {old_secs}s ({src})"
                  + ('   DISAGREE' if bad else ''), flush=True)
            if bad:
                sys.exit(1)


if __name__ == '__main__':
    main()
