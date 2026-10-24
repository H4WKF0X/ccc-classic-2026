"""Exact CP-SAT time-expanded model of Level 6 in line coordinates (see lines.py).

`solve(lg, T, k, free_start)` decides: is there a program of T ticks that produces >= k copies,
starting either
  * from the real start (free_start=False: every emitter at the middle line, off), or
  * from ANY emitter configuration (free_start=True) with pattern + halo empty  -- this is the state
    right after any detection, so it bounds every later stretch of a program.

The model is exact (not a relaxation): hit counts h = number of active emitters aiming at a line through
the cell; h == 2 creates matter, h >= 3 destroys it; matter persists; detection is *forced* exactly
when all pattern cells are matter and no halo cell is (it then clears the pattern cells).  Other cells
are don't-care and are left out.  Feasibility is monotone in T (append no-op lines), so
INFEASIBLE at T proves "every program needs >= T+1 lines" for that question.
"""
from ortools.sat.python import cp_model


def solve(lg, T, k, free_start=False, secs=60.0, workers=1, hint=None, extra=None, symbreak=True,
          start_cfg=None):
    """Returns (status_name, states) where states = [(q[6], on[6]) for t in 0..T] when feasible.
    `extra(m, V)` may add constraints (V = dict of variables) -- used for decompositions.
    start_cfg = (q[6], on[6]) fixes the configuration at t=0 (pattern + halo empty), e.g. the
    configuration of a known program right after one of its detections."""
    if start_cfg is not None:
        free_start, symbreak = True, False      # fixed but arbitrary start: twins no longer symmetric
    m = cp_model.CpModel()
    nq = lg.nq
    U = lg.S + lg.K
    nS = len(lg.S)
    used = [sorted({u[a] for u in U}) for a in range(3)]          # lines that touch pattern/halo
    pos = [[[m.NewBoolVar(f'p{e}_{t}_{q}') for q in range(nq)] for t in range(T + 1)] for e in range(6)]
    on = [[m.NewBoolVar(f'o{e}_{t}') for t in range(T + 1)] for e in range(6)]
    for e in range(6):
        for t in range(T + 1):
            m.AddExactlyOne(pos[e][t])
        if start_cfg is not None:
            m.Add(pos[e][0][start_cfg[0][e]] == 1)
            m.Add(on[e][0] == int(start_cfg[1][e]))
        elif not free_start:
            m.Add(pos[e][0][lg.start_q] == 1)
            m.Add(on[e][0] == 0)
        for t in range(1, T + 1):
            P0, P1 = pos[e][t - 1], pos[e][t]
            tog = m.NewBoolVar('')
            # tog <-> on[t] != on[t-1]
            m.Add(on[e][t] != on[e][t - 1]).OnlyEnforceIf(tog)
            m.Add(on[e][t] == on[e][t - 1]).OnlyEnforceIf(tog.Not())
            for q in range(nq):
                m.AddBoolOr([P0[j] for j in (q - 1, q, q + 1) if 0 <= j < nq]).OnlyEnforceIf(P1[q])
                m.Add(P1[q] == P0[q]).OnlyEnforceIf(tog)
    if symbreak:
        # Emitters e and e+3 are interchangeable (same axis, same line numbering, same start), so
        # swapping their whole trajectories maps solutions to solutions: keep only the solutions
        # where the trajectory of e is lexicographically <= that of e+3 (value 2q+on per tick).
        for a in range(3):
            eq = None
            for t in range(0 if free_start else 1, T + 1):
                va = sum(2 * q * pos[a][t][q] for q in range(nq)) + on[a][t]
                vb = sum(2 * q * pos[a + 3][t][q] for q in range(nq)) + on[a + 3][t]
                same = m.NewBoolVar('')
                m.Add(va == vb).OnlyEnforceIf(same)
                m.Add(va != vb).OnlyEnforceIf(same.Not())
                if eq is None:
                    m.Add(va <= vb)
                    eq = same
                else:
                    m.Add(va <= vb).OnlyEnforceIf(eq)
                    nxt = m.NewBoolVar('')
                    m.AddBoolAnd([eq, same]).OnlyEnforceIf(nxt)
                    m.AddBoolOr([eq.Not(), same.Not()]).OnlyEnforceIf(nxt.Not())
                    eq = nxt
    # c[a][t][l] = number of active emitters of axis a aiming at line l
    c = [[{} for t in range(T + 1)] for a in range(3)]
    for t in range(1, T + 1):
        for a in range(3):
            for l in used[a]:
                zs = []
                for e in (a, a + 3):
                    z = m.NewBoolVar('')
                    p = pos[e][t][l + 1]
                    m.AddImplication(z, p)
                    m.AddImplication(z, on[e][t])
                    m.AddBoolOr([p.Not(), on[e][t].Not(), z])
                    zs.append(z)
                c[a][t][l] = zs
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
                # carried = prev and (not cleared by a detection at t-1, pattern cells only)
                cl = [prev.Not()] + ([det[t - 1]] if i < nS else [])
                carried = m.NewBoolVar('')
                m.AddBoolAnd([prev] + ([det[t - 1].Not()] if i < nS else [])).OnlyEnforceIf(carried)
                m.AddBoolOr(cl).OnlyEnforceIf(carried.Not())
                # mu = two or (carried and not three)
                m.AddBoolOr([two, carried]).OnlyEnforceIf(mu)
                m.AddImplication(mu, three.Not())
                m.AddImplication(two, mu)
                m.AddBoolOr([three, carried.Not(), mu])
            mt[t, i] = mu
        # forced detection
        lits = [mt[t, i] for i in range(nS)] + [mt[t, i].Not() for i in range(nS, len(U))]
        m.AddBoolAnd(lits).OnlyEnforceIf(det[t])
        m.AddBoolOr([l.Not() for l in lits] + [det[t]])
    m.Add(sum(det[1:]) >= k)
    V = dict(pos=pos, on=on, det=det, mt=mt, c=c)
    if extra:
        extra(m, V)
    if hint:
        for (e, t, q) in hint:
            m.AddHint(pos[e][t][q], 1)
    sol = cp_model.CpSolver()
    sol.parameters.max_time_in_seconds = secs
    sol.parameters.num_workers = workers
    st = sol.Solve(m)
    name = sol.StatusName(st)
    if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        states = []
        for t in range(0, T + 1):
            q = [next(j for j in range(nq) if sol.Value(pos[e][t][j])) for e in range(6)]
            o = [bool(sol.Value(on[e][t])) for e in range(6)]
            states.append((q, o))
        return 'FEASIBLE', states
    return name, None
