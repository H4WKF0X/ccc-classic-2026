# Level 6 "Nanofabricator": lower bounds and optimality proofs

_Post-contest research. The scripts are in `tools/level6/` and the numbers in `results/level6/`._

RESULTS_SUMMARY

## 1. An exact, compact reformulation: line coordinates

`tools/level6/lines.py` asserts each of the following facts for every case of every input file:

1. **A ray is a whole line or nothing.** The ring cells (`*`) lie outside the hexagon, and the
   hexagon is convex. So the ray of emitter `e` from ring position `p` covers either every board
   cell of one line of axis `a = e mod 3` or no cell at all. Axis 0 is the rows, axis 1 the ↘/↖
   diagonals and axis 2 the ↙/↗ diagonals. A radius-R board has `2R-1` lines per axis.
2. **Each emitter walks an arc.** The ring positions where emitter `e` hits something form a
   contiguous arc of `2R-1` positions, and walking the arc visits the lines in order. One F/B step
   moves the beam to the neighbouring parallel line.
3. **Start.** Emitter `e` starts at ring index `e*R`. That position is on its arc and aims at the
   middle line `R-1`, so emitters `e` and `e+3` start off and on the *same* middle line. They are
   interchangeable.

So an emitter's state is `(q, on)` with `q ∈ {0..2R}`: `q = l+1` aims at line `l`, and `q = 0` or
`q = 2R` is "parked" just past an end of the arc, where the ray is empty. Each tick an emitter
keeps its state, toggles, or moves `q` by ±1. Positions further round the ring are never needed. A
detour round the back of the ring from one parked end to the other takes `4R` ticks, while
"toggle off, walk the arc dark, toggle on" takes at most `2R+2 ≤ 4R` ticks and fires exactly the
same (empty) beams. Any program can therefore be rewritten without such detours, at the same length.
Some best programs do take that detour; it is harmless but never needed.

A cell `u` has a line index `u_a` on each axis. In one tick its hit count is

    h(u) = #{active emitters e aiming at line u_{e mod 3}}  ∈ {0..6},

with matter created if `h = 2` and destroyed if `h ≥ 3`. Per tick, the only ways to create a cell
are a **co-linear pair** (both emitters of one axis on its line: a whole line, h=2 everywhere unless
a third beam crosses) or a **crossing** of two beams of different axes. The state space per emitter
has only `2(2R+1)` values (22 for R=5, 50 for R=12). That is what makes exact search feasible.

## 2. The exact CP-SAT model (`satmodel.py`)

Time-expanded over `T` ticks, with variables per emitter and tick: a one-hot over `q`, an `on` flag,
and a toggle flag (a toggle forbids a move in the same tick). Per pattern or halo cell and tick:
`two ⇔ h = 2`, `three ⇔ h ≥ 3`, and matter `m_t = two ∨ (carried ∧ ¬three)`. Here `carried` is
`m_{t-1}` unless a detection at `t-1` cleared that pattern cell. **Detection is forced:**
`det_t ⇔ (all pattern cells matter) ∧ (no halo cell matter)`. Don't-care cells are left out
because they never influence anything. The question is whether `Σ det_t ≥ k`.

* The model is **exact**, not a relaxation. Its solutions are converted back to F/B/T programs
  (`program_from_states`) and replayed in the reference simulator `cycles.simulate`. Every solution
  found so far replays to exactly `T` lines.
* **Soundness check** (`exact.py`, column `sound`): every best program, projected to line
  coordinates, is accepted by the model. Programs that use the back-of-ring detour can't be
  projected tick by tick; for those the model is solved at `T = best` and must be feasible.
  Every case passes. A model that rejected a real program would produce false "optimal" claims.
* **Monotone in T:** padding with no-op lines keeps all detections. INFEASIBLE at `T` therefore proves
  that *every* program needs at least `T+1` lines. A single solve at `T = best-1` proves a best
  program optimal.

## 3. Decomposition bounds (`bounds.py`)

The state right after a detection is only the emitter configuration: the pattern was just cleared,
the halo is empty (that is the detection condition), and the other cells don't matter. Define

* `F_j` = minimum lines for `j` copies from the real start;
* `W_k` = minimum lines for `k` copies from **any** emitter configuration, with pattern and halo empty.

Cut an optimal program after its `j`-th detection. The rest is a W-type program, so

    OPT ≥ F_j + B(n-j),   B(m) = max_{k≤m} (W_k + B(m-k)),  B(0) = 0,

where `n` is the required count and `B` chains the W-bounds by superadditivity. Each `F_j` or `W_k` is
bracketed by solving the same exact model at chosen horizons (a lower bound is the largest T proven
infeasible + 1). If a solve hits its time cap, the proven part is kept, so every number in the tables
is a valid bound even when the search was cut short.

DECOMP_AND_RESULTS
