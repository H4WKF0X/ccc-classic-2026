"""Level 6 in *line coordinates* -- the compact, exact reformulation used by bounds.py / exact.py.

Facts (all asserted at construction time by `LineGeo`, against the ring/ray geometry of cycles.Geo):

* Every ray of emitter e from ring position p is either empty or covers a *whole* board line of axis
  a = e % 3 (axis 0: rows, axis 1: the SE/NW diagonals, axis 2: the SW/NE diagonals).  A board of
  radius R has 2R-1 lines per axis, numbered 0..2R-2.
* The ring positions with a non-empty ray form a contiguous arc of 2R-1 positions; walking the arc
  visits the lines in order (one step = neighbouring parallel line).
* Emitter e starts (ring index e*R) on the arc, at the middle line R-1, switched off.  Emitters e and
  e+3 share the axis and both start on the same middle line, so they are interchangeable.

Hence an emitter's state is (q, on) with q in 0..2R: q = l+1 is "aims at line l", q = 0 / q = 2R are
the two "parked" positions just outside the arc (ray empty = effectively off).  Positions further
round the ring are never needed (an excursion round the back of the ring takes >= 4R+2 ticks, while
"toggle off, walk the arc dark, toggle on" takes 2R+2 and has the same effect).  Per tick an emitter
either keeps its state, toggles, or moves q by +-1.  A board cell u has line index u[a] on every axis
a; its hit count in a tick is  h(u) = sum over active emitters e of [line(e) == u[e % 3]].
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cycles import Geo, parse_in, parse_out, simulate, L6, DIRS  # noqa: F401  (re-exported)

KEYS = ['1-small', '2-medium', '3-large', '4-enormous']


def _line_key(axis, cell):
    y, x = cell
    return y if axis == 0 else (x - y if axis == 1 else x + y)


class LineGeo:
    """Pattern in line coordinates.  Attributes:
    R, nl (= lines per axis = 2R-1), nq (= arc positions incl. the two parked ones = 2R+1),
    S / K: lists of (x, y, z) line triples of pattern cells / halo cells,
    start_q: initial arc position of every emitter (= R, the middle line),
    arc[e]: ring index -> q for the 2R+1 ring positions used by emitter e,  geo: the cycles.Geo."""

    def __init__(self, r, grid):
        g = self.geo = Geo(r, grid)
        self.R = r
        self.nl = 2 * r - 1
        self.nq = 2 * r + 1
        idx = []
        for a in range(3):
            keys = sorted({_line_key(a, u) for u in g.cells})
            assert len(keys) == self.nl, (a, len(keys))
            idx.append({k: i for i, k in enumerate(keys)})
        self.coord = {u: tuple(idx[a][_line_key(a, u)] for a in range(3)) for u in g.cells}
        lines = [{} for _ in range(3)]
        for u, c in self.coord.items():
            for a in range(3):
                lines[a].setdefault(c[a], set()).add(u)
        # verify: rays are whole lines, non-empty rays form an arc visiting lines in order
        self.arc = []
        for e in range(6):
            a = e % 3
            ln = []
            for p in range(g.P):
                ray = set(g.ray[e][p])
                if not ray:
                    ln.append(None)
                    continue
                ks = {self.coord[u][a] for u in ray}
                assert len(ks) == 1 and ray == lines[a][next(iter(ks))], (e, p)
                ln.append(next(iter(ks)))
            on = [p for p in range(g.P) if ln[p] is not None]
            assert len(on) == self.nl
            # rotate so that the arc is contiguous
            first = next(p for p in on if ln[(p - 1) % g.P] is None)
            seq = [(first + i) % g.P for i in range(self.nl)]
            assert all(ln[p] is not None for p in seq)
            vals = [ln[p] for p in seq]
            assert vals == list(range(self.nl)) or vals == list(range(self.nl - 1, -1, -1)), vals
            m = {}
            for p in seq:
                m[p] = ln[p] + 1
            lo, hi = (first - 1) % g.P, (first + self.nl) % g.P   # parked neighbours
            if vals[0] == 0:
                m[lo], m[hi] = 0, self.nq - 1
            else:
                m[lo], m[hi] = self.nq - 1, 0
            self.arc.append(m)
            assert m.get(e * r) == r, (e, m.get(e * r))   # starts aiming at the middle line
        self.start_q = r
        self.S = sorted(self.coord[u] for u in g.S)
        self.K = sorted(self.coord[u] for u in g.K)

    def hits(self, lines_by_emitter, u):
        """Hit count of cell u (line triple) given each emitter's line (None = dark)."""
        return sum(1 for e, l in enumerate(lines_by_emitter) if l is not None and l == u[e % 3])


def load(key):
    """[(R, grid, count)] and best programs of one input file."""
    cases = parse_in(f'{L6}/in/in_level-6_{key}.txt')
    best = parse_out(f'{L6}/best/out_level-6_{key}.txt')
    return cases, best


def program_from_states(lg, states):
    """Turn a sequence of per-tick emitter states [(q[0..5], on[0..5])] (tick 1..T; tick 0 = start)
    into program lines.  F/B are chosen per emitter so that q follows the arc direction."""
    g = lg.geo
    inv = [{q: p for p, q in lg.arc[e].items()} for e in range(6)]
    prev_q = [lg.start_q] * 6
    prev_on = [False] * 6
    prog = []
    for q, on in states:
        line = []
        for e in range(6):
            if on[e] != prev_on[e]:
                assert q[e] == prev_q[e]
                line.append('T')
            elif q[e] == prev_q[e]:
                line.append('-')
            else:
                p0, p1 = inv[e][prev_q[e]], inv[e][q[e]]
                if (p0 + 1) % g.P == p1:
                    line.append('F')
                else:
                    assert (p0 - 1) % g.P == p1
                    line.append('B')
        prog.append(line)
        prev_q, prev_on = list(q), list(on)
    return prog
