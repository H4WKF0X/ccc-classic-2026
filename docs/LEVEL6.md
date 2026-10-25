# Level 6 "Nanofabricator": what is in this repo

Start here. This page explains the level, where everything lives, and how to run it.
The deeper theory (optimality proofs, lower bounds) is in [`level6-theory.md`](level6-theory.md).
All six level statements are in [`statements/`](statements/).

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
| contest end (5th place) | 5,814 | 4,689 | 4,088 | 14,591 |
| now, `results/level6/best/` | **5,805** | **4,648** | **4,073** | **14,526** |
| provable lower bound | 5,736 | 3,581 | not computed yet | |
| first place (approx.) | | | | ~14,290 |

- 10/10 small and **203/210 medium cases are proven optimal**. Medium can improve by at most 69
  lines in total.
- 102/190 large cases are proven optimal. The remaining large gap (1,067 lines) is mostly *loose
  bounds* on big patterns, not necessarily real room.
- Enormous bounds still have to be computed (an ~8 h overnight job, see below).

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
| `view_case.py` | Writes one case + its program for the offline viewer (`work/level6/statement/sandbox-level-6.html`, paste into Input / Solution). |

Improvements found by `exact.py` / `improve.py` land in `results/level6/exact_programs/` and
`results/level6/improved/`. To merge them into the best: put full output files into
`work/level6/candidates/` (the name must contain `2-medium`, `3-large` or `4-enormous`) and run
`cargo ccc best 6`. It checks every program and keeps the shorter one per case.

## Overnight: enormous lower bounds

See section 7 of [`level6-theory.md`](level6-theory.md) for the exact commands (3 processes × 4
threads, ≈ 8 hours). Afterwards run `~/.ccc-venv/bin/python tools/level6/collect.py --md`.

## How we got here (short history)

1. **Contest (15:00–19:00):** started from a teammate's beam search (zip), then merged per case
   with three other teams' public outputs, our own runs (cycle search, splicing, beam5 seeded from
   the merged best). Finished 5th with 14,591.
2. **Day after:** cleaned up, rewrote the solver in Rust (6–10× faster), and built exact methods
   (CP-SAT on a line-coordinate model). These proved most medium cases optimal and found
   improvements in cases where every beam search, ours and the other teams', had stopped improving. Result: 14,526.

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
