"""Raise the decomposition lower bounds of large/enormous cases with satmodel2 (climbing).

For each open case (best > lb) the questions W1, F1, W2, F2, ... (W_k: k copies from any
configuration; F_j: j copies from the real start) are climbed from their proven lower value:
ask T = lo; INFEASIBLE -> lo = T+1 and ask again; FEASIBLE -> T is an upper bound, next question;
UNKNOWN (time limit) -> next question.  All bounds proven so far are passed to satmodel2 as
`known` (closed under superadditivity), as recommended in docs/level6-theory.md section 10:
W questions with the default model, F questions with opts canon/swap off.
After every result the case's bound  lb = max_j F_j + B(n - j)  is recomputed (bounds.chain).

Sources of proven bounds: decomp_<key>.csv (bounds.py runs) and close2_<key>.jsonl (this script,
one JSON line per solve, resumable).  Summary per case: results/level6/bounds2_<key>.csv.
An F_n solve that is FEASIBLE below the best length is a shorter program: it is replayed and saved
to results/level6/improved/<key>_<case>.txt (merge with merge_improved.py).

usage: nice -n 10 ~/.ccc-venv/bin/python -u bounds2.py 3-large [--cases 3,17] [--part 0/2]
           [--secs 600] [--workers 4] [--case-budget 1800]
"""
import argparse, csv, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
from bounds import chain
import satmodel2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, 'results', 'level6')
F_OPTS = {'canon': False, 'swap': False}     # dominance rules slow real-start questions down


def post(kind, text):
    d = os.path.join(ROOT, 'work', 'dashboard'); os.makedirs(d, exist_ok=True)
    with open(f'{d}/events.jsonl', 'a') as f:
        f.write(json.dumps(dict(id=f'e{int(time.time() * 1000)}', t=int(time.time()), agent='bounds2',
                                kind=kind, text=text)) + '\n')


def known_bounds(key):
    """{case: {'F': {j: lb}, 'W': {k: lb}, 'Fub': {..}, 'Wub': {..}}} from every recorded result."""
    out = {}

    def put(case, kind, k, v, up=False):
        d = out.setdefault(case, {'F': {}, 'W': {}, 'Fub': {}, 'Wub': {}})
        name = kind + ('ub' if up else '')
        cur = d[name].get(k)
        d[name][k] = v if cur is None else (min(cur, v) if up else max(cur, v))
    p = os.path.join(RES, f'decomp_{key}.csv')
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            c = int(r['case'])
            for kind in ('F', 'W'):
                for a, b in json.loads(r[kind] or '{}').items():
                    put(c, kind, int(a), b)
                for a, b in json.loads(r[kind + 'ub'] or '{}').items():
                    put(c, kind, int(a), b, up=True)
    jsonls = [f'close2_{key}.jsonl'] + (['close_medium.jsonl', 'close_medium2.jsonl'] if key == '2-medium' else [])
    for name in jsonls:
        p = os.path.join(RES, name)
        if not os.path.exists(p):
            continue
        for line in open(p):
            d = json.loads(line)
            kind = d.get('kind', 'W')          # close_medium.jsonl only asked W questions
            if d['status'] == 'INFEASIBLE':
                put(d['case'], kind, d['k'], d['T'] + 1)
            elif d['status'] == 'FEASIBLE':
                put(d['case'], kind, d['k'], d['T'], up=True)
    p = os.path.join(RES, f'exact_{key}.csv')       # whole-program proofs: F_n >= T+1
    if os.path.exists(p):
        cases, _ = load(key)
        for r in csv.DictReader(open(p)):
            if r.get('status') == 'INFEASIBLE':
                c = int(r['case']); put(c, 'F', cases[c][2], int(r['T']) + 1)
    return out


def case_lb(kn, n):
    F, W = satmodel2.closure(kn['F'], kn['W'], n)
    lb = 0
    for j in [0] + sorted(F):
        if j <= n:
            lb = max(lb, (F[j] if j else 0) + (chain(W, n - j) if W and n - j > 0 else n - j))
    return max(lb, F.get(n, 0)), F, W


def summarize(key, cases, best):
    kb = known_bounds(key)
    old = {int(r['case']): int(r['lb'] or 0) for r in csv.DictReader(open(f'{RES}/bounds.csv')) if r['file'] == key}
    rows = []
    for c in range(len(cases)):
        kn = kb.get(c, {'F': {}, 'W': {}, 'Fub': {}, 'Wub': {}})
        lb, F, W = case_lb(kn, cases[c][2])
        lb = max(lb, old.get(c, 0)); b = len(best[c])
        assert lb <= b, (key, c, lb, b)          # a bound above a real program = bug
        rows.append([c, cases[c][2], b, old.get(c, 0), lb, b - lb, json.dumps(F), json.dumps(W)])
    with open(f'{RES}/bounds2_{key}.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['case', 'count', 'best', 'lb_old', 'lb', 'gap', 'F_lb', 'W_lb'])
        w.writerows(rows)
    return {r[0]: r[4] for r in rows}


def questions(n):
    """W1, F1, W2, F2, ...: W_k only for k < n (later copies), F_j up to the whole program."""
    out = []
    for s in range(1, n + 1):
        if s < n:
            out.append(('W', s))
        out.append(('F', s))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key', nargs='?', default='3-large')
    ap.add_argument('--cases', default='open')
    ap.add_argument('--part', default='0/1', help='p/N: every N-th case of the list, starting at p')
    ap.add_argument('--secs', type=float, default=600)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--case-budget', type=float, default=1800)
    a = ap.parse_args()
    cases, best = load(a.key)
    out_path = f'{RES}/close2_{a.key}.jsonl'
    lbs = summarize(a.key, cases, best)
    if a.cases == 'open':
        # open cases, small patterns first (fast solves = most proofs per hour)
        idx = sorted((c for c in range(len(cases)) if lbs[c] < len(best[c])),
                     key=lambda c: (len(LineGeo(*cases[c][:2]).S), c))
    else:
        idx = [int(v) for v in a.cases.split(',')]
    p, N = map(int, a.part.split('/'))
    idx = idx[p::N]
    print(f'{a.key}: {len(idx)} cases in this part', flush=True)
    for c in idx:
        r, g, n = cases[c]
        lg = LineGeo(r, g)
        b = len(best[c]); t_case = time.time()
        lb0 = lbs[c]
        print(f'{a.key} case {c} R={r} n={n} cells={len(lg.S)} best={b} lb={lb0}', flush=True)
        for kind, k in questions(n):
            while time.time() - t_case < a.case_budget:
                kn = known_bounds(a.key).get(c, {'F': {}, 'W': {}, 'Fub': {}, 'Wub': {}})
                lb, F, W = case_lb(kn, n)
                if lb >= b:
                    break
                lo = (W if kind == 'W' else F).get(k, k)
                ub = kn[kind + 'ub'].get(k, b if kind == 'F' and k == n else 10 ** 9)
                if lo >= ub:
                    break                      # settled
                T = lo
                secs = min(a.secs, a.case_budget - (time.time() - t_case))
                if secs < 5:
                    break
                known = {'F': kn['F'], 'W': kn['W']}
                t0 = time.time()
                st, states = satmodel2.solve(lg, T, k, free_start=(kind == 'W'), secs=secs, workers=a.workers,
                                             known=known, opts=None if kind == 'W' else F_OPTS)
                rec = dict(case=c, kind=kind, k=k, T=T, status=st, secs=round(time.time() - t0, 1))
                if states and kind == 'F':
                    prog = program_from_states(lg, states[1:])
                    rep = simulate(lg.geo, prog, k)
                    assert rep is not None and rep <= T, 'F solution does not replay'
                    if k == n and rep < b:      # a shorter whole program
                        with open(f'{RES}/improved/{a.key}_{c}.txt', 'w') as o:
                            o.write('\n'.join(' '.join(l) for l in prog[:rep]) + '\n')
                        print(f'  -> spliced: {b} -> {rep} (whole program)', flush=True)
                        post('win', f'{a.key} case {c}: {b} -> {rep} lines (satmodel2 whole program, not merged yet)')
                        b = rep
                with open(out_path, 'a') as f:
                    f.write(json.dumps(rec) + '\n')
                print(f'  {kind}{k}@{T}: {st} ({rec["secs"]}s)', flush=True)
                if st != 'INFEASIBLE':
                    break
            else:
                break                           # case budget used up
        lbs = summarize(a.key, cases, best)
        msg = f'{a.key} case {c}: lb {lb0} -> {lbs[c]} (best {b}{", optimal" if lbs[c] >= b else ""})'
        print(msg, flush=True)
        if lbs[c] > lb0:
            post('win' if lbs[c] >= b else 'info', msg)


if __name__ == '__main__':
    main()
