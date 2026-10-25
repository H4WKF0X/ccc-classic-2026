"""Where does the plain beam lose lines?  Compares from-scratch beam programs (the `measure` test in
level6.rs) with our best programs, split into first copy and later copies.

  cd solution && L6_MEAS_CASES=<abs list> L6_MEAS_W=800,4000,20000 L6_MEAS_OUT=<abs out> \\
      cargo test --release level6::tests::measure -- --ignored
  ~/.ccc-venv/bin/python tools/level6/measure.py work/level6/measure/all_out.txt
"""
import collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines import LineGeo, load
from multi_cycles import det_ticks_of
import bounds2

rows = collections.defaultdict(dict)
for line in open(sys.argv[1]):
    k, c, w, secs, *prog = line.split()
    rows[(k, int(c))][int(w)] = ([list(l) for l in prog[0].split(';')] if prog else None, float(secs))

data = {}
for key in ('2-medium', '3-large', '4-enormous'):
    cases, best = load(key)
    lbs = bounds2.summarize(key, cases, best)
    for c, (r, g, n) in enumerate(cases):
        if (key, c) not in rows:
            continue
        geo = LineGeo(r, g).geo
        tb = det_ticks_of(geo, best[c])[:n]
        d = dict(key=key, case=c, n=n, cells=len(geo.S), best=len(best[c]), proven=lbs[c] >= len(best[c]),
                 bfirst=tb[0], blater=tb[-1] - tb[0], beam={})
        for w, (prog, secs) in rows[(key, c)].items():
            if prog is None:
                continue
            ts = det_ticks_of(geo, prog)[:n]
            assert len(ts) == n, (key, c, w)
            d['beam'][w] = dict(len=ts[-1], first=ts[0], later=ts[-1] - ts[0], secs=secs)
        data[(key, c)] = d

widths = sorted({w for d in data.values() for w in d['beam']})


def table(title, sel):
    print(f'\n== {title}: {len(sel)} cases')
    print(f'{"width":>7} {"total":>7} {"excess":>7} {"first+":>7} {"later+":>7} {"=best":>6} {"<best":>6} {"cpu-s":>7}')
    print(f'{"best":>7} {sum(d["best"] for d in sel):>7}')
    for w in widths:
        s = [d for d in sel if w in d['beam']]
        tot = sum(d['beam'][w]['len'] for d in s)
        ex = sum(d['beam'][w]['len'] - d['best'] for d in s)
        f = sum(d['beam'][w]['first'] - d['bfirst'] for d in s)
        l = sum(d['beam'][w]['later'] - d['blater'] for d in s)
        eq = sum(d['beam'][w]['len'] == d['best'] for d in s)
        lt = sum(d['beam'][w]['len'] < d['best'] for d in s)
        cpu = sum(d['beam'][w]['secs'] for d in s)
        print(f'{w:>7} {tot:>7} {ex:>+7} {f:>+7} {l:>+7} {eq:>6} {lt:>6} {cpu:>7.0f}')


for key in ('2-medium', '3-large', '4-enormous'):
    sel = [d for d in data.values() if d['key'] == key]
    table(f'{key} all', sel)
    table(f'{key} proven optimal', [d for d in sel if d['proven']])
    for lo, hi in ((0, 30), (30, 60), (60, 100), (100, 400)):
        s = [d for d in sel if lo <= d['cells'] < hi]
        if s:
            table(f'{key} cells {lo}-{hi - 1}', s)
    for n in sorted({d['n'] for d in sel}):
        s = [d for d in sel if d['n'] == n]
        if len(s) >= 10:
            table(f'{key} copies={n}', s)

# cases where the plain beam beats our best: free wins
wins = [(d['key'], d['case'], d['best'], min(v['len'] for v in d['beam'].values()))
        for d in data.values() if d['beam'] and min(v['len'] for v in d['beam'].values()) < d['best']]
print('\nplain beam shorter than our best:', wins)
