//! Level 6 "Nanofabricator": the shortest emitter program that prints a pattern `count` times.
//!
//! # Rules (exact semantics live in `model.rs`, verified against the website)
//!
//! A hex board of radius `R` has a ring of `6R` border positions. Emitter `k` (0..6) starts at
//! ring index `k*R`, switched off, and always fires in its own direction (→ ↘ ↙ ← ↖ ↗). A program
//! is a list of lines, one instruction per emitter: `-` nothing, `T` toggle, `F`/`B` one step
//! clockwise / counter-clockwise. Each line is one tick: apply the instructions, then every active
//! emitter fires; a cell hit by exactly two beams becomes matter, by three or more loses it. After
//! the tick, if every pattern cell is matter and no *halo* cell (a non-pattern cell next to the
//! pattern) is, a copy is detected and the pattern cells are cleared. The cost is the number of
//! lines until `count` copies were detected.
//!
//! Only pattern ∪ halo cells ever matter (at most a few hundred), so the whole board state is a
//! small bitset plus the six emitters ([`sim::State`]).
//!
//! # Structure
//!
//! - [`geo`]: relevant cells as bit indices, beam masks per emitter and ring position.
//! - [`sim`]: the exact bitset simulator (tested against `model.rs`).
//! - [`sym`]: the 12 board symmetries and how programs map between symmetric boards.
//! - [`beam`]: one beam-search attempt, the hot loop.
//! - [`seeds`]: loading known programs (by default `work/level6/best/`) as incumbents.
//! - [`opt`]: the optimiser: runs attempts over all cases on a bounded number of threads and
//!   keeps the shortest valid program per case.
//!
//! Environment: `L6_SEED_DIR` (seed outputs, empty = none), `L6_SEED` (random seed, default 0),
//! `L6_ROUNDS` (improvement attempts per case; default unlimited with `--budget`, else none).
//! Threads: `CCC_THREADS`, shared by all input files of one `cargo ccc all` run.
//!
//! Credits: the search follows team leddis088's `beam5.c` and its driver `cloud_beam.py`
//! (`work/level6/third_party/leddis088/`): the scoring (copies, painted cells, emitter distance,
//! halo junk), the per-parent child cap, the tail rerank, and restarting from a prefix of the
//! incumbent on a random symmetric copy of the board. This is an independent Rust rewrite; the
//! expansion groups emitter options by their beam so each beam combination is evaluated once.

use crate::model::{Pattern, count_accepted, parse_instr};

struct Case {
    pattern: Pattern,
    count: usize,
}

fn parse(input: &str) -> Vec<Case> {
    let mut lines = input.lines().filter(|l| !l.trim().is_empty());
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    (0..n)
        .map(|_| {
            let h = harness::parse::ints(lines.next().unwrap());
            let (r, rows, count) = (h[0] as usize, h[1] as usize, h[3] as usize);
            let grid = (0..rows).map(|_| lines.next().unwrap().trim().as_bytes().to_vec()).collect();
            Case { pattern: Pattern::new(crate::model::Board { r, grid }), count }
        })
        .collect()
}

/// Splits the output into one program per case (programs separated by blank lines).
fn split_programs(output: &[String]) -> Vec<Vec<&str>> {
    let mut progs = vec![Vec::new()];
    for l in output {
        if l.trim().is_empty() {
            if !progs.last().unwrap().is_empty() {
                progs.push(Vec::new());
            }
        } else {
            progs.last_mut().unwrap().push(l.as_str());
        }
    }
    if progs.last().unwrap().is_empty() {
        progs.pop();
    }
    progs
}

fn parse_program(lines: &[&str]) -> Result<Vec<[u8; 6]>, String> {
    lines
        .iter()
        .map(|l| {
            let toks: Vec<&str> = l.split_whitespace().collect();
            if toks.len() != 6 || toks.iter().any(|t| !matches!(*t, "F" | "B" | "T" | "-")) {
                return Err(format!("bad instruction line {l:?}"));
            }
            Ok(parse_instr(l))
        })
        .collect()
}

pub fn check(input: &str, output: &[String]) -> Result<(), String> {
    score(input, output).map(|_| ())
}

/// Cost per case: number of instruction lines.
pub fn score(input: &str, output: &[String]) -> Result<Vec<i64>, String> {
    let cases = parse(input);
    let progs = split_programs(output);
    if progs.len() != cases.len() {
        return Err(format!("expected {} programs, got {}", cases.len(), progs.len()));
    }
    let mut costs = Vec::new();
    for (i, (c, p)) in cases.iter().zip(&progs).enumerate() {
        let prog = parse_program(p).map_err(|e| format!("case {i}: {e}"))?;
        let got = count_accepted(&c.pattern, &prog);
        if got < c.count {
            return Err(format!("case {i}: accepted {got} of {} patterns", c.count));
        }
        costs.push(prog.len() as i64);
    }
    Ok(costs)
}

pub fn solve(input: &str) -> Vec<String> {
    let cases = parse(input);
    let progs = opt::optimize(&cases);
    let mut out = Vec::new();
    for (case, prog) in cases.iter().zip(&progs) {
        let lines: Vec<[u8; 6]> = prog.iter().map(|&a| unpack(a)).collect();
        assert!(count_accepted(&case.pattern, &lines) >= case.count, "solver produced an invalid program");
        out.extend(lines.iter().map(|l| l.iter().map(|&c| (c as char).to_string()).collect::<Vec<_>>().join(" ")));
        out.push(String::new());
    }
    out
}

/// One instruction line packed into 12 bits: 2 bits per emitter, emitter `k` at bits `2k..2k+2`.
type Action = u16;
/// Instruction codes inside an [`Action`].
const NOP: u16 = 0;
const FWD: u16 = 1;
const BWD: u16 = 2;
const TOGGLE: u16 = 3;
const SYMBOLS: [u8; 4] = *b"-FBT";

/// Instruction code of emitter `k` in `a`.
fn op(a: Action, k: usize) -> u16 {
    (a >> (2 * k)) & 3
}

fn pack(line: &[u8; 6]) -> Action {
    (0..6).fold(0, |a, k| a | (SYMBOLS.iter().position(|&s| s == line[k]).unwrap() as u16) << (2 * k))
}

fn unpack(a: Action) -> [u8; 6] {
    std::array::from_fn(|k| SYMBOLS[op(a, k) as usize])
}

/// Board geometry restricted to the cells that matter.
mod geo {
    use crate::model::{Pattern, Rig};
    use std::collections::BTreeMap;

    /// Bitset words. 8 words = 512 relevant cells; the inputs need at most 6.
    pub const MAXW: usize = 8;
    pub type Bits = [u64; MAXW];
    /// Beam id of a beam that hits no relevant cell (the same as no beam at all).
    pub const EMPTY: u16 = u16::MAX;

    /// Relevant cells are numbered pattern cells first (`0..npat`), then halo cells.
    pub struct Geo {
        pub r: usize,
        /// Ring length `6r`.
        pub ring: usize,
        /// Bitset words in use.
        pub nw: usize,
        pub npat: usize,
        pub pat: Bits,
        pub halo: Bits,
        /// `beam[k * ring + p]`: relevant cells hit by emitter `k` from ring position `p`.
        pub beam: Vec<Bits>,
        /// Equal ids for equal beam masks of the same emitter ([`EMPTY`] if it hits nothing).
        pub beam_id: Vec<u16>,
        /// `line[j * 6 + k]`: window offset (see [`Geo::window_start`]) at which emitter `k`'s
        /// beam crosses pattern cell `j`.
        pub line: Vec<u8>,
        /// `lc[k * ring + p]`: emitter `k`'s position `p` in common line coordinates of the pair
        /// `k mod 3`, `k mod 3 + 3`: they fire along the same lines, in opposite order of their
        /// window offsets (tested), so swapping their (line, on) states changes nothing. Positions
        /// outside the window get unique values.
        pub lc: Vec<u16>,
    }

    impl Geo {
        pub fn new(pattern: &Pattern) -> Geo {
            let r = pattern.board.r;
            let rig = Rig::new(r);
            let ring = rig.ring.len();
            let index: BTreeMap<(usize, usize), usize> =
                pattern.cells.iter().chain(&pattern.skirting).enumerate().map(|(i, &c)| (c, i)).collect();
            let nrel = index.len();
            assert!(nrel <= MAXW * 64, "{nrel} relevant cells do not fit the bitsets");
            let npat = pattern.cells.len();
            let mut pat = [0; MAXW];
            let mut halo = [0; MAXW];
            for i in 0..nrel {
                let m = if i < npat { &mut pat } else { &mut halo };
                m[i / 64] |= 1 << (i % 64);
            }
            let mut beam = vec![[0u64; MAXW]; 6 * ring];
            for k in 0..6 {
                for (p, &(y, x)) in rig.ring.iter().enumerate() {
                    for cell in pattern.board.beam_cells(y, x, k as u8 + 1) {
                        if let Some(&i) = index.get(&cell) {
                            beam[k * ring + p][i / 64] |= 1 << (i % 64);
                        }
                    }
                }
            }
            let beam_id = (0..6 * ring)
                .map(|kp| {
                    let (k, p) = (kp / ring, kp % ring);
                    if beam[kp] == [0; MAXW] {
                        EMPTY
                    } else {
                        (0..=p).find(|&q| beam[k * ring + q] == beam[kp]).unwrap() as u16
                    }
                })
                .collect();
            let mut geo =
                Geo { r, ring, nw: nrel.div_ceil(64).max(1), npat, pat, halo, beam, beam_id, line: Vec::new(), lc: Vec::new() };
            geo.lc = (0..6 * ring)
                .map(|kp| {
                    let (k, o) = (kp / ring, geo.offset(kp / ring, kp % ring));
                    match (o <= 2 * r, k < 3) {
                        (true, true) => o as u16,
                        (true, false) => (2 * r - o) as u16,
                        (false, _) => (100 + o + ring * k) as u16,
                    }
                })
                .collect();
            geo.line = (0..npat * 6)
                .map(|jk| {
                    let (j, k) = (jk / 6, jk % 6);
                    (0..=2 * r)
                        .find(|&o| geo.beam(k, geo.pos_at(k, o))[j / 64] >> (j % 64) & 1 == 1)
                        .expect("every cell lies on one line per direction") as u8
                })
                .collect();
            geo
        }

        pub fn beam(&self, k: usize, p: usize) -> &Bits {
            &self.beam[k * self.ring + p]
        }

        /// Emitter `k` only ever needs the `2r+1` ring positions centred on its start: elsewhere
        /// its beam runs along the border or off the board. This is the first of them.
        pub fn window_start(&self, k: usize) -> usize {
            (k * self.r + self.ring - self.r) % self.ring
        }

        /// Offset of ring position `p` in emitter `k`'s window (`> 2r` means outside).
        pub fn offset(&self, k: usize, p: usize) -> usize {
            (p + self.ring - self.window_start(k)) % self.ring
        }

        /// Ring position at window offset `o` of emitter `k`.
        pub fn pos_at(&self, k: usize, o: usize) -> usize {
            (self.window_start(k) + o) % self.ring
        }
    }
}

/// Exact simulation on the relevant-cell bitsets.
mod sim {
    use super::geo::{Bits, Geo, MAXW};
    use super::{Action, BWD, FWD, TOGGLE, op};

    /// Everything that determines the future: matter on relevant cells, the emitters, copies.
    #[derive(Clone, Copy, PartialEq, Eq, Debug)]
    pub struct State {
        pub m: Bits,
        /// Ring position per emitter.
        pub pos: [u8; 6],
        /// Bit `k` set = emitter `k` is on.
        pub act: u8,
        /// Copies detected so far.
        pub subs: u8,
    }

    impl State {
        pub fn start(geo: &Geo) -> State {
            State { m: [0; MAXW], pos: std::array::from_fn(|k| (k * geo.r) as u8), act: 0, subs: 0 }
        }
    }

    /// New ring position after instruction `code` (wrapping around the ring).
    pub fn moved(geo: &Geo, p: usize, code: u16) -> usize {
        match code {
            FWD => (p + 1) % geo.ring,
            BWD => (p + geo.ring - 1) % geo.ring,
            _ => p,
        }
    }

    /// One tick: instructions, beams, matter rules, copy detection. `NW` = bitset words in use.
    #[inline(always)]
    pub fn step<const NW: usize>(geo: &Geo, s: &State, a: Action) -> State {
        let mut t = *s;
        let (mut c1, mut c2, mut c3) = ([0u64; NW], [0u64; NW], [0u64; NW]);
        for k in 0..6 {
            let code = op(a, k);
            t.pos[k] = moved(geo, t.pos[k] as usize, code) as u8;
            if code == TOGGLE {
                t.act ^= 1 << k;
            }
            if t.act >> k & 1 == 1 {
                let b = geo.beam(k, t.pos[k] as usize);
                for w in 0..NW {
                    c3[w] |= c2[w] & b[w];
                    c2[w] |= c1[w] & b[w];
                    c1[w] |= b[w];
                }
            }
        }
        let mut full = true;
        for w in 0..NW {
            t.m[w] = (t.m[w] | c2[w]) & !c3[w];
            full &= t.m[w] & geo.pat[w] == geo.pat[w] && t.m[w] & geo.halo[w] == 0;
        }
        if full {
            t.subs = t.subs.saturating_add(1);
            for w in 0..NW {
                t.m[w] &= !geo.pat[w];
            }
        }
        t
    }

    /// [`step`] for any word count.
    pub fn step_any(geo: &Geo, s: &State, a: Action) -> State {
        match geo.nw {
            1 => step::<1>(geo, s, a),
            2 => step::<2>(geo, s, a),
            3 => step::<3>(geo, s, a),
            4 => step::<4>(geo, s, a),
            5 => step::<5>(geo, s, a),
            6 => step::<6>(geo, s, a),
            7 => step::<7>(geo, s, a),
            _ => step::<8>(geo, s, a),
        }
    }

    pub fn run(geo: &Geo, start: &State, prog: &[Action]) -> State {
        prog.iter().fold(*start, |s, &a| step_any(geo, &s, a))
    }

    /// Number of lines after which `prog` has detected `count` copies (`None` if it never does).
    pub fn finish_len(geo: &Geo, prog: &[Action], count: usize) -> Option<usize> {
        let mut s = State::start(geo);
        for (i, &a) in prog.iter().enumerate() {
            s = step_any(geo, &s, a);
            if s.subs as usize >= count {
                return Some(i + 1);
            }
        }
        None
    }
}

/// The 12 symmetries of the hex board, and programs mapped between symmetric boards.
mod sym {
    use super::{Action, BWD, FWD, op};
    use crate::model::{Board, Pattern};

    /// Mirror (row `y` -> `2R - y`) first, then `rot` rotations by 60° clockwise.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Sym {
        pub mirror: bool,
        pub rot: u8,
    }

    pub const IDENTITY: Sym = Sym { mirror: false, rot: 0 };

    pub const ALL: [Sym; 12] = {
        let mut all = [IDENTITY; 12];
        let mut i = 0;
        while i < 12 {
            all[i] = Sym { mirror: i >= 6, rot: (i % 6) as u8 };
            i += 1;
        }
        all
    };

    impl Sym {
        /// The emitter that emitter `k` becomes on the transformed board. A rotation shifts
        /// directions by one per 60°; the mirror swaps ↘/↗ and ↙/↖ and reverses the ring.
        fn emitter(self, k: usize) -> usize {
            let k = if self.mirror { (6 - k) % 6 } else { k };
            (k + self.rot as usize) % 6
        }

        /// Instruction code as seen on the transformed board (the mirror swaps F and B).
        fn code(self, c: u16) -> u16 {
            match (self.mirror, c) {
                (true, FWD) => BWD,
                (true, BWD) => FWD,
                _ => c,
            }
        }

        /// A line for the original board -> the equivalent line for the transformed board.
        pub fn forward(self, a: Action) -> Action {
            (0..6).fold(0, |b, k| b | self.code(op(a, k)) << (2 * self.emitter(k)))
        }

        /// A line for the transformed board -> the equivalent line for the original board.
        pub fn back(self, a: Action) -> Action {
            (0..6).fold(0, |b, k| b | self.code(op(a, self.emitter(k))) << (2 * k))
        }

        /// The pattern moved by this symmetry (on a board of the same shape).
        pub fn pattern(self, p: &Pattern) -> Pattern {
            let r = p.board.r as i64;
            let mut grid = p.board.grid.clone();
            for &(y, x) in &p.cells {
                grid[y][x] = b'O';
            }
            for &(y, x) in &p.cells {
                let y = if self.mirror { 2 * r - y as i64 } else { y as i64 };
                // Axial coordinates around the centre: x = 2R + 2a + b, y = R + b.
                let mut b = y - r;
                let mut a = (x as i64 - 2 * r - b) / 2;
                for _ in 0..self.rot {
                    (a, b) = (-b, a + b);
                }
                grid[(r + b) as usize][(2 * r + 2 * a + b) as usize] = b'M';
            }
            Pattern::new(Board { r: p.board.r, grid })
        }
    }
}

/// One beam-search attempt: from a start state, find a program reaching `count` copies within
/// `max_ticks` lines. This is the hot loop.
///
/// Every tick expands each beam state by all instruction lines (up to 4^6). Options are grouped
/// per emitter by the beam they produce (an emitter that is off and stays off, or whose beam
/// hits nothing, yields the same matter whatever it does), so the matter update and scoring run
/// once per beam combination; the members of a group ("variants") only differ in emitter
/// positions and get their score by one addition. The beam combinations are enumerated
/// depth-first with shared prefixes: emitter `k`'s beam is added to the hit counters of the
/// first `k` emitters (bitsets for >=1, >=2, >=3 hits).
mod beam {
    use super::geo::{Bits, EMPTY, Geo, MAXW};
    use super::sim::{self, State};
    use super::{Action, BWD, FWD, NOP, TOGGLE};

    /// Search knobs (defaults = beam5.c's as run by cloud_beam.py).
    #[derive(Clone, Debug)]
    pub struct Params {
        /// States kept per tick.
        pub width: usize,
        /// Children kept per parent.
        pub kcap: usize,
        /// The stage-2 pool (tail rerank) holds `pool * width` states.
        pub pool: usize,
        /// Score weight per painted pattern cell.
        pub wa: i64,
        /// Score weight per step an emitter needs to reach a useful line (or to switch on).
        pub wd: i64,
        /// 0: never put matter on the halo. > 0: allowed, this penalty per halo cell with matter.
        pub hp: i64,
        /// Tie-break noise added to every child score: uniform `0..=tn`, plus `0..nz`.
        pub tn: u32,
        pub nz: u32,
        /// A state is in the tail when at most this percentage of the pattern is missing.
        pub tail_pct: usize,
        /// Tail: penalty per missing cell and step of the second-closest emitter line (cap 6).
        pub h2: i64,
    }

    impl Default for Params {
        fn default() -> Params {
            Params { width: 800, kcap: 30, pool: 3, wa: 100, wd: 5, hp: 0, tn: 10, nz: 0, tail_pct: 25, h2: 30 }
        }
    }

    /// Counters of one attempt (for benchmarks).
    #[derive(Clone, Copy, Debug, Default)]
    pub struct Stats {
        pub ticks: usize,
        /// Children (instruction lines) of all expanded states: the work of a plain expansion.
        pub nominal: u64,
        /// Children (instruction lines) scored.
        pub children: u64,
        /// Beam combinations evaluated (matter update + scoring).
        pub leaves: u64,
    }

    /// Runs one attempt. `abort` is polled every tick. Returns the lines after `start`.
    pub fn search(
        geo: &Geo,
        start: &State,
        count: usize,
        max_ticks: usize,
        prm: &Params,
        seed: u64,
        abort: &dyn Fn() -> bool,
    ) -> (Option<Vec<Action>>, Stats) {
        match geo.nw {
            1 => Search::<1>::new(geo, count, prm, seed).run(start, max_ticks, abort),
            2 => Search::<2>::new(geo, count, prm, seed).run(start, max_ticks, abort),
            3 => Search::<3>::new(geo, count, prm, seed).run(start, max_ticks, abort),
            4 => Search::<4>::new(geo, count, prm, seed).run(start, max_ticks, abort),
            5 => Search::<5>::new(geo, count, prm, seed).run(start, max_ticks, abort),
            6 => Search::<6>::new(geo, count, prm, seed).run(start, max_ticks, abort),
            7 => Search::<7>::new(geo, count, prm, seed).run(start, max_ticks, abort),
            _ => Search::<8>::new(geo, count, prm, seed).run(start, max_ticks, abort),
        }
    }

    /// Score of a child: copies dominate, then painted cells, minus distance penalties; times
    /// 1024 plus random tie-break bits.
    const COPY_SCORE: i64 = 10_000_000;
    const NO_BEAM: u32 = u32::MAX;
    /// The beam of an option that fires nothing.
    static ZERO: Bits = [0; MAXW];

    /// The `cap` largest (key, line) pairs pushed so far, as a binary min-heap.
    struct TopK {
        heap: Vec<(i64, Action)>,
        cap: usize,
    }

    impl TopK {
        /// Keys at or below this cannot enter any more.
        #[inline(always)]
        fn threshold(&self) -> i64 {
            if self.heap.len() < self.cap { i64::MIN } else { self.heap[0].0 }
        }

        #[inline(always)]
        fn push(&mut self, item: (i64, Action)) {
            let h = &mut self.heap;
            if h.len() < self.cap {
                h.push(item);
                let mut i = h.len() - 1;
                while i > 0 && h[(i - 1) / 2].0 > h[i].0 {
                    h.swap(i, (i - 1) / 2);
                    i = (i - 1) / 2;
                }
            } else if item.0 > h[0].0 {
                h[0] = item;
                let mut i = 0;
                loop {
                    let (l, r) = (2 * i + 1, 2 * i + 2);
                    let mut m = i;
                    if l < h.len() && h[l].0 < h[m].0 {
                        m = l;
                    }
                    if r < h.len() && h[r].0 < h[m].0 {
                        m = r;
                    }
                    if m == i {
                        break;
                    }
                    h.swap(i, m);
                    i = m;
                }
            }
        }
    }

    /// One option of one emitter: its instruction (already shifted into place) and penalty.
    #[derive(Clone, Copy, Default)]
    struct Variant {
        code: u16,
        pen: i32,
    }

    /// Options of one emitter that produce the same beam.
    #[derive(Clone, Copy)]
    struct Group {
        /// Index into `geo.beam`, or [`NO_BEAM`].
        beam: u32,
        n: usize,
        vars: [Variant; 4],
        /// Smallest penalty among `vars`.
        min_pen: i32,
    }

    const NO_GROUP: Group = Group { beam: NO_BEAM, n: 0, vars: [Variant { code: 0, pen: 0 }; 4], min_pen: 0 };

    /// A child that survived its parent's cap: score, state hash, where it came from.
    #[derive(Clone, Copy)]
    struct Cand {
        key: i64,
        hash: u64,
        parent: u32,
        code: Action,
    }

    struct Search<'g, const NW: usize> {
        geo: &'g Geo,
        count: usize,
        prm: Params,
        rng: u64,
        pat: [u64; NW],
        halo: [u64; NW],
        stats: Stats,

        // --- per parent ---
        m: [u64; NW],
        subs: u8,
        /// Option groups per emitter.
        groups: [[Group; 4]; 6],
        ngroups: [usize; 6],
        /// Emitters in search order: fewest groups first, so the fused last level does most work.
        order: [usize; 6],
        /// Halo matter is possible (allowed by `hp`, or already in the parent).
        junk_possible: bool,
        /// `reach[l]`: every cell some option of the emitters at levels `l..6` could still hit;
        /// `reach2[l]`: cells two different such emitters could hit.
        reach: [[u64; NW]; 7],
        reach2: [[u64; NW]; 7],
        /// `rest_pen[l]`: the smallest total penalty of the emitters at levels `l..6`.
        rest_pen: [i32; 7],
        /// Hit counters after the first `k` emitters: >=1, >=2, >=3 beams.
        c1: [[u64; NW]; 7],
        c2: [[u64; NW]; 7],
        c3: [[u64; NW]; 7],
        /// Variant lists: `vars[l][..nvars[l]]` = (code, penalty) combinations built at level `l`,
        /// `minpen[l]` = their smallest penalty.
        vars: Vec<[(u16, i32); 4096]>,
        nvars: [usize; 7],
        minpen: [i32; 7],
        /// The current parent's best `kcap` children: (key, line).
        local: TopK,
        found: Option<Action>,

        // --- per tick ---
        pool: Vec<Cand>,
        pool_thr: i64,
        seen: Vec<u64>,
    }

    impl<'g, const NW: usize> Search<'g, NW> {
        fn new(geo: &'g Geo, count: usize, prm: &Params, seed: u64) -> Self {
            let keep = prm.pool * prm.width;
            Search {
                geo,
                count,
                prm: prm.clone(),
                rng: super::opt::mix(seed) | 1,
                pat: std::array::from_fn(|w| geo.pat[w]),
                halo: std::array::from_fn(|w| geo.halo[w]),
                stats: Stats::default(),
                m: [0; NW],
                subs: 0,
                groups: [[NO_GROUP; 4]; 6],
                ngroups: [0; 6],
                order: [0, 1, 2, 3, 4, 5],
                junk_possible: false,
                reach: [[0; NW]; 7],
                reach2: [[0; NW]; 7],
                rest_pen: [0; 7],
                c1: [[0; NW]; 7],
                c2: [[0; NW]; 7],
                c3: [[0; NW]; 7],
                vars: vec![[(0, 0); 4096]; 7],
                nvars: [0; 7],
                minpen: [0; 7],
                local: TopK { heap: Vec::with_capacity(prm.kcap), cap: prm.kcap.max(1) },
                found: None,
                pool: Vec::with_capacity(8 * keep + 64),
                pool_thr: i64::MIN,
                seen: vec![0; (4 * keep).next_power_of_two()],
            }
        }

        #[inline(always)]
        fn rand(&mut self) -> u64 {
            self.rng ^= self.rng << 13;
            self.rng ^= self.rng >> 7;
            self.rng ^= self.rng << 17;
            self.rng
        }

        /// Runs the attempt, compiled for the best instruction set this CPU has.
        fn run(self, start: &State, max_ticks: usize, abort: &dyn Fn() -> bool) -> (Option<Vec<Action>>, Stats) {
            #[cfg(target_arch = "x86_64")]
            if std::arch::is_x86_feature_detected!("avx2")
                && std::arch::is_x86_feature_detected!("popcnt")
                && std::arch::is_x86_feature_detected!("bmi1")
                && std::arch::is_x86_feature_detected!("lzcnt")
            {
                // SAFETY: the CPU supports every feature `run_x86_v3` is compiled for.
                return unsafe { self.run_x86_v3(start, max_ticks, abort) };
            }
            self.run_impl(start, max_ticks, abort)
        }

        /// [`Self::run_impl`] with popcnt / BMI / AVX2 code generation (x86-64-v3).
        #[cfg(target_arch = "x86_64")]
        #[target_feature(enable = "avx2,popcnt,bmi1,bmi2,lzcnt")]
        fn run_x86_v3(self, start: &State, max_ticks: usize, abort: &dyn Fn() -> bool) -> (Option<Vec<Action>>, Stats) {
            self.run_impl(start, max_ticks, abort)
        }

        /// The tick loop: expand every state, keep the best `width` distinct children.
        #[inline(always)]
        fn run_impl(mut self, start: &State, max_ticks: usize, abort: &dyn Fn() -> bool) -> (Option<Vec<Action>>, Stats) {
            let keep = self.prm.pool * self.prm.width;
            let cap = (keep + keep / 2).max(2048);
            let mut cur = vec![*start];
            // hist[t][i] = (parent index at tick t, line) of state i after tick t + 1.
            let mut hist: Vec<Vec<(u32, Action)>> = Vec::new();
            let mut next: Vec<State> = Vec::with_capacity(keep);
            let mut order: Vec<(i64, u32)> = Vec::with_capacity(keep);
            for tick in 0..max_ticks {
                if abort() {
                    return (None, self.stats);
                }
                self.stats.ticks = tick + 1;
                self.pool.clear();
                self.pool_thr = i64::MIN;
                for (pi, parent) in cur.iter().enumerate() {
                    self.expand(parent);
                    if let Some(code) = self.found {
                        let mut prog = vec![code];
                        let mut i = pi;
                        for h in hist.iter().rev() {
                            prog.push(h[i].1);
                            i = h[i].0 as usize;
                        }
                        prog.reverse();
                        return (Some(prog), self.stats);
                    }
                    for &(key, code) in &self.local.heap {
                        let child = sim::step::<NW>(self.geo, parent, code);
                        self.pool.push(Cand { key, hash: hash::<NW>(self.geo, &child), parent: pi as u32, code });
                    }
                    if self.pool.len() >= cap {
                        self.compact(keep);
                    }
                }
                self.compact(keep);
                if self.pool.is_empty() {
                    return (None, self.stats);
                }
                // Stage 2: materialise the pool, rerank states in the tail, keep `width`.
                next.clear();
                order.clear();
                for (i, c) in self.pool.iter().enumerate() {
                    let s = sim::step::<NW>(self.geo, &cur[c.parent as usize], c.code);
                    order.push((c.key - 1024 * self.prm.h2 * self.tail_penalty(&s), i as u32));
                    next.push(s);
                }
                let width = self.prm.width.min(order.len());
                if width < order.len() {
                    order.select_nth_unstable_by(width - 1, |a, b| b.cmp(a));
                    order.truncate(width);
                }
                hist.push(order.iter().map(|&(_, i)| (self.pool[i as usize].parent, self.pool[i as usize].code)).collect());
                cur.clear();
                cur.extend(order.iter().map(|&(_, i)| next[i as usize]));
            }
            (None, self.stats)
        }

        /// Sorts the pool by score, drops duplicate states, keeps the best `keep`.
        fn compact(&mut self, keep: usize) {
            self.pool.sort_unstable_by(|a, b| b.key.cmp(&a.key).then(a.hash.cmp(&b.hash)));
            self.seen.fill(0);
            let mask = self.seen.len() - 1;
            let mut n = 0;
            for i in 0..self.pool.len() {
                if n == keep {
                    break;
                }
                let h = self.pool[i].hash | 1;
                let mut j = (h >> 7) as usize & mask;
                let dup = loop {
                    match self.seen[j] {
                        0 => break false,
                        x if x == h => break true,
                        _ => j = (j + 1) & mask,
                    }
                };
                if !dup {
                    self.seen[j] = h;
                    self.pool[n] = self.pool[i];
                    n += 1;
                }
            }
            self.pool.truncate(n);
            if n == keep {
                self.pool_thr = self.pool[n - 1].key;
            }
        }

        /// Tail heuristic: once few pattern cells are missing, each of them needs two emitters
        /// lined up; sum over missing cells of the second-closest emitter's distance (cap 6).
        #[inline(always)]
        fn tail_penalty(&self, s: &State) -> i64 {
            let geo = self.geo;
            let missing: u32 = (0..NW).map(|w| (self.pat[w] & !s.m[w]).count_ones()).sum();
            if missing == 0 || missing as usize * 100 > geo.npat * self.prm.tail_pct || self.prm.h2 == 0 {
                return 0;
            }
            let off: [i64; 6] = std::array::from_fn(|k| geo.offset(k, s.pos[k] as usize) as i64);
            let mut total = 0;
            for w in 0..NW {
                let mut bits = self.pat[w] & !s.m[w];
                while bits != 0 {
                    let j = w * 64 + bits.trailing_zeros() as usize;
                    bits &= bits - 1;
                    let (mut d1, mut d2) = (99, 99);
                    for k in 0..6 {
                        let d = (off[k] - geo.line[j * 6 + k] as i64).abs() + (s.act >> k & 1 == 0) as i64;
                        if d < d1 {
                            (d1, d2) = (d, d1);
                        } else if d < d2 {
                            d2 = d;
                        }
                    }
                    total += d2.min(6);
                }
            }
            total
        }

        /// Builds the emitter option groups of `parent` (with their distance penalties).
        #[inline(always)]
        fn prepare(&mut self, parent: &State) {
            let geo = self.geo;
            let r2 = 2 * geo.r;
            self.m = std::array::from_fn(|w| parent.m[w]);
            self.subs = parent.subs;
            let unpainted: [u64; NW] = std::array::from_fn(|w| self.pat[w] & !parent.m[w]);
            let mut nominal = 1;
            for k in 0..6 {
                // Window offsets whose beam would paint a missing pattern cell.
                let mut useful = 0u64;
                for o in 0..=r2 {
                    let b = geo.beam(k, geo.pos_at(k, o));
                    if (0..NW).any(|w| b[w] & unpainted[w] != 0) {
                        useful |= 1 << o;
                    }
                }
                let p = parent.pos[k] as usize;
                let on = parent.act >> k & 1 == 1;
                let o = geo.offset(k, p);
                // Moves stay inside the window (or head back into it).
                let fwd_ok = o + 1 <= r2 || o > r2;
                let bwd_ok = (o >= 1 && o <= r2) || o > r2;
                let mut opts: [(u16, usize, bool); 4] = [(NOP, p, on); 4];
                let mut nopts = 1;
                if fwd_ok {
                    opts[nopts] = (FWD, sim::moved(geo, p, FWD), on);
                    nopts += 1;
                }
                if bwd_ok {
                    opts[nopts] = (BWD, sim::moved(geo, p, BWD), on);
                    nopts += 1;
                }
                opts[nopts] = (TOGGLE, p, !on);
                nopts += 1;
                let mut ng = 0;
                for &(code, q, a) in &opts[..nopts] {
                    let id = if a { geo.beam_id[k * geo.ring + q] } else { EMPTY };
                    let beam = if id == EMPTY { NO_BEAM } else { (k * geo.ring + q) as u32 };
                    let dist = distance(useful, geo.offset(k, q), r2) + (useful != 0 && !a) as i64;
                    let var = Variant { code: code << (2 * k), pen: (self.prm.wd * dist) as i32 };
                    let same = |g: &Group| {
                        g.beam == beam || (g.beam != NO_BEAM && beam != NO_BEAM && geo.beam_id[g.beam as usize] == id)
                    };
                    match self.groups[k][..ng].iter().position(same) {
                        Some(g) => {
                            let grp = &mut self.groups[k][g];
                            grp.vars[grp.n] = var;
                            grp.n += 1;
                            grp.min_pen = grp.min_pen.min(var.pen);
                        }
                        None => {
                            self.groups[k][ng] = Group { beam, n: 1, vars: [var; 4], min_pen: var.pen };
                            ng += 1;
                        }
                    }
                }
                self.ngroups[k] = ng;
                // Cheapest groups first: good children early raise the threshold sooner.
                self.groups[k][..ng].sort_by_key(|g| g.min_pen);
                nominal *= nopts as u64;
            }
            self.junk_possible = self.prm.hp != 0 || (0..NW).any(|w| parent.m[w] & self.halo[w] != 0);
            self.order = [0, 1, 2, 3, 4, 5];
            let ng = self.ngroups;
            self.order.sort_by_key(|&e| ng[e]);
            self.stats.nominal += nominal;
            self.reach[6] = [0; NW];
            self.reach2[6] = [0; NW];
            self.rest_pen[6] = 0;
            for l in (0..6).rev() {
                let k = self.order[l];
                let mut u = [0; NW];
                let mut min_pen = i32::MAX;
                for g in &self.groups[k][..self.ngroups[k]] {
                    if g.beam != NO_BEAM {
                        let b = &geo.beam[g.beam as usize];
                        for w in 0..NW {
                            u[w] |= b[w];
                        }
                    }
                    min_pen = min_pen.min(g.min_pen);
                }
                for w in 0..NW {
                    self.reach2[l][w] = self.reach2[l + 1][w] | (self.reach[l + 1][w] & u[w]);
                    self.reach[l][w] = self.reach[l + 1][w] | u[w];
                }
                self.rest_pen[l] = self.rest_pen[l + 1] + min_pen;
            }
        }

        /// Expands one parent: fills `self.local` with its best `kcap` children (or sets `found`).
        #[inline(always)]
        fn expand(&mut self, parent: &State) {
            self.prepare(parent);
            self.local.heap.clear();
            self.c1[0] = [0; NW];
            self.c2[0] = [0; NW];
            self.c3[0] = [0; NW];
            self.vars[0][0] = (0, 0);
            self.nvars[0] = 1;
            self.minpen[0] = 0;
            self.dfs();
        }

        /// Depth-first over the beam groups, emitter `order[l]` at level `l`; level 5 is fused
        /// with the evaluation ([`Self::last_level`]). Iterative (no recursion) so that it can
        /// be inlined into the CPU-specific entry points. At level `l`, the variant combinations
        /// so far are `vars[src[l]]`, each plus `(code[l], pen[l])`.
        #[inline(always)]
        fn dfs(&mut self) {
            let mut next = [0usize; 6];
            let mut src = [0usize; 6];
            let mut code = [0u16; 6];
            let mut pen = [0i32; 6];
            let mut l = 0;
            loop {
                if l == 5 {
                    self.last_level(src[5], code[5], pen[5]);
                    if self.found.is_some() {
                        return;
                    }
                    l = 4;
                    continue;
                }
                let e = self.order[l];
                if next[l] == self.ngroups[e] {
                    if l == 0 {
                        return;
                    }
                    l -= 1;
                    continue;
                }
                let grp = self.groups[e][next[l]];
                next[l] += 1;
                let b = self.geo.beam.get(grp.beam as usize).unwrap_or(&ZERO);
                let mut bad = 0;
                for w in 0..NW {
                    let (x1, x2, x3) = (self.c1[l][w], self.c2[l][w], self.c3[l][w]);
                    let (y2, y3) = (x2 | (x1 & b[w]), x3 | (x2 & b[w]));
                    self.c1[l + 1][w] = x1 | b[w];
                    self.c2[l + 1][w] = y2;
                    self.c3[l + 1][w] = y3;
                    // A halo cell hit exactly twice that no later emitter can reach gets matter.
                    bad |= y2 & !y3 & self.halo[w] & !self.reach[l + 1][w];
                }
                if bad != 0 && self.prm.hp == 0 {
                    continue;
                }
                if self.hopeless(l + 1, src[l], pen[l] + grp.min_pen) {
                    continue;
                }
                if grp.n == 1 {
                    src[l + 1] = src[l];
                    code[l + 1] = code[l] | grp.vars[0].code;
                    pen[l + 1] = pen[l] + grp.vars[0].pen;
                } else {
                    let (lo, hi) = self.vars.split_at_mut(l + 1);
                    let (from, to) = (&lo[src[l]][..self.nvars[src[l]]], &mut hi[0]);
                    let mut n = 0;
                    for &(c, p) in from {
                        for v in &grp.vars[..grp.n] {
                            to[n] = (c | code[l] | v.code, p + pen[l] + v.pen);
                            n += 1;
                        }
                    }
                    self.nvars[l + 1] = n;
                    self.minpen[l + 1] = self.minpen[src[l]] + pen[l] + grp.min_pen;
                    src[l + 1] = l + 1;
                    code[l + 1] = 0;
                    pen[l + 1] = 0;
                }
                next[l + 1] = 0;
                l += 1;
            }
        }

        /// Branch and bound: true if no child below this node (counters at level `l`, variant
        /// list `src`, penalty so far `dpen`) can pass the current threshold, even with maximal
        /// noise. Such children would be dropped before drawing noise, so pruning them changes
        /// nothing. A pattern cell can end up painted only if it is not hit 3+ times yet and is
        /// matter, hit twice, hit once with an emitter left, or reachable by two emitters left.
        #[inline(always)]
        fn hopeless(&self, l: usize, src: usize, dpen: i32) -> bool {
            let thr = self.local.threshold().max(self.pool_thr);
            if thr == i64::MIN {
                return false;
            }
            let mut can = 0;
            for w in 0..NW {
                let (c1, c2, c3) = (self.c1[l][w], self.c2[l][w], self.c3[l][w]);
                let open = self.m[w] | c2 | (c1 & self.reach[l][w]) | self.reach2[l][w];
                can += (self.pat[w] & !c3 & open).count_ones();
            }
            if can as usize >= self.geo.npat {
                return false; // a copy may still be completed
            }
            let pen = (self.minpen[src] + dpen + self.rest_pen[l]) as i64;
            let best = self.subs as i64 * COPY_SCORE + can as i64 * self.prm.wa - pen + (self.prm.tn + self.prm.nz) as i64;
            best * 1024 + 1023 <= thr
        }

        /// The last level, fused with the evaluation of each complete beam combination (the
        /// "leaf"): matter update, halo rule, detection, score; then every variant is a child.
        #[inline(always)]
        fn last_level(&mut self, src: usize, dcode: u16, dpen: i32) {
            let e = self.order[5];
            for g in 0..self.ngroups[e] {
                let grp = self.groups[e][g];
                let b = self.geo.beam.get(grp.beam as usize).unwrap_or(&ZERO);
                let (mut halo_hit, mut painted, mut junk) = (0u64, 0u32, 0u32);
                for w in 0..NW {
                    let c2 = self.c2[5][w] | (self.c1[5][w] & b[w]);
                    let c3 = self.c3[5][w] | (self.c2[5][w] & b[w]);
                    let two = c2 & !c3;
                    let nm = (self.m[w] | two) & !c3;
                    halo_hit |= two & self.halo[w];
                    painted += (nm & self.pat[w]).count_ones();
                    if self.junk_possible {
                        junk += (nm & self.halo[w]).count_ones();
                    }
                }
                self.stats.leaves += 1;
                if self.prm.hp == 0 && halo_hit != 0 {
                    continue;
                }
                let full = painted as usize == self.geo.npat && junk == 0;
                let subs = self.subs as i64 + full as i64;
                if subs as usize >= self.count {
                    self.found = Some(self.vars[src][0].0 | dcode | grp.vars[0].code);
                    return;
                }
                let painted = if full { 0 } else { painted as i64 };
                let base = subs * COPY_SCORE + painted * self.prm.wa - junk as i64 * self.prm.hp - dpen as i64;
                for v in 0..grp.n {
                    let v = grp.vars[v];
                    self.children(src, dcode | v.code, base - v.pen as i64);
                }
            }
        }

        /// Offers the children `vars[src]` (each plus `dcode`) with score `base - penalty` to
        /// the parent's top `kcap`.
        #[inline(always)]
        fn children(&mut self, src: usize, dcode: u16, base: i64) {
            let n = self.nvars[src];
            self.stats.children += n as u64;
            let max_noise = (self.prm.tn + self.prm.nz) as i64;
            let mut thr = self.local.threshold().max(self.pool_thr);
            // Even the cheapest variant with the most noise cannot make it.
            if (base - self.minpen[src] as i64 + max_noise) * 1024 + 1023 <= thr {
                return;
            }
            let (tn1, nz) = (self.prm.tn as u64 + 1, self.prm.nz as u64);
            for i in 0..n {
                let (code, pen) = self.vars[src][i];
                let sc = base - pen as i64;
                if (sc + max_noise) * 1024 + 1023 <= thr {
                    continue;
                }
                let r = self.rand();
                let noise = ((r & 0xffff_ffff) * tn1 >> 32) + (((r >> 32) & 0x3f_ffff) * nz >> 22);
                let key = (sc + noise as i64) * 1024 + (r >> 54) as i64;
                if key <= thr {
                    continue;
                }
                self.local.push((key, code | dcode));
                thr = self.local.threshold().max(self.pool_thr);
            }
        }
    }

    /// Steps from window offset `o` to the nearest set bit of `useful` (0 if none). Offsets
    /// beyond `r2` are outside the window and first walk back to its nearer end.
    fn distance(useful: u64, o: usize, r2: usize) -> i64 {
        if useful == 0 {
            return 0;
        }
        if o > r2 {
            return 99;
        }
        let up = useful >> o;
        let d_up = if up != 0 { up.trailing_zeros() as i64 } else { 99 };
        let down = useful << (63 - o);
        let d_down = if down != 0 { down.leading_zeros() as i64 } else { 99 };
        d_up.min(d_down)
    }

    /// Hash of a state up to swapping the (line, on) states of opposite emitters (see
    /// [`Geo::lc`]): such states have the same future, so the beam keeps only one of them.
    #[inline(always)]
    fn hash<const NW: usize>(geo: &Geo, s: &State) -> u64 {
        const K: u64 = 0x9E37_79B9_7F4A_7C15;
        let mut h = K;
        for w in 0..NW {
            h = (h ^ s.m[w]).wrapping_mul(K);
            h ^= h >> 29;
        }
        let key = |k: usize| (geo.lc[k * geo.ring + s.pos[k] as usize] as u64) << 1 | (s.act >> k & 1) as u64;
        h = (h ^ s.subs as u64).wrapping_mul(K);
        for a in 0..3 {
            let (x, y) = (key(a), key(a + 3));
            h = (h ^ (x.min(y) << 16 | x.max(y))).wrapping_mul(K);
            h ^= h >> 29;
        }
        h
    }
}

/// Known programs to start from.
mod seeds {
    use super::geo::Geo;
    use super::{Action, Case, pack, parse_program, sim, split_programs};
    use std::path::PathBuf;

    /// `L6_SEED_DIR` if set (empty = no seeds), else `work/level6/best` of this repo if it exists.
    fn dir() -> Option<PathBuf> {
        match std::env::var("L6_SEED_DIR") {
            Ok(d) if d.is_empty() => None,
            Ok(d) => Some(PathBuf::from(d)),
            Err(_) => {
                let d = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../work/level6/best"));
                d.is_dir().then_some(d)
            }
        }
    }

    /// Per case, the shortest valid program among all files in the seed directory that have one
    /// program per case (cut after the last needed copy).
    pub fn load(cases: &[Case], geos: &[Geo]) -> Vec<Option<Vec<Action>>> {
        let mut best: Vec<Option<Vec<Action>>> = vec![None; cases.len()];
        let Some(dir) = dir() else { return best };
        let mut files: Vec<PathBuf> =
            std::fs::read_dir(&dir).into_iter().flatten().flatten().map(|e| e.path()).filter(|p| p.is_file()).collect();
        files.sort();
        for f in files {
            let Ok(text) = std::fs::read_to_string(&f) else { continue };
            let lines: Vec<String> = text.lines().map(str::to_owned).collect();
            let progs = split_programs(&lines);
            if progs.len() != cases.len() {
                continue;
            }
            for (i, p) in progs.iter().enumerate() {
                let Ok(prog) = parse_program(p) else { continue };
                let prog: Vec<Action> = prog.iter().map(pack).collect();
                if let Some(len) = sim::finish_len(&geos[i], &prog, cases[i].count) {
                    if best[i].as_ref().is_none_or(|b| len < b.len()) {
                        best[i] = Some(prog[..len].to_vec());
                    }
                }
            }
        }
        best
    }
}

/// The optimiser: improves one incumbent per case with repeated beam attempts.
mod opt {
    use super::beam::{self, Params};
    use super::geo::Geo;
    use super::sim::{self, State};
    use super::sym::{self, Sym};
    use super::{Action, Case, count_accepted, seeds, unpack};
    use std::sync::{Condvar, Mutex};

    /// Beam widths by attempt number (the last one repeats).
    const WIDTHS: [usize; 4] = [800, 1500, 3000, 6000];
    /// Fractions of the incumbent kept as a fixed prefix (one is drawn per attempt).
    const PREFIX: [f64; 7] = [0.0, 0.0, 0.25, 0.4, 0.55, 0.7, 0.85];

    /// SplitMix64 finaliser: a well-mixed 64-bit value from any input.
    pub fn mix(mut x: u64) -> u64 {
        x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
        x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        x ^ (x >> 31)
    }

    fn env_u64(name: &str) -> Option<u64> {
        std::env::var(name).ok().and_then(|v| v.parse().ok())
    }

    /// Process-wide limit on concurrent attempts: `cargo ccc all` solves all input files at once,
    /// and together they must not use more than `CCC_THREADS` cores.
    static SLOTS: (Mutex<usize>, Condvar) = (Mutex::new(0), Condvar::new());

    fn with_slot<R>(f: impl FnOnce() -> R) -> R {
        let limit = harness::par::threads();
        let (lock, cv) = &SLOTS;
        let mut busy = lock.lock().unwrap();
        while *busy >= limit {
            busy = cv.wait(busy).unwrap();
        }
        *busy += 1;
        drop(busy);
        let r = f();
        *lock.lock().unwrap() -= 1;
        cv.notify_one();
        r
    }

    /// A case's search data: lazily built geometry per symmetry and the incumbent.
    struct CaseRun<'a> {
        index: usize,
        case: &'a Case,
        geos: Vec<Option<Geo>>,
        best: Option<Vec<Action>>,
        attempts: u64,
        improved: u64,
    }

    impl CaseRun<'_> {
        fn geo(&mut self, s: usize) -> &Geo {
            let case = self.case;
            self.geos[s].get_or_insert_with(|| Geo::new(&sym::ALL[s].pattern(&case.pattern)))
        }

        /// One attempt; replaces the incumbent if it finds a shorter valid program.
        fn attempt(&mut self, seed: u64) {
            let n = self.attempts;
            self.attempts += 1;
            let mut rng = mix(seed ^ mix(self.index as u64) ^ mix(n << 32));
            let mut draw = |k: usize| {
                rng = mix(rng);
                (rng % k as u64) as usize
            };
            let count = self.case.count;
            let (s, prefix, max_ticks, width, abort): (usize, Vec<Action>, usize, usize, bool) = match &self.best {
                // No incumbent yet: construct from scratch (never aborted, so there is a result).
                None => (0, Vec::new(), 999, 200 << n.min(4), false),
                Some(best) => {
                    let s = if n == 0 { 0 } else { draw(12) };
                    let npre = (best.len() as f64 * PREFIX[draw(PREFIX.len())]) as usize;
                    (s, best[..npre].to_vec(), best.len() - 1 - npre, WIDTHS[(n as usize).min(WIDTHS.len() - 1)], true)
                }
            };
            if max_ticks == 0 {
                return;
            }
            let sym = sym::ALL[s];
            let prm = Params { width, nz: [0, 0, 1, 2][draw(4)], ..Params::default() };
            let search_seed = rng;
            let geo = self.geo(s);
            let fwd: Vec<Action> = prefix.iter().map(|&a| sym.forward(a)).collect();
            let start = sim::run(geo, &State::start(geo), &fwd);
            if start.subs as usize >= count {
                return;
            }
            let stop = || abort && harness::budget::expired();
            let (found, _) = beam::search(geo, &start, count, max_ticks, &prm, search_seed, &stop);
            let Some(rest) = found else { return };
            let mut prog = prefix;
            prog.extend(rest.iter().map(|&a| sym.back(a)));
            self.offer(prog, sym, width);
        }

        /// Keeps `prog` if it is valid (exact bitset simulation and `model.rs`) and shorter.
        fn offer(&mut self, prog: Vec<Action>, sym: Sym, width: usize) {
            let count = self.case.count;
            let Some(len) = sim::finish_len(self.geo(0), &prog, count) else {
                panic!("case {}: beam result does not validate ({sym:?})", self.index)
            };
            if self.best.as_ref().is_some_and(|b| b.len() <= len) {
                return;
            }
            let lines: Vec<[u8; 6]> = prog[..len].iter().map(|&a| unpack(a)).collect();
            assert!(count_accepted(&self.case.pattern, &lines) >= count, "case {}: simulators disagree", self.index);
            harness::trace!(
                "case {}: {} -> {len} lines (attempt {}, width {width}, {sym:?})",
                self.index,
                self.best.as_ref().map_or(0, |b| b.len()),
                self.attempts - 1
            );
            self.best = Some(prog[..len].to_vec());
            self.improved += 1;
        }
    }

    /// Which case a worker should attempt next: incumbents first, then round-robin.
    struct Schedule {
        busy: Vec<bool>,
        attempts: Vec<u64>,
        built: Vec<bool>,
    }

    /// Best program per case: seeds (if any) improved until the budget runs out, or built from
    /// scratch. Deterministic per case for a fixed `L6_SEED` and number of attempts.
    pub fn optimize(cases: &[Case]) -> Vec<Vec<Action>> {
        let seed = env_u64("L6_SEED").unwrap_or(0);
        // Without --budget there is no deadline: only construct what has no seed.
        let rounds = env_u64("L6_ROUNDS").unwrap_or(if harness::budget::per_file().is_some() { u64::MAX } else { 0 });
        let geos: Vec<Geo> = cases.iter().map(|c| Geo::new(&c.pattern)).collect();
        let seeded = seeds::load(cases, &geos);
        let seed_total: usize = seeded.iter().flatten().map(Vec::len).sum();
        let runs: Vec<Mutex<CaseRun>> = cases
            .iter()
            .zip(geos)
            .zip(seeded)
            .enumerate()
            .map(|(index, ((case, geo), best))| {
                let mut geos: Vec<Option<Geo>> = (0..12).map(|_| None).collect();
                geos[0] = Some(geo);
                Mutex::new(CaseRun { index, case, geos, best, attempts: 0, improved: 0 })
            })
            .collect();
        let schedule = Mutex::new(Schedule {
            busy: vec![false; cases.len()],
            attempts: vec![0; cases.len()],
            built: runs.iter().map(|r| r.lock().unwrap().best.is_some()).collect(),
        });
        let pick = || {
            let mut s = schedule.lock().unwrap();
            let expired = harness::budget::expired();
            let i = (0..cases.len())
                .filter(|&i| !s.busy[i] && (!s.built[i] || (!expired && s.attempts[i] < rounds)))
                .min_by_key(|&i| (s.built[i], s.attempts[i], i))?;
            s.busy[i] = true;
            Some(i)
        };
        let threads = harness::par::threads().min(cases.len()).max(1);
        let workers: Vec<usize> = (0..threads).collect();
        harness::par::map_threads(threads, &workers, |_| {
            while let Some(i) = pick() {
                let mut run = runs[i].lock().unwrap();
                let was_built = run.best.is_some();
                with_slot(|| run.attempt(seed));
                let mut s = schedule.lock().unwrap();
                s.busy[i] = false;
                s.built[i] = run.best.is_some();
                if was_built {
                    s.attempts[i] += 1;
                }
            }
        });
        let runs: Vec<CaseRun> = runs.into_iter().map(|r| r.into_inner().unwrap()).collect();
        let total: usize = runs.iter().map(|r| r.best.as_ref().map_or(0, |b| b.len())).sum();
        harness::trace!(
            "{} cases: {} lines (seeds {}), {} attempts, {} improvements",
            cases.len(),
            total,
            seed_total,
            runs.iter().map(|r| r.attempts).sum::<u64>(),
            runs.iter().map(|r| r.improved).sum::<u64>()
        );
        runs.into_iter().map(|r| r.best.expect("every case was built")).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::geo::Geo;
    use super::sim::{self, State};
    use super::*;
    use std::path::Path;

    const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/..");

    /// (input text, best output lines) for every real input that has a best output.
    fn best_files() -> Vec<(String, Vec<String>)> {
        let mut v = Vec::new();
        for name in ["1-small", "2-medium", "3-large", "4-enormous"] {
            let inp = Path::new(ROOT).join(format!("work/level6/in/in_level-6_{name}.txt"));
            let out = Path::new(ROOT).join(format!("work/level6/best/out_level-6_{name}.txt"));
            if let (Ok(i), Ok(o)) = (std::fs::read_to_string(inp), std::fs::read_to_string(out)) {
                v.push((i, o.lines().map(str::to_owned).collect()));
            }
        }
        v
    }

    fn programs(out: &[String]) -> Vec<Vec<Action>> {
        split_programs(out).iter().map(|p| parse_program(p).unwrap().iter().map(pack).collect()).collect()
    }

    /// Emitters `e` and `e + 3` fire along the same board lines in opposite order: offset `o`
    /// of `e + 3` hits exactly the cells of offset `2R - o` of `e` (the basis of [`geo::Geo::lc`]).
    #[test]
    fn opposite_emitters_share_lines() {
        for name in ["0-example", "1-small", "2-medium", "3-large", "4-enormous"] {
            let Ok(input) = std::fs::read_to_string(Path::new(ROOT).join(format!("work/level6/in/in_level-6_{name}.txt")))
            else {
                continue;
            };
            for c in parse(&input) {
                let geo = Geo::new(&c.pattern);
                let b = &c.pattern.board;
                let ring = crate::model::border_ring(geo.r);
                let cells = |k: usize, o: usize| {
                    let (y, x) = ring[geo.pos_at(k, o)];
                    let mut v = b.beam_cells(y, x, k as u8 + 1);
                    v.sort();
                    v
                };
                for k in 0..3 {
                    for o in 0..=2 * geo.r {
                        assert_eq!(cells(k + 3, o), cells(k, 2 * geo.r - o), "R={} k={k} o={o}", geo.r);
                    }
                }
            }
        }
    }

    #[test]
    fn pack_round_trip() {
        for a in 0..4096u16 {
            assert_eq!(pack(&unpack(a)), a);
        }
    }

    #[test]
    fn symmetry_line_round_trip() {
        for s in sym::ALL {
            for a in 0..4096u16 {
                assert_eq!(s.back(s.forward(a)), a, "{s:?}");
            }
        }
    }

    /// Every symmetric copy of a program detects as many copies on the symmetric board.
    #[test]
    fn symmetry_preserves_programs() {
        for (input, out) in best_files() {
            let cases = parse(&input);
            for (c, prog) in cases.iter().zip(programs(&out)).step_by(7) {
                for s in sym::ALL {
                    let p2 = s.pattern(&c.pattern);
                    assert_eq!(p2.cells.len(), c.pattern.cells.len());
                    let lines: Vec<[u8; 6]> = prog.iter().map(|&a| unpack(s.forward(a))).collect();
                    assert!(count_accepted(&p2, &lines) >= c.count, "{s:?}");
                }
            }
        }
    }

    /// The bitset simulator agrees with model.rs on every best program, after every line.
    #[test]
    fn simulator_matches_model() {
        let mut checked = 0;
        for (input, out) in best_files() {
            let cases = parse(&input);
            for (c, prog) in cases.iter().zip(programs(&out)) {
                let geo = Geo::new(&c.pattern);
                let lines: Vec<[u8; 6]> = prog.iter().map(|&a| unpack(a)).collect();
                let mut s = State::start(&geo);
                for (i, &a) in prog.iter().enumerate() {
                    s = sim::step_any(&geo, &s, a);
                    if i % 5 == 0 || i + 1 == prog.len() {
                        assert_eq!(s.subs as usize, count_accepted(&c.pattern, &lines[..=i]));
                    }
                }
                assert!(s.subs as usize >= c.count);
                checked += 1;
            }
        }
        eprintln!("{checked} programs checked");
    }

    /// Benchmark (not a test): `L6_BENCH="2-medium:0,3-large:5" L6_BENCH_W=800 cargo test --release
    /// bench_beam -- --ignored --nocapture`. Also writes each case in beam5.c's input format to
    /// `$L6_BENCH_DUMP/<file>_<case>.txt` (if set) for a comparison at equal width.
    #[test]
    #[ignore]
    fn bench_beam() {
        let spec = std::env::var("L6_BENCH").unwrap_or("2-medium:0".into());
        let width: usize = std::env::var("L6_BENCH_W").ok().and_then(|v| v.parse().ok()).unwrap_or(800);
        let dump = std::env::var("L6_BENCH_DUMP").ok();
        for item in spec.split(',') {
            let (file, idx) = item.split_once(':').unwrap();
            let idx: usize = idx.parse().unwrap();
            let input =
                std::fs::read_to_string(Path::new(ROOT).join(format!("work/level6/in/in_level-6_{file}.txt"))).unwrap();
            let c = &parse(&input)[idx];
            let geo = Geo::new(&c.pattern);
            if let Some(d) = &dump {
                let bits = |m: &geo::Bits| -> String {
                    (0..geo::MAXW * 64).filter(|&i| m[i / 64] >> (i % 64) & 1 == 1).map(|i| i.to_string()).collect::<Vec<_>>().join(" ")
                };
                let nrel = c.pattern.cells.len() + c.pattern.skirting.len();
                let mut txt = format!("{} {} {}\n{}\n{}\n", geo.r, c.count, nrel, bits(&geo.pat), bits(&geo.halo));
                for k in 0..6 {
                    for o in 0..=2 * geo.r {
                        txt += &format!("{}\n", bits(geo.beam(k, geo.pos_at(k, o))));
                    }
                }
                std::fs::write(format!("{d}/{file}_{idx}.txt"), txt).unwrap();
            }
            let prm = beam::Params { width, ..Default::default() };
            let t0 = std::time::Instant::now();
            let (prog, st) = beam::search(&geo, &State::start(&geo), c.count, 999, &prm, 0, &|| false);
            let secs = t0.elapsed().as_secs_f64();
            let fp = prog.as_ref().map_or(0, |p| p.iter().fold(0u64, |h, &a| opt::mix(h ^ a as u64)));
            println!(
                "{file}:{idx} R={} cells={} count={} W={width}: {} lines ({fp:016x}), {secs:.3} s, {} ticks, {:.1} M nominal children/s, scored {:.0}%, leaves {:.0}%",
                geo.r,
                geo.npat,
                c.count,
                prog.map_or(0, |p| p.len()),
                st.ticks,
                st.nominal as f64 / secs / 1e6,
                100.0 * st.children as f64 / st.nominal as f64,
                100.0 * st.leaves as f64 / st.nominal as f64,
            );
        }
    }

    /// Quality benchmark (not a test): total lines of from-scratch attempts over every `step`-th
    /// case of each real input, for seeds `0..L6_QUAL_SEEDS`, at width `L6_QUAL_W`:
    /// `L6_QUAL_W=800 cargo test --release quality -- --ignored --nocapture`.
    #[test]
    #[ignore]
    fn quality() {
        let width: usize = std::env::var("L6_QUAL_W").ok().and_then(|v| v.parse().ok()).unwrap_or(800);
        let seeds: u64 = std::env::var("L6_QUAL_SEEDS").ok().and_then(|v| v.parse().ok()).unwrap_or(2);
        let step: usize = std::env::var("L6_QUAL_STEP").ok().and_then(|v| v.parse().ok()).unwrap_or(19);
        let mut items = Vec::new();
        for file in ["2-medium", "3-large", "4-enormous"] {
            let input =
                std::fs::read_to_string(Path::new(ROOT).join(format!("work/level6/in/in_level-6_{file}.txt"))).unwrap();
            for (i, c) in parse(&input).into_iter().enumerate().filter(|(i, _)| i % step == 0) {
                for seed in 0..seeds {
                    items.push((file, i, c.count, Geo::new(&c.pattern), seed));
                }
            }
        }
        let t0 = std::time::Instant::now();
        let res = harness::par::map_threads(8, &items, |(_, _, count, geo, seed)| {
            let prm = beam::Params { width, ..Default::default() };
            let t = std::time::Instant::now();
            let (prog, st) = beam::search(geo, &State::start(geo), *count, 999, &prm, *seed, &|| false);
            (prog.map_or(999, |p| p.len()), t.elapsed().as_secs_f64(), st.nominal)
        });
        for file in ["2-medium", "3-large", "4-enormous"] {
            let sel: Vec<_> = items.iter().zip(&res).filter(|(it, _)| it.0 == file).map(|(_, r)| r).collect();
            let lines: usize = sel.iter().map(|r| r.0).sum();
            let secs: f64 = sel.iter().map(|r| r.1).sum();
            println!("{file}: {} runs, {lines} lines, {secs:.1} cpu-s", sel.len());
        }
        let lines: usize = res.iter().map(|r| r.0).sum();
        let secs: f64 = res.iter().map(|r| r.1).sum();
        let nominal: u64 = res.iter().map(|r| r.2).sum();
        println!(
            "TOTAL W={width}: {lines} lines, {secs:.1} cpu-s ({:.1} s wall), {:.0} M nominal children/cpu-s",
            t0.elapsed().as_secs_f64(),
            nominal as f64 / secs / 1e6
        );
    }

    #[test]
    fn beam_solves_example() {
        let input = std::fs::read_to_string(Path::new(ROOT).join("work/level6/in/in_level-6_0-example.txt")).unwrap();
        for c in parse(&input) {
            let geo = Geo::new(&c.pattern);
            let (prog, _) =
                beam::search(&geo, &State::start(&geo), c.count, 200, &beam::Params::default(), 1, &|| false);
            let prog = prog.expect("beam finds a program");
            let lines: Vec<[u8; 6]> = prog.iter().map(|&a| unpack(a)).collect();
            assert!(count_accepted(&c.pattern, &lines) >= c.count);
        }
    }
}
