"""Stronger exact CP-SAT model of Level 6 in line coordinates -- drop-in for satmodel.solve.

Same question, same variables exposed to `extra` (V = dict(pos, on, det, mt, c)), same return value.
The base model (dynamics, hit counts, matter, forced detection) is identical to satmodel.py.  On top
of it come only additions that hold for every valid program, or that keep at least one program of
every class of equivalent programs.  The derivations are in docs/level6-theory.md, section
"Stronger model"; the groups below match its subsections.

  (A) valid cuts (always on; accept every program -- tested on the whole pool):
      integer line position q per emitter with |q_t - q_{t-1}| <= 1 - toggle (channelled to the
      one-hot), at-most-one beam line per emitter and tick, per-axis line counts.
  (B) dominance / symmetry (only with symbreak=True and no start_cfg; they discard programs but
      always keep an equivalent one, which fires exactly the same beams):
      B1  free start: the configuration at t=0 equals the one at t=1 (t=0 never fires);
      B2  unlit stretches (emitter off, or on but aiming at a line that misses pattern+halo, with no
          toggle inside): positions inside are irrelevant, so moves are monotone and as early as
          possible; with a free start an initial stretch has no moves at all, and a stretch that
          reaches T has no moves at all;
      B3  twins e / e+3 lexicographically ordered (as in satmodel);
      B4  lex-leader constraints for every automorphism of (pattern, halo) in line space
          (axis permutation + line reversal); real start is invariant too.
  (C) knowledge (only when `known` is given; uses lower bounds proven earlier):
      known = {'F': {j: lb}, 'W': {k: lb}}: F_j / W_k = fewest ticks for j copies from the real start
      / k copies from any configuration.  Then the j-th detection is at tick >= F_j (or W_j), any
      L = W_i consecutive ticks hold <= i detections, and if T is minimal for this question
      (lb >= T) the last detection is at T and no tick is a removable no-op (a tick where nothing
      moves or toggles and no detection happened the tick before).

`known` must only contain bounds proven INFEASIBLE by an exact model; it is the caller's duty.
"""
from itertools import permutations, product
from ortools.sat.python import cp_model


def automorphisms(lg):
    """Non-identity maps (perm, rev) of line triples that map pattern onto pattern and halo onto halo:
    axis a -> perm[a], line l -> nl-1-l if rev[a]."""
    S, K, nl = set(lg.S), set(lg.K), lg.nl
    out = []
    for perm in permutations(range(3)):
        for rev in product((0, 1), repeat=3):
            if perm == (0, 1, 2) and rev == (0, 0, 0):
                continue

            def f(u):
                v = [0, 0, 0]
                for a in range(3):
                    v[perm[a]] = nl - 1 - u[a] if rev[a] else u[a]
                return tuple(v)
            if {f(u) for u in S} == S and {f(u) for u in K} == K:
                out.append((perm, rev))
    return out


def closure(F, W, kmax):
    """Max-plus closure of proven bounds: W_{i+j} >= W_i + W_j, F_{i+j} >= F_i + W_j."""
    W = dict(W or {})
    F = dict(F or {})
    for n in range(1, kmax + 1):
        best = W.get(n, 0)
        for i in range(1, n):
            if i in W and (n - i) in W:
                best = max(best, W[i] + W[n - i])
        if best:
            W[n] = best
    for n in range(1, kmax + 1):
        best = F.get(n, 0)
        for i in range(1, n):
            if i in F and (n - i) in W:
                best = max(best, F[i] + W[n - i])
        if best:
            F[n] = best
    return F, W


def _lex_leq(m, A, B):
    """Post A <=_lex B for equal-length lists of (expr, key) pairs; positions whose keys are equal
    are identical expressions and skipped."""
    eq = None
    for (a, ka), (b, kb) in zip(A, B):
        if ka == kb:
            continue
        same = m.NewBoolVar('')
        m.Add(a == b).OnlyEnforceIf(same)
        m.Add(a != b).OnlyEnforceIf(same.Not())
        if eq is None:
            m.Add(a <= b)
            eq = same
        else:
            m.Add(a <= b).OnlyEnforceIf(eq)
            nxt = m.NewBoolVar('')
            m.AddBoolAnd([eq, same]).OnlyEnforceIf(nxt)
            m.AddBoolOr([eq.Not(), same.Not()]).OnlyEnforceIf(nxt.Not())
            eq = nxt


DEFAULT_OPTS = dict(cuts=True, canon=True, auto=True, noop=True, dettime=True)


def solve(lg, T, k, free_start=False, secs=60.0, workers=1, hint=None, extra=None, symbreak=True,
          start_cfg=None, known=None, opts=None, params=None):
    """Returns (status_name, states) where states = [(q[6], on[6]) for t in 0..T] when feasible.
    Arguments as satmodel.solve, plus
      known: {'F': {j: lb}, 'W': {k: lb}} proven lower bounds (see module doc, group C);
      opts:  feature switches (DEFAULT_OPTS) -- for benchmarking only;
      params: extra CP-SAT parameters {name: value}."""
    o = dict(DEFAULT_OPTS, **(opts or {}))
    if start_cfg is not None:
        free_start, symbreak = True, False      # fixed but arbitrary start: twins no longer symmetric
    real_start = not free_start
    m = cp_model.CpModel()
    nq = lg.nq
    U = lg.S + lg.K
    nS = len(lg.S)
    used = [sorted({u[a] for u in U}) for a in range(3)]          # lines that touch pattern/halo
    pos = [[[m.NewBoolVar(f'p{e}_{t}_{q}') for q in range(nq)] for t in range(T + 1)] for e in range(6)]
    on = [[m.NewBoolVar(f'o{e}_{t}') for t in range(T + 1)] for e in range(6)]
    tog = [[None] * (T + 1) for e in range(6)]
    for e in range(6):
        for t in range(T + 1):
            m.AddExactlyOne(pos[e][t])
        if start_cfg is not None:
            m.Add(pos[e][0][start_cfg[0][e]] == 1)
            m.Add(on[e][0] == int(start_cfg[1][e]))
        elif real_start:
            m.Add(pos[e][0][lg.start_q] == 1)
            m.Add(on[e][0] == 0)
        for t in range(1, T + 1):
            P0, P1 = pos[e][t - 1], pos[e][t]
            tg = tog[e][t] = m.NewBoolVar(f'g{e}_{t}')
            m.Add(on[e][t] != on[e][t - 1]).OnlyEnforceIf(tg)
            m.Add(on[e][t] == on[e][t - 1]).OnlyEnforceIf(tg.Not())
            for q in range(nq):
                m.AddBoolOr([P0[j] for j in (q - 1, q, q + 1) if 0 <= j < nq]).OnlyEnforceIf(P1[q])
                m.Add(P1[q] == P0[q]).OnlyEnforceIf(tg)

    # ---- (A) integer positions and moves (valid for every program) -----------------------------
    qv = [[None] * (T + 1) for e in range(6)]
    up = [[None] * (T + 1) for e in range(6)]
    dn = [[None] * (T + 1) for e in range(6)]
    for e in range(6):
        for t in range(T + 1):
            qv[e][t] = m.NewIntVar(0, nq - 1, f'q{e}_{t}')
            m.Add(qv[e][t] == sum(q * pos[e][t][q] for q in range(nq)))
        for t in range(1, T + 1):
            u_, d_ = up[e][t], dn[e][t] = m.NewBoolVar(f'u{e}_{t}'), m.NewBoolVar(f'd{e}_{t}')
            m.Add(qv[e][t] - qv[e][t - 1] == u_ - d_)
            m.AddAtMostOne([u_, d_, tog[e][t]])         # a tick is one action: move up, down, or toggle
            if o['cuts']:
                # moving up into q needs q-1 before; down needs q+1 before (pure channelling)
                for q in range(nq):
                    if q == 0:
                        m.AddImplication(pos[e][t][0], u_.Not())
                    else:
                        m.AddImplication(pos[e][t][q], pos[e][t - 1][q - 1]).OnlyEnforceIf(u_)
                    if q == nq - 1:
                        m.AddImplication(pos[e][t][q], d_.Not())
                    else:
                        m.AddImplication(pos[e][t][q], pos[e][t - 1][q + 1]).OnlyEnforceIf(d_)

    # z[e][t][l] = emitter e active and aiming at line l (only lines touching pattern/halo)
    z = [[{} for t in range(T + 1)] for e in range(6)]
    lit = [[None] * (T + 1) for e in range(6)]
    for e in range(6):
        a = e % 3
        for t in range(T + 1):
            for l in used[a]:
                v = m.NewBoolVar(f'z{e}_{t}_{l}')
                p = pos[e][t][l + 1]
                m.AddImplication(v, p)
                m.AddImplication(v, on[e][t])
                m.AddBoolOr([p.Not(), on[e][t].Not(), v])
                z[e][t][l] = v
            lt = lit[e][t] = m.NewBoolVar(f'lit{e}_{t}')
            m.Add(sum(z[e][t].values()) == lt)          # at most one beam line, lit = has a beam on U
    # c[a][t][l] = [z_a, z_a+3] (same layout as satmodel, for `extra`)
    c = [[{} for t in range(T + 1)] for a in range(3)]
    for t in range(1, T + 1):
        for a in range(3):
            for l in used[a]:
                c[a][t][l] = [z[a][t][l], z[a + 3][t][l]]

    # ---- (B) dominance and symmetry breaking ---------------------------------------------------
    if symbreak:
        if free_start and o['canon']:
            # B1: t=0 never fires; its only role is to precede t=1 -> take it equal to t=1
            for e in range(6):
                m.Add(qv[e][0] == qv[e][1])
                m.Add(on[e][0] == on[e][1])
        if o['canon'] and T >= 1:
            for e in range(6):
                # B2 local windows: ticks t-1, t, t+1 unlit, no toggle into t or t+1
                for t in range(1, T):
                    cond = [lit[e][t - 1].Not(), lit[e][t].Not(), lit[e][t + 1].Not(),
                            tog[e][t].Not(), tog[e][t + 1].Not()]
                    neg = [x.Not() for x in cond]
                    # no reversal
                    m.AddBoolOr(neg + [up[e][t].Not(), dn[e][t + 1].Not()])
                    m.AddBoolOr(neg + [dn[e][t].Not(), up[e][t + 1].Not()])
                    # no stay followed by a move (moves as early as possible)
                    m.AddBoolOr(neg + [up[e][t], dn[e][t], up[e][t + 1].Not()])
                    m.AddBoolOr(neg + [up[e][t], dn[e][t], dn[e][t + 1].Not()])
                # end rule: a stretch that reaches T has no moves
                suf = lit[e][T].Not()
                for t in range(T - 1, -1, -1):
                    s = m.NewBoolVar('')
                    m.AddBoolAnd([lit[e][t].Not(), tog[e][t + 1].Not(), suf]).OnlyEnforceIf(s)
                    m.AddBoolOr([lit[e][t], tog[e][t + 1], suf.Not()]).OnlyEnforceIf(s.Not())
                    # s: ticks t..T are one unlit stretch -> no move into t+1
                    m.AddImplication(s, up[e][t + 1].Not())
                    m.AddImplication(s, dn[e][t + 1].Not())
                    suf = s
                # start rule (free start only): an initial stretch has no moves
                if free_start:
                    pre = lit[e][0].Not()
                    for t in range(1, T + 1):
                        s = m.NewBoolVar('')
                        m.AddBoolAnd([pre, lit[e][t].Not(), tog[e][t].Not()]).OnlyEnforceIf(s)
                        m.AddBoolOr([pre.Not(), lit[e][t], tog[e][t]]).OnlyEnforceIf(s.Not())
                        m.AddImplication(s, up[e][t].Not())
                        m.AddImplication(s, dn[e][t].Not())
                        pre = s
        # B3 + B4: lex-leader for twin swaps and pattern automorphisms, one global order:
        # emitter-major, ticks t0..T, value 2q+on
        t0 = 0 if free_start else 1
        val = lambda e, t, rev: (2 * ((nq - 1) - qv[e][t] if rev else qv[e][t]) + on[e][t],
                                 (e, t, rev))
        X = [val(e, t, False) for e in range(6) for t in range(t0, T + 1)]
        groups = []
        for a in range(3):          # twin swap of axis a
            img = list(range(6))
            img[a], img[a + 3] = a + 3, a
            groups.append((img, [0] * 6))
        if o['auto']:
            for perm, rev in automorphisms(lg):
                img = [perm[e % 3] + 3 * (e // 3) for e in range(6)]     # emitter e -> img[e]
                groups.append((img, [rev[e % 3] for e in range(6)]))
        for img, rv in groups:
            inv = [0] * 6
            for e in range(6):
                inv[img[e]] = e
            # g(X) at emitter e' = transformed trajectory of emitter inv[e']
            GX = [val(inv[e], t, bool(rv[inv[e]])) for e in range(6) for t in range(t0, T + 1)]
            _lex_leq(m, X, GX)

    # ---- base matter model (as satmodel) -------------------------------------------------------
    mt = {}
    det = [None] + [m.NewBoolVar(f'd{t}') for t in range(1, T + 1)]
    for t in range(1, T + 1):
        for i, u in enumerate(U):
            h = sum(c[0][t][u[0]]) + sum(c[1][t][u[1]]) + sum(c[2][t][u[2]])
            two, three = m.NewBoolVar(''), m.NewBoolVar('')
            m.Add(h == 2).OnlyEnforceIf(two)
            m.Add(h != 2).OnlyEnforceIf(two.Not())
            m.Add(h >= 3).OnlyEnforceIf(three)
            m.Add(h <= 2).OnlyEnforceIf(three.Not())
            mu = m.NewBoolVar(f'm{t}_{i}')
            if t == 1:
                m.Add(mu == two)
            else:
                prev = mt[t - 1, i]
                cl = [prev.Not()] + ([det[t - 1]] if i < nS else [])
                carried = m.NewBoolVar('')
                m.AddBoolAnd([prev] + ([det[t - 1].Not()] if i < nS else [])).OnlyEnforceIf(carried)
                m.AddBoolOr(cl).OnlyEnforceIf(carried.Not())
                m.AddBoolOr([two, carried]).OnlyEnforceIf(mu)
                m.AddImplication(mu, three.Not())
                m.AddImplication(two, mu)
                m.AddBoolOr([three, carried.Not(), mu])
            mt[t, i] = mu
        lits = [mt[t, i] for i in range(nS)] + [mt[t, i].Not() for i in range(nS, len(U))]
        m.AddBoolAnd(lits).OnlyEnforceIf(det[t])
        m.AddBoolOr([l.Not() for l in lits] + [det[t]])
    m.Add(sum(det[1:]) >= k)

    # ---- (C) knowledge from proven lower bounds ------------------------------------------------
    if known:
        F, W = closure(known.get('F'), known.get('W'), max(k, 1) + 1)
        D = det[1:]                     # D[t-1] = det at tick t
        if o['dettime']:
            # first detections: j-th detection at tick >= F_j (real start) or W_j (any W-start)
            first = F if real_start else W
            for j, L in first.items():
                if j >= 1 and L - 1 >= 1:
                    m.Add(sum(D[:min(L - 1, T)]) <= j - 1)
            # later: any L = W_i consecutive ticks contain at most i detections
            for i, L in W.items():
                if i >= 1 and 2 <= L <= T:
                    for s in range(0, T - L + 1):
                        m.Add(sum(D[s:s + L]) <= i)
        own = (F if real_start else W).get(k, 0)
        if own > T:
            m.AddBoolOr([])             # infeasible by the known bound itself
        elif own == T and o['noop']:
            # T is minimal: no tick may be deletable (a deletion would give a program of T-1 ticks).
            # act[e][t]: emitter e does something (move or toggle) in the transition into t.
            act = [[None] * (T + 1) for e in range(6)]
            for e in range(6):
                for t in range(1, T + 1):
                    act[e][t] = m.NewBoolVar('')
                    m.Add(act[e][t] == up[e][t] + dn[e][t] + tog[e][t])
            # tick 1 from the real start: all off, nothing fires -> an all-idle tick 1 is deletable
            if real_start:
                m.AddBoolOr([act[e][1] for e in range(6)])
            # same[t]: the lit beams of tick t equal those of tick t-1 (as multisets of lines)
            for t in range(2, T + 1):
                eqs = []
                for a in range(3):
                    for l in used[a]:
                        q_ = m.NewBoolVar('')
                        cur = z[a][t][l] + z[a + 3][t][l]
                        prv = z[a][t - 1][l] + z[a + 3][t - 1][l]
                        m.Add(cur == prv).OnlyEnforceIf(q_)
                        m.Add(cur != prv).OnlyEnforceIf(q_.Not())
                        eqs.append(q_)
                same = m.NewBoolVar('')
                m.AddBoolAnd(eqs).OnlyEnforceIf(same)
                m.AddBoolOr([x.Not() for x in eqs] + [same])
                # If same[t] and no detection at t-1, firing tick t changes nothing (idempotent) and
                # det[t] = 0.  Then tick t can be merged into a neighbour whenever every emitter is
                # idle in one of the two transitions involved:
                #   with t+1: config t-1 -> config t+1 in one step;  with t-1: config t-2 -> config t.
                # With a free start, tick 1 can always be dropped when same[2] (start in config 2).
                if free_start and start_cfg is None and t == 2:
                    m.AddBoolOr([det[1], same.Not()])
                    continue
                for (t1, t2) in ((t, t + 1), (t - 1, t)):
                    if t2 > T:
                        continue
                    both = []
                    for e in range(6):
                        b = m.NewBoolVar('')
                        m.AddBoolAnd([act[e][t1], act[e][t2]]).OnlyEnforceIf(b)
                        m.AddBoolOr([act[e][t1].Not(), act[e][t2].Not()]).OnlyEnforceIf(b.Not())
                        both.append(b)
                    m.AddBoolOr([det[t - 1], same.Not()] + both)

    V = dict(pos=pos, on=on, det=det, mt=mt, c=c, qv=qv, up=up, dn=dn, tog=tog, lit=lit, z=z)
    if extra:
        extra(m, V)
    if hint:
        for (e, t, q) in hint:
            m.AddHint(pos[e][t][q], 1)
    sol = cp_model.CpSolver()
    sol.parameters.max_time_in_seconds = secs
    sol.parameters.num_workers = workers
    for kk, vv in (params or {}).items():
        setattr(sol.parameters, kk, vv)
    st = sol.Solve(m)
    name = sol.StatusName(st)
    if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        states = []
        for t in range(0, T + 1):
            q = [next(j for j in range(nq) if sol.Value(pos[e][t][j])) for e in range(6)]
            ob = [bool(sol.Value(on[e][t])) for e in range(6)]
            states.append((q, ob))
        return 'FEASIBLE', states
    return name, None
