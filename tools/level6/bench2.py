"""Benchmark one W_k / F_j question with satmodel or satmodel2 (one JSON line per run).
usage: bench2.py <key> <case> <W|F> <k> <T> <variant> [--secs 600] [--workers 4] [--known '{"W":{"1":5}}']
variant: old | new | new-<opt>=0,... (switch off options of satmodel2) | new+known
Appends to results/level6/bench2.jsonl."""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load, simulate, program_from_states
import satmodel, satmodel2

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'results', 'level6')


def parse_known(s):
    if not s:
        return None
    d = json.loads(s)
    return {kk: {int(a): b for a, b in v.items()} for kk, v in d.items()}


def run(key, case, kind, k, T, variant, secs, workers, known=None, params=None):
    cases, _ = load(key)
    r, g, count = cases[case]
    lg = LineGeo(r, g)
    free = kind == 'W'
    t0 = time.time()
    if variant == 'old':
        st, states = satmodel.solve(lg, T, k, free_start=free, secs=secs, workers=workers)
    else:
        opts = {}
        if '-' in variant:
            for kv in variant.split('-', 1)[1].split(','):
                a, b = kv.split('=')
                opts[a] = bool(int(b))
        st, states = satmodel2.solve(lg, T, k, free_start=free, secs=secs, workers=workers,
                                     known=known if 'known' in variant or known else None,
                                     opts=opts, params=params)
    dt = time.time() - t0
    rep = None
    if states:
        prog = program_from_states(lg, states[1:])
        if free:
            rep = 'free-start (segment)'
        else:
            n = simulate(lg.geo, prog, k)
            assert n is not None and n <= T, 'solution does not replay'
            rep = n
    return dict(key=key, case=case, q=f'{kind}{k}', T=T, variant=variant, known=known, status=st,
                secs=round(dt, 1), workers=workers, replay=rep, states=states)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    for n in ('key', 'case', 'kind', 'k', 'T', 'variant'):
        ap.add_argument(n)
    ap.add_argument('--secs', type=float, default=600)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--known', default='')
    ap.add_argument('--out', default=os.path.join(RES, 'bench2.jsonl'))
    a = ap.parse_args()
    rec = run(a.key, int(a.case), a.kind, int(a.k), int(a.T), a.variant, a.secs, a.workers,
              parse_known(a.known))
    with open(a.out, 'a') as f:
        f.write(json.dumps(rec) + '\n')
    print(f"{a.key} {a.case} {rec['q']}@{a.T} {a.variant} known={a.known}: {rec['status']} {rec['secs']}s",
          flush=True)
