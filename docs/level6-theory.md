# Level 6 "Nanofabricator": lower bounds and optimality proofs

_Post-contest research. The scripts are in `tools/level6/` and the numbers in `results/level6/`._

## Summary (numbers as of this write-up)

| | lines |
|---|---:|
| our contest-end total (medium + large + enormous) | 14,590 |
| `work/level6/best/` now (incl. the fast Rust solver and merged finds) | 14,544 |
| best incl. all programs found by this research | **14,526** |
| first place (approx.) | 14,290 |

* **Small: 10/10 proven optimal.** **Medium: 203/210 proven optimal**, and the
  other 7 cases can save **at most 69 lines** in total.
* **Large: 102/190 proven optimal**, provable gap 1067 lines. Almost half of it
  (479 lines) is in the 10 big R=6..8 patterns with gap ≥ 30, where the bounds are weak.
* **Enormous: not computed yet**: only trivial bounds. Overnight commands are in section 7.
* The exact solver also **found shorter programs**: −41 lines on medium + large, each counted
  against the best program that existed when the run started (section 4.6).
* **Verdict:** medium (≤ 69) cannot hold first place's ~240-line lead. The lead has to come
  from large and enormous big-pattern cases: better construction of 40 to 300-cell blobs, not
  better repetition. See section 6.

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
  All 220 small and medium cases pass. A model that rejected a real program would produce false
  "optimal" claims. `bounds.py` doesn't repeat this check, but it asserts `lb ≤ best` for every case.
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

## 4. Results

### 4.1 Totals

Gaps are measured against `work/level6/best/` as of this write-up (medium 5805, large 4666, enormous
4073, total 14,544). The coordinator merges new finds into it continuously. The column "best incl. this research" also counts shorter programs this research found
(section 4.6). Lower bounds are summed per case, and **every per-case bound is checked against a real
program** (`collect.py` asserts `lb ≤ best`; it has never fired).

| file | cases | best (work/level6/best) | best incl. this research | lower bound | gap | proven optimal |
|---|---:|---:|---:|---:|---:|---:|
| 1-small | 10 | 107 | 107 | 107 | 0 | 10 |
| 2-medium | 210 | 5805 | 5805 | 5736 | 69 | 203 |
| 3-large | 190 | 4666 | 4648 | 3581 | 1067 | 102 |
| 4-enormous | 140 | 4073 | 4073 | 225 | 3848 | 0 |
| **scored (2+3+4)** | 540 | 14544 | 14526 | 9542 | 4984 | 305 |
| scored without enormous | 400 | 10471 | 10453 | 9317 | 1136 | 305 |

**Enormous was deliberately not computed yet.** The bound shown there is only the trivial
`lb = count`, plus one trial case (case 0: lb 17, best 33). See section 7 for the overnight run.

### 4.2 Small (10 cases): all optimal

All 10 programs (107 lines) are **proven optimal**. Each `T = best-1` model is INFEASIBLE, in at most
1 s per case.

### 4.3 Medium (210 cases): 203 proven optimal, at most 69 lines left

* **Exact proofs:** 180 cases are INFEASIBLE at `T = best-1` (median 0.7 s, 90th percentile 10 s,
  max 134 s; 4 threads, 60 to 300 s cap). That proves those programs optimal for the *whole*
  program, not just per copy.
* **Decomposition:** the other 30 are the large R=5 patterns, where the whole-program proof times
  out. The decomposition bound `F_j + B(n-j)` closes another 19 of them exactly (`lb = best`).
  Example: case 26 has F1 = 7 and W1 = 5, so `OPT ≥ 7 + 9·5 = 52 = best`.
* **Closed by improvement:** in 4 more cases (80, 107, 130, 203) the bound was 1 below our program.
  There the later copies were provably optimal (`rest = B(n-1)`), but `F1` was one less than our
  first copy. `improve.py` then found a program 1 line shorter in each case, which meets the bound.
  Those cases are now optimal too.
* **Open:** 7 cases with a total gap of 69 lines:

  | case | count | cells | best | lb | gap | first copy: F1 / best | later copies: B(n-1) / best |
  |---:|---:|---:|---:|---:|---:|---|---|
  | 50 | 19 | 19 | 106 | 97 | 9 | 7 / 7 | 90 / 99 |
  | 58 | 5 | 22 | 31 | 27 | 4 | 7 / 7 | 20 / 24 |
  | 132 | 6 | 42 | 50 | 38 | 12 | 8 / 10 | 30 / 40 |
  | 161 | 7 | 59 | 51 | 44 | 7 | 8 / 9 | 36 / 42 |
  | 167 | 17 | 49 | 122 | 104 | 18 | 8 / 10 | 96 / 112 |
  | 186 | 4 | 32 | 27 | 23 | 4 | 8 / 8 | 15 / 19 |
  | 197 | 8 | 51 | 65 | 50 | 15 | 8 / 9 | 42 / 56 |

  All 7 (50, 58, 132, 161, 167, 186, 197) are big R=5 patterns
  (17 to 59 cells), where `W1` is proven but chained segments are not (`W2` stays undecided at
  60 s).

### 4.4 Large (190 cases): 102 proven optimal, the gap is concentrated in ~15 cases

All 190 cases have F1 / W1..W3 / F2..F3 bounds (40 s per solve, 200 s per case, then a second
"climbing" pass on the 43 cases with the biggest gaps: 150 s per solve, 300 s per case). After that,
`improve.py` (30 s per window, windows ≤ 20 lines) ran on the 79 open cases with gap ≤ 20. It
shortened 20 of them, by 26 lines in total, and 6 of those now meet their bound.

Gap histogram (gap bucket: cases, summed gap): {'0': (102, 0), '1-2': (18, 23), '10-29': (26, 392), '3-9': (34, 173), '30+': (10, 479)}.

Split of the large open cases' slack: first-copy slack (first_best - F1) = 317, later-copies slack (rest_best - B(n-1)) = 788.

### 4.5 The largest remaining gaps (medium + large)

| file | case | R | count | cells | best | lb | gap | F1 lb / first copy in best | later copies: bound / best |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 3-large | 143 | 8 | 6 | 131 | 135 | 48 | 87 | 1 / 25 | 40 / 110 |
| 3-large | 64 | 8 | 6 | 69 | 115 | 44 | 71 | 9 / 24 | 35 / 91 |
| 3-large | 141 | 8 | 6 | 91 | 111 | 45 | 66 | 10 / 21 | 35 / 90 |
| 3-large | 172 | 8 | 6 | 42 | 89 | 43 | 46 | 8 / 16 | 35 / 73 |
| 3-large | 184 | 8 | 4 | 52 | 72 | 32 | 40 | 11 / 20 | 21 / 52 |
| 3-large | 127 | 8 | 6 | 72 | 77 | 39 | 38 | 9 / 15 | 30 / 62 |
| 3-large | 103 | 8 | 5 | 44 | 69 | 34 | 35 | 10 / 16 | 24 / 53 |
| 3-large | 118 | 6 | 6 | 68 | 73 | 39 | 34 | 9 / 14 | 30 / 59 |
| 3-large | 146 | 8 | 2 | 131 | 48 | 16 | 32 | 1 / 26 | 8 / 22 |
| 3-large | 124 | 8 | 3 | 120 | 53 | 23 | 30 | 9 / 21 | 14 / 32 |
| 3-large | 148 | 7 | 3 | 54 | 50 | 21 | 29 | 1 / 18 | 14 / 32 |
| 3-large | 54 | 8 | 5 | 44 | 61 | 34 | 27 | 10 / 15 | 24 / 46 |
| 3-large | 76 | 6 | 4 | 65 | 50 | 27 | 23 | 9 / 14 | 18 / 36 |
| 3-large | 26 | 8 | 3 | 40 | 43 | 22 | 21 | 8 / 16 | 14 / 27 |
| 3-large | 44 | 7 | 2 | 73 | 35 | 16 | 19 | 9 / 19 | 7 / 16 |
| 2-medium | 167 | 5 | 17 | 49 | 122 | 104 | 18 | 8 / 10 | 96 / 112 |
| 3-large | 114 | 7 | 2 | 72 | 34 | 16 | 18 | 9 / 18 | 7 / 16 |
| 3-large | 91 | 7 | 3 | 46 | 38 | 21 | 17 | 9 / 14 | 12 / 24 |
| 3-large | 63 | 7 | 4 | 71 | 43 | 27 | 16 | 9 / 13 | 18 / 30 |
| 3-large | 168 | 6 | 5 | 44 | 49 | 33 | 16 | 9 / 13 | 24 / 36 |
| 2-medium | 197 | 5 | 8 | 51 | 65 | 50 | 15 | 8 / 9 | 42 / 56 |
| 3-large | 77 | 8 | 2 | 95 | 31 | 16 | 15 | 9 / 17 | 7 / 14 |
| 3-large | 60 | 8 | 5 | 60 | 47 | 33 | 14 | 9 / 11 | 24 / 36 |
| 3-large | 119 | 6 | 4 | 81 | 43 | 29 | 14 | 8 / 10 | 21 / 35 |
| 3-large | 21 | 8 | 2 | 76 | 30 | 17 | 13 | 10 / 16 | 7 / 14 |

Nearly all of these are R=8 (or R=6/7), count ≥ 2 patterns with 40 to 131 cells. For them the
model cannot even pin `W1`: proving "one copy takes ≥ 8 ticks from *any* start" already needs 2
minutes. For example, case 143 needs 22 lines per later copy in our program, against a proven 7.
These gaps measure **bound weakness at least as much as real room**. A 131-cell blob cannot be
built in 7 ticks, but this method cannot prove it within minutes.

### 4.6 Shorter programs found along the way

The solver returns a real program whenever `T = best-1` is feasible. `improve.py` re-solves the
windows between two detections exactly, with fixed start and end configurations. Every program
found replays correctly in `cycles.simulate`.

| file | case | contest end | best when our run started | found here | lower bound | by |
|---|---:|---:|---:|---:|---:|---|
| 2-medium | 50 | 109 | 109 | 106 | 97 | improve.py |
| 2-medium | 58 | 32 | 32 | 31 | 27 | improve.py |
| 2-medium | 80 | 74 | 74 | 73 | 73 | improve.py |
| 2-medium | 107 | 66 | 66 | 65 | 65 | improve.py |
| 2-medium | 130 | 77 | 77 | 76 | 76 | improve.py |
| 2-medium | 170 | 20 | 20 | 19 | 19 | exact/bounds |
| 2-medium | 203 | 66 | 66 | 65 | 65 | improve.py |
| 3-large | 4 | 26 | 26 | 25 | 25 | improve.py |
| 3-large | 6 | 34 | 34 | 33 | 28 | improve.py |
| 3-large | 12 | 15 | 15 | 14 | 13 | improve.py |
| 3-large | 13 | 6 | 6 | 5 | 5 | improve.py |
| 3-large | 17 | 25 | 25 | 24 | 23 | improve.py |
| 3-large | 22 | 39 | 39 | 38 | 28 | improve.py |
| 3-large | 31 | 53 | 52 | 51 | 38 | improve.py |
| 3-large | 36 | 21 | 21 | 19 | 19 | improve.py |
| 3-large | 40 | 23 | 23 | 22 | 22 | improve.py |
| 3-large | 46 | 29 | 29 | 27 | 23 | improve.py |
| 3-large | 74 | 46 | 46 | 45 | 39 | improve.py |
| 3-large | 80 | 33 | 33 | 32 | 21 | improve.py |
| 3-large | 86 | 51 | 51 | 50 | 38 | improve.py |
| 3-large | 96 | 11 | 11 | 10 | 9 | exact/bounds |
| 3-large | 100 | 26 | 26 | 22 | 20 | improve.py |
| 3-large | 104 | 45 | 45 | 43 | 33 | improve.py |
| 3-large | 105 | 36 | 35 | 34 | 28 | improve.py |
| 3-large | 113 | 10 | 10 | 9 | 8 | exact/bounds |
| 3-large | 119 | 45 | 45 | 43 | 29 | improve.py |
| 3-large | 122 | 33 | 33 | 32 | 27 | improve.py |
| 3-large | 131 | 9 | 9 | 8 | 8 | exact/bounds |
| 3-large | 132 | 18 | 18 | 17 | 17 | improve.py |
| 3-large | 144 | 29 | 29 | 28 | 27 | improve.py |
| 3-large | 169 | 26 | 26 | 25 | 25 | improve.py |
| 3-large | 178 | 14 | 14 | 13 | 13 | exact/bounds |
| **total saved by this research** | | | | **−41** | | |

They are in `results/level6/exact_programs/` and `results/level6/improved/`. The coordinator has
already merged the earlier ones into `work/level6/best/`.

## 5. Structural findings

* **Chaining never beats repetition (`W_k = k·W1`).** In 183 of 191
  decomposition rows, the best `k` consecutive copies from any start cost exactly `k` times the
  best single copy (k ≤ 3 or 4). So no clever multi-copy cycle beats repeating the best single
  copy. This matches the earlier CP-SAT cycle search, but here it is a *proof* for open walks, not
  just periodic cycles.
* **Per-copy minimum.** Medium `W1` ∈ {3..6}; large `W1` distribution: 1: 1, 2: 5, 3: 40, 4: 29, 5: 43, 6: 27, 7: 13, 8: 2 cases. Where the
  decomposition was computed (30 medium, 190 large cases), our later copies match the chained
  bound `B(n-1)` exactly in 22/30 medium and 114/190 large cases.
* **Where the lines go.** For the open cases, splitting the gap into "first copy" (first detection
  tick in best − F1) and "later copies" (rest − B(n−1)) gives medium: first-copy slack (first_best - F1) = 6, later-copies slack (rest_best - B(n-1)) = 63; large: first-copy slack (first_best - F1) = 317, later-copies slack (rest_best - B(n-1)) = 788. Most of the
  unexplained room is in the later copies of big patterns.
* **The first copy is cheap to pin.** `F1` equals our first copy in 25/30 medium and 118/190
  large decomposition rows. The start costs about `W1 + 1..3` (toggles and travel to the pattern).
  Exceptions are the biggest large patterns (143, 146, 148), where even `F1` stayed unproven
  (`F1 lb = 1`) because the budget ran out on `W1`.

## 6. Verdict: how much is left, and is ~14,290 reachable?

`work/level6/best/` is at 14,544, or 14,526 with every program this research found. First place
was about 14,290, so we are still **≈ 240 lines** behind.

* **Medium can give at most 69 lines** (a hard proof: 203/210 cases are optimal, and the
  7 open cases have bounded gaps). Realistically, it is fewer than that.
* **Small doesn't count** and is optimal anyway.
* So **at least ≈ 240 − 69 ≈ 170 lines must come from large + enormous** if first
  place's programs are valid. Large's provable gap is 1067 lines, which is room enough on
  paper. Almost all of it sits in the ~15 large R=8 cases with 40+ cells (top table), where our
  bounds are weak. Enormous has no bounds yet. Its 140 programs average 29 lines, and its huge
  patterns (100 to 300 cells, count ≤ 2) are exactly the kind where we can neither prove nor
  disprove much.
* **Conclusion:** the theory rules out finding the 240 lines in medium. Medium is essentially
  solved, and its open cases are worth ≤ 69 lines in total. The remaining room is in big
  patterns: large cases like 143, 64, 141, 172, 184, 127, 103, 118, 124 and 146, and most likely
  enormous. That is where first place must have been better: better building strategies for big
  blobs (more cells per tick, fewer halo repairs). Better repetition of small patterns is ruled out.

## 7. How to run (and the enormous overnight job)

All commands from `tools/level6/`, Python from `~/.ccc-venv`. Every script is resumable and appends
CSV rows to `results/level6/`. Re-running continues where it stopped, and `--redo` recomputes but
starts from the bounds proven earlier.

```bash
cd tools/level6
PY=~/.ccc-venv/bin/python
# whole-program optimality proofs (small: seconds; medium: ~1.5 h on 4 threads)
nice -n 10 $PY -u exact.py 1-small --secs 60 --workers 4
nice -n 10 $PY -u exact.py 2-medium --secs 60 --workers 4
# decomposition bounds (medium open cases, large)
nice -n 10 $PY -u bounds.py 3-large --cases 0,1,2 --secs 40 --budget 200 --fmax 3 --wmax 3 --workers 4
# second pass on hard cases: start from the old bounds, climb up from the lower bound
nice -n 10 $PY -u bounds.py 3-large --redo --climb --cases 143,64 --secs 150 --budget 300 --fmax 3 --wmax 3 --workers 4
# exact window re-optimisation of a known program (writes results/level6/improved/)
nice -n 10 $PY -u improve.py 2-medium --cases 50 --maxlen 25 --secs 30 --workers 4
# merge everything -> results/level6/bounds.csv, totals, markdown tables
$PY collect.py --md
```

**Enormous overnight (not run yet).** 140 cases with count 1 or 2, so only `F1`, `F2` and `W1`
matter (`--fmax 2 --wmax 1`). Three processes with 4 CP-SAT workers each use 12 threads, at
≤ 10 minutes per case. The trial on case 0 (R=9, 109 cells) took ~7 min and proved F1 ≥ 10,
W1 ≥ 7, lb 17 (best 33). Expect ≈ 140 × 10 min / 3 ≈ **8 hours**:

```bash
cd tools/level6
for j in 0 1 2; do
  cs=$(seq $j 3 139 | paste -sd,)
  nohup nice -n 10 ~/.ccc-venv/bin/python -u bounds.py 4-enormous --cases $cs \
      --secs 120 --budget 600 --fmax 2 --wmax 1 --workers 4 --climb \
      >> ../../results/level6/logs/decomp_4-enormous_$j.log 2>&1 &
done
# morning: python3 collect.py --md   (case 0 already has a row; add --redo --cases 0 to refresh it)
```

Use `--climb` for enormous. Bisection wastes the budget on middle probes that all time out, while
climbing proves the cheap low horizons first and keeps the best proven bound. Memory is about
0.5 to 1 GB per process at R=12.

## 8. Limitations

* The lower bounds come from **time-capped** CP-SAT runs. They are valid, but most bounds for big
  patterns are far from tight. A gap is "room we can't rule out", not "room that exists".
* `W_k` uses a *free* start configuration, which may not be reachable or efficient after a real
  previous copy. That is why the decomposition stays below the truth on chained problems.
* The model's correctness rests on the facts asserted in `lines.py` (checked on every case), on
  the soundness check (every best program is accepted by the model), and on every solution found
  replaying in the reference simulator. The reference simulator `cycles.simulate` matches the
  sandbox's `applyEmitterStep` / `detectAndAcceptPatterns` (detection once per tick, after firing;
  `h == 2` creates, `h ≥ 3` destroys, halo = `O` cells next to an `M`).
* Enormous: no bounds computed yet (section 7).

## 9. Files

* `tools/level6/lines.py`: line-coordinate geometry and its asserted facts; states → program.
* `tools/level6/satmodel.py`: the exact CP-SAT model (real or free start, fixed start config,
  twin symmetry breaking).
* `tools/level6/exact.py`: soundness check plus a whole-program proof at `best-1`
  (`results/level6/exact_<file>.csv`).
* `tools/level6/bounds.py`: `F_j` / `W_k` decomposition bounds (`results/level6/decomp_<file>.csv`).
* `tools/level6/improve.py`: exact window re-optimisation of known programs.
* `tools/level6/collect.py`: merges everything into `results/level6/bounds.csv` (columns: file,
  case, R, count, cells, halo, best, lb, best_new, gap, proven_optimal, method, F_lb, W_lb,
  first/rest split).
* `results/level6/logs/`: raw solver logs (every probe with its status and time).
