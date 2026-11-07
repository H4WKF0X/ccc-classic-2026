# Level 6 "Nanofabricator": what is in this repo

Start here. This page explains the level, where everything lives, and how to run it.
The deeper theory (optimality proofs, lower bounds) is in [`level6-theory.md`](level6-theory.md).

## The level in one paragraph

A hexagonal board of radius R with a pattern of `M` cells. Six emitters sit on the border ring;
each tick every emitter does one of `-` (nothing), `T` (toggle on/off), `F`/`B` (move one step
along the ring), then every active emitter fires a beam across the board. A cell hit by exactly two
beams becomes matter, a cell hit by three or more loses it. When all pattern cells are matter and
no *halo* cell (empty cell next to the pattern) is, one copy is detected and the pattern is cleared.
Build the pattern `count` times. **Score = number of program lines; lower is better.** Only
medium + large + enormous count on the website.

## Results

| | medium | large | enormous | total |
|---|---:|---:|---:|---:|
| contest end (5th Vienna, 17th world) | 5,814 | 4,689 | 4,088 | 14,591 |
| now, `results/level6/best/` | **5,800** | **4,600** | **3,954** | **14,354** |
| proven lower bound | 5,787 | 3,590 | 1,792 | |
| proven optimal cases | 208/210 | 112/190 | 15/140 | |

Known leaderboard totals from the contest: Tschech 14,362 (1st world), Krautl 14,499 (1st Vienna,
5th world). Our 14,356 was uploaded to a training game of the same contest on 2026-10-25 (all six
levels correct); it is post-contest and unofficial.

- Medium can improve by at most 13 lines (open: 132, 197). 161 and 167 were closed by the depth-first chain search below.
- The large and enormous gaps are mostly *loose bounds* on big patterns, not necessarily real room.
- **What found the last 170 lines: beam width.** The plain beam keeps getting better with width on
  big patterns (from scratch, large: +342 lines above our best at width 800, +117 at 20,000, +60 at
  100,000). The optimiser used to stop at 12,000. See "What to run" below.

## Where things are

| Path | What |
|---|---|
| `solution/src/levels/level6.rs` | The solver inside the harness (Rust). Fast beam search + optimiser. |
| `tools/level6/` | Python tools: exact proofs, lower bounds, window re-optimisation, helpers. |
| `results/level6/best/` | The best program per case, one file per input. |
| `results/level6/pool.tar.xz` | Every distinct program we collected during the contest (ours + 3 other teams' repos + downloads). |
| `results/level6/*.csv` | Bounds and proofs per case (`bounds.csv` is the summary). |
| `docs/level6-theory.md` | The theory: line coordinates, the exact model, decomposition bounds, numbers. |
| `work/level6/` | Working area (git-ignored): inputs, current `best/`, `pool/`, third-party code, archive. |

## The Rust solver (`level6.rs`)

Modules, top to bottom:

- **`geo`**: which cells matter (pattern + halo, ≤ 358 cells, so ≤ 6 × 64-bit words), and the beam
  bitset of every emitter at every ring position.
- **`sim`**: exact bitset simulator (checked against `model.rs` on every best program).
- **`sym`**: the 12 rotations/mirrors of the board, and mapping programs onto and back from them.
- **`beam`**: one beam search: per tick, expand every kept state by all 4⁶ = 4096 instruction
  lines, score them, keep the best W ("beam width"). Grouped, pruned and allocation-free, it is 6–10×
  faster than the best C beam search we had during the contest (`beam5.c`).
- **`seeds`**: loads known programs (default `work/level6/best/`) as starting points.
- **`opt`**: the optimiser: restart from a random prefix of the best program, on a random symmetric
  board, with the bound "best − 1"; widen the beam over time; keep only verified improvements.

```bash
cargo ccc validate 6                 # example must say GO
cargo ccc all 6 --budget 600         # optimise 10 min per file, seeded from work/level6/best/
CCC_THREADS=8 nice -n 10 cargo ccc all 6 --budget 600   # same, limited to 8 threads
L6_SEED_DIR="" cargo ccc all 6 --budget 180   # from scratch, no seeds
L6_WIDTHS=100000 cargo ccc all 6 --budget 3600  # much wider beams (default schedule 800 ... 12,000)
L6_ALT="hp=40" L6_ALT_PCT=33 ...               # a share of restarts with other beam knobs
```

The harness keeps the best program per case in `work/level6/best/` across runs, so experiments can
never make the result worse.

## The Python tools (`tools/level6/`)

Run with `~/.ccc-venv/bin/python` (has OR-Tools / CP-SAT and HiGHS).

| Script | What it does |
|---|---|
| `lines.py` | Line-coordinate model of the board (asserts its facts on every case). |
| `satmodel.py` | Exact CP-SAT model: "is there a program of T lines with `count` copies?" |
| `satmodel2.py` | Stronger drop-in version of `satmodel.py`: valid cuts, dominance/symmetry breaking, proven bounds as knowledge (theory section 10). |
| `test_satmodel2.py`, `diff_satmodel2.py` | Soundness tests (pool + random trajectories) and the differential test against `satmodel.py`. |
| `close_medium2.py`, `stitch.py`, `medium_bounds2.py` | Decisive W/F solves with `satmodel2`, stitching full programs from them, recomputed medium bounds. |
| `exact.py` | Whole-program optimality proofs (solve at T = best−1; INFEASIBLE = optimal). |
| `bounds.py` | Lower bounds by splitting a program at its copies (first copy + later copies). |
| `improve.py` | Exact window re-optimisation: re-solve the stretch between two copies, keep it if shorter. |
| `collect.py` | Merges all results into `results/level6/bounds.csv` and the markdown tables. |
| `cycles.py`, `multi_cycles.py` | Repeating-cycle search (from the contest). |
| `splice.py` | Recombine copy-to-copy stretches across many programs. |
| `bounds2.py` | Lower-bound climbing with `satmodel2` for any file (W_k, F_j from the proven value upwards). |
| `attack.py` | Exact search for a whole program with best−1 lines (or a proof that the best is optimal). |
| `inner.py`, `cyc.py` | Inner-copy windows and exact repeating cycles (both tried, no wins at scale). |
| `measure.py`, `watch_wins.py` | Compare plain beam runs (the `measure` test) with the best; follow a run and save wins. |
| `merge_improved.py` | Merge `results/level6/improved/*` into `work/level6/best/` (re-checked by `cargo ccc best 6`). |
| `view_case.py` | Writes one case + its program for the offline viewer (`work/level6/statement/sandbox-level-6.html`, paste into Input / Solution). |

Improvements found by `exact.py` / `improve.py` land in `results/level6/exact_programs/` and
`results/level6/improved/`. To merge them into the best: put full output files into
`work/level6/candidates/` (the name must contain `2-medium`, `3-large` or `4-enormous`) and run
`cargo ccc best 6`. It checks every program and keeps the shorter one per case.

## What to run (what works, what does not)

**Works: very wide beams.** Seeded optimiser at width 100,000 on the open cases of one file
(about 360 MB RAM per process; `--no-windows` = Rust only):

```bash
L6_WIDTHS=100000 nice -n 10 ~/.ccc-venv/bin/python -u tools/level6/overnight_large.py \
    --key 4-enormous --hours 6 --round-min 60 --rust-threads 7 --no-windows
```

Plain from-scratch sweeps at a given width (writes one line per finished case; `watch_wins.py` saves
every program shorter than the best):

```bash
cd solution && L6_MEAS_CASES=$PWD/../work/level6/measure/big_open.txt L6_MEAS_W=500000 \
    L6_MEAS_OUT=$PWD/../work/level6/measure/w500k_out.txt L6_MEAS_THREADS=7 \
    cargo test --release level6::tests::measure -- --ignored
~/.ccc-venv/bin/python -u tools/level6/watch_wins.py work/level6/measure/w500k_out.txt
~/.ccc-venv/bin/python tools/level6/merge_improved.py        # then copy best/ to results/ and commit
```

On 2026-10-25: one width-100,000 sweep over all large+enormous cases found 20 shorter programs
(−21 lines); four seeded width-100,000 rounds gave −34, −10, −4, −2; 30 minutes of width 500,000
on the 21 biggest open patterns gave −4. 93 big open patterns were never tried at 500,000.

**Does not pay any more** (all measured on 2026-10-25, details in the git log):

- exact windows between copies (`improve.py`): only short windows decide; capped at 18 lines;
- inner-copy windows (`inner.py`): 176 spans of 4–18 ticks, 0 wins: the programs are locally optimal;
- best−1 whole-program attack (`attack.py`): proves short programs optimal, 0 shorter programs;
- exact cycles (`cyc.py`): undecided at the copy lengths where there is room;
- halo matter in the beam (`L6_ALT="hp=40"`): 0 wins in two rounds;
- the beam at width ≤ 12,000 (the old optimiser): stalled.

**Medium 161 (best 51, bound 50), tight-chain search (`tight.py`, 2026-10-26).** A 50-line program
must have its first copy at exactly tick 8 and then a copy every 7 ticks (F1 = 8 and W1 = 7 are
proven), so `tight.py` enumerates, layer by layer, every emitter configuration such a chain can be
in after each copy (twin-swapped configurations merged; 14 processes). Layer 1: 137 configurations
(33 min, 3 of 27 enumerations hit the 30-minute limit); layer 2: 161 configurations (2 h, 14 of 137
hit the limit). Stopped there: the layers do not shrink, so a 50-line chain may well exist, but each
layer costs about 2 hours and a proof would also need the timed-out enumerations redone.
**Solved the same day with `dfs.py`:** a depth-first search for *one* chain (14 workers, random seeds, shared proven dead ends) found a 50-line program after 7 solves in 2.5 minutes: 161 is 50 lines and optimal (lb 50). Medium 167 the same way: 121 = 9 + 16 x 7 lines, found after about 50 minutes, optimal. The idea, a depth-first search for *one* chain (one quick solve per copy,
backtrack on dead ends, 14 independent random searches) instead of enumerating every configuration.
It can only find a 50-line program, not prove 51 optimal; the layered search remains the way to a proof.

Lower bounds: `bounds2.py` climbs W_k / F_j with `satmodel2` (cheap enormous pass: `--secs 45
--case-budget 90`, about 1.5 hours). Results land in `results/level6/bounds2_<key>.csv`, which the
optimiser and the dashboard read.

## How we got here (short history)

1. **Contest (15:00–19:00):** started from a teammate's beam search (zip), then merged per case
   with three other teams' public outputs, our own runs (cycle search, splicing, beam5 seeded from
   the merged best). Finished 5th with 14,591.
2. **Day after:** cleaned up, rewrote the solver in Rust (6–10× faster), and built exact methods
   (CP-SAT on a line-coordinate model). These proved most medium cases optimal and found
   improvements in cases where every beam search, ours and the other teams', had stopped improving. Result: 14,526.
3. **Day 3 (2026-10-25):** enormous optimiser rounds and exact windows (14,445), a stronger exact
   model (satmodel2: medium 58 and 186 optimal, 206/210 medium proven), first real enormous bounds,
   a live dashboard, and many exact ideas that found nothing (above). Then a measurement of the plain
   beam against all known optima showed that width had not saturated: widths 100,000–500,000 took
   the total from 14,431 to **14,356**, below the contest's first place. Uploaded to a training
   game: all levels correct, 14,356.

## Live dashboard

```bash
python3 tools/dashboard/serve.py        # then open http://127.0.0.1:8765 (local only, standard library)
```

One page with: the score and how it changed since the contest end, the known leaderboard totals,
proven-optimal cases and the gap to the lower bounds per file, every running job (CPU, RAM, progress
from its log), the machine (cores, temperature, RAM, fans, battery), the Claude Code agents, a
"needs attention" list (errors in logs, unmerged wins, uncommitted best, unanswered notes) and a
per-case map + table. Leaderboard numbers and the contest-end score are in `tools/dashboard/config.json`.

**Agents and scripts report to it** with `tools/dashboard/post.py` (appends to `work/dashboard/events.jsonl`):

```bash
python3 tools/dashboard/post.py --agent <name> --kind win "large case 96: 23 -> 22"   # kinds: info win question done error plan
python3 tools/dashboard/post.py --notes                                              # unanswered notes from the human
python3 tools/dashboard/post.py --agent <name> --ack <note id> "answer"              # answer a note
```

Post a `win` for every shorter program or new proof, `plan` when starting a long run, `done` at the
end, `question` when the human has to decide. Check `--notes` now and then.
