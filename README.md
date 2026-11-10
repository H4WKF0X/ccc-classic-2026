# ccc-classic-2026

Our repo for the **Cloudflight Coding Contest Classic 2026**. It solves all six levels.

The repo starts from the [ccc-rs](https://github.com/H4WKF0X/ccc-rs) template. The harness, the
checker and the Claude Code skills come from there. The contest statements are not in this repo.

## Result

At the end of the contest, the team was 5th in Vienna and 17th in the world.

Level 6 is scored: the score is the number of program lines, and lower is better. The work on
level 6 went on after the contest.

| | medium | large | enormous | total |
|---|---:|---:|---:|---:|
| contest end | 5,814 | 4,689 | 4,088 | 14,591 |
| now, `results/level6/best/` | 5,800 | 4,596 | 3,954 | 14,350 |
| proven optimal cases | 208/210 | 115/190 | 15/140 | |

[docs/LEVEL6.md](docs/LEVEL6.md) explains the level, the solver, the tools and how to run them.
[docs/level6-theory.md](docs/level6-theory.md) holds the optimality proofs and the lower bounds.

## Run

The setup is the same as in the ccc-rs template: Rust (stable, edition 2024), Node.js for the
checker, and Claude Code for the skills.

```bash
cargo ccc validate 3             # check level 3 against the worked example
cargo ccc all 3                  # solve all inputs of level 3 and check the outputs
cargo ccc all 6 --budget 600     # optimise level 6 for 10 minutes per file
```

The inputs are not in the repo. `cargo ccc ingest <zip>` reads a downloaded level into `work/`.

## Layout

| Path | Purpose |
|------|---------|
| `solution/src/levels/level<N>.rs` | One solver per level. Levels 1 to 5 are short, level 6 is the beam search and the optimiser. |
| `solution/src/model.rs` | The hex board model that the levels share. |
| `harness/` | The engine from the template: I/O, ingest, validation, CLI, platform client. |
| `checker/` | Judges levels with many valid answers with the game's own sandbox script. |
| `tools/level6/` | Python tools for level 6: exact proofs, lower bounds, window re-optimisation. |
| `tools/dashboard/` | A local live dashboard for the level 6 runs. |
| `results/level6/` | The best program per case, the bounds and the logs. |
| `docs/` | The level 6 notes, the theory, the contest day runbook and the platform API. |
| `CLAUDE.md`, `.claude/skills/` | Project memory and the skills: `/level`, `/optimize`, `/solve`, `/review`. |
| `work/` | Runtime only (git-ignored): inputs, outputs, statements. |
