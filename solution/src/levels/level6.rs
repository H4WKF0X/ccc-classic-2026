use crate::model::{count_accepted, empty_board, parse_instr, Board, Pattern, Rig};
use std::collections::VecDeque;

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
            Case { pattern: Pattern::new(Board { r, grid }), count }
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

const NONE: u32 = u32::MAX;

/// Static geometry of a board: ring, cell classes, and every emitter's beam per ring position.
struct Geo {
    n: usize,
    cols: usize,
    /// 0 = free (far from the pattern), 1 = pattern, 2 = skirting.
    class: Vec<u8>,
    /// beams[e][p] = flat cell indices hit by emitter `e` at ring position `p`.
    beams: Vec<Vec<Vec<u32>>>,
    start: [usize; 6],
}

impl Geo {
    fn new(pat: &Pattern) -> Geo {
        let r = pat.board.r;
        let b = empty_board(r);
        let rig = Rig::new(r);
        let cols = b.cols();
        let mut class = vec![0u8; b.rows() * cols];
        for &(y, x) in &pat.cells {
            class[y * cols + x] = 1;
        }
        for &(y, x) in &pat.skirting {
            class[y * cols + x] = 2;
        }
        let beams = (0..6)
            .map(|e| {
                rig.ring
                    .iter()
                    .map(|&(y, x)| {
                        b.beam_cells(y, x, e as u8 + 1)
                            .into_iter()
                            .map(|(cy, cx)| (cy * cols + cx) as u32)
                            .collect()
                    })
                    .collect()
            })
            .collect();
        Geo { n: rig.ring.len(), cols, class, beams, start: rig.pos }
    }
}

const ACTIONS: [u8; 4] = [b'-', b'F', b'B', b'T'];

fn step_pos(n: usize, p: usize, a: u8) -> usize {
    match a {
        b'F' => (p + 1) % n,
        b'B' => (p + n - 1) % n,
        _ => p,
    }
}

/// Baseline: two emitters of different families as a "pen" whose beam intersection walks over
/// the pattern, never marking a skirting cell.
fn pen(geo: &Geo, ea: usize, eb: usize, count: usize) -> Option<Vec<[u8; 6]>> {
    let n = geo.n;
    let mut inter = vec![NONE; n * n];
    for pa in 0..n {
        for pb in 0..n {
            let a = &geo.beams[ea][pa];
            if let Some(&c) = a.iter().find(|c| geo.beams[eb][pb].contains(c)) {
                inter[pa * n + pb] = c;
            }
        }
    }
    let total = geo.class.iter().filter(|&&c| c == 1).count();
    let enc = |pa: usize, pb: usize, aa: bool, ab: bool| ((pa * n + pb) * 2 + aa as usize) * 2 + ab as usize;
    let mark = |s: usize| -> u32 {
        let (ab, aa, pab) = (s & 1 == 1, (s >> 1) & 1 == 1, s >> 2);
        if aa && ab {
            inter[pab]
        } else {
            NONE
        }
    };
    let mut marked = vec![false; geo.class.len()];
    let mut done = 0;
    let mut copies = 0;
    let mut cur = enc(geo.start[ea], geo.start[eb], false, false);
    let mut prog: Vec<[u8; 6]> = Vec::new();
    let ns = n * n * 4;
    let mut prev = vec![(usize::MAX, 0u8, 0u8); ns];
    let mut seen = vec![0u32; ns];
    let mut stamp = 0u32;
    while copies < count {
        // BFS to the nearest state that marks an unmarked pattern cell.
        stamp += 1;
        let mut q = VecDeque::new();
        seen[cur] = stamp;
        q.push_back(cur);
        let mut goal = None;
        'bfs: while let Some(s) = q.pop_front() {
            let (ab, aa, pab) = (s & 1 == 1, (s >> 1) & 1 == 1, s >> 2);
            let (pa, pb) = (pab / n, pab % n);
            for &xa in &ACTIONS {
                for &xb in &ACTIONS {
                    let t = enc(
                        step_pos(n, pa, xa),
                        step_pos(n, pb, xb),
                        aa ^ (xa == b'T'),
                        ab ^ (xb == b'T'),
                    );
                    if seen[t] == stamp {
                        continue;
                    }
                    let m = mark(t);
                    if m != NONE && geo.class[m as usize] == 2 {
                        continue;
                    }
                    seen[t] = stamp;
                    prev[t] = (s, xa, xb);
                    if m != NONE && geo.class[m as usize] == 1 && !marked[m as usize] {
                        goal = Some(t);
                        break 'bfs;
                    }
                    q.push_back(t);
                }
            }
        }
        let goal = goal?;
        let mut path = Vec::new();
        let mut s = goal;
        while s != cur {
            let (p, xa, xb) = prev[s];
            path.push((s, xa, xb));
            s = p;
        }
        for &(s, xa, xb) in path.iter().rev() {
            let mut line = [b'-'; 6];
            line[ea] = xa;
            line[eb] = xb;
            prog.push(line);
            let m = mark(s);
            if m != NONE && geo.class[m as usize] == 1 && !marked[m as usize] {
                marked[m as usize] = true;
                done += 1;
                if done == total {
                    copies += 1;
                    done = 0;
                    marked.iter_mut().for_each(|x| *x = false);
                }
            }
        }
        cur = goal;
    }
    let _ = geo.cols;
    Some(prog)
}

fn solve_case(c: &Case) -> Vec<[u8; 6]> {
    let geo = Geo::new(&c.pattern);
    let mut best: Option<Vec<[u8; 6]>> = None;
    let t0 = std::time::Instant::now();
    for f in 0..3 {
        let sw = Sweep::new(&geo, &c.pattern, f);
        for from_max in [false, true] {
            if let Some(p) = sw.search(c.count, from_max, beam_width()) {
                if best.as_ref().map_or(true, |b| p.len() < b.len()) {
                    best = Some(p);
                }
            }
        }
    }
    let sweep_len = best.as_ref().map_or(0, |b| b.len());
    let t1 = t0.elapsed().as_secs_f64();
    let pen_best = best_pen(&geo, c.count);
    harness::trace!("r={} m={} K={} sweep={} ({:.1}s) pen={}", c.pattern.board.r, c.pattern.cells.len(), c.count, sweep_len, t1, pen_best.len());
    if best.as_ref().map_or(true, |b| pen_best.len() < b.len()) {
        best = Some(pen_best);
    }
    best.unwrap()
}

fn best_pen(geo: &Geo, count: usize) -> Vec<[u8; 6]> {
    let mut best: Option<Vec<[u8; 6]>> = None;
    for ea in 0..6 {
        for eb in ea + 1..6 {
            if ea % 3 == eb % 3 {
                continue;
            }
            if let Some(p) = pen(geo, ea, eb, count) {
                if best.as_ref().map_or(true, |b| p.len() < b.len()) {
                    best = Some(p);
                }
            }
        }
    }
    best.expect("no pen pair works")
}

pub fn solve(input: &str) -> Vec<String> {
    let cases = parse(input);
    let prm = zip_beam::Params::from_env();
    let done = std::sync::atomic::AtomicUsize::new(0);
    let t0 = std::time::Instant::now();
    let progs = harness::par::map(&cases, |c| {
        let prog = zip_beam::solve_case(c, &prm).filter(|p| count_accepted(&c.pattern, p) >= c.count);
        let prog = prog.unwrap_or_else(|| solve_case(c));
        let k = done.fetch_add(1, std::sync::atomic::Ordering::Relaxed) + 1;
        harness::trace!(
            "progress n={} {k}/{} r={} cells={} count={} -> {} lines ({:.0}s)",
            cases.len(), cases.len(), c.pattern.board.r, c.pattern.cells.len(), c.count, prog.len(),
            t0.elapsed().as_secs_f64()
        );
        prog
    });
    let mut out = Vec::new();
    for p in progs {
        for line in p {
            let toks: Vec<String> = line.iter().map(|&c| (c as char).to_string()).collect();
            out.push(toks.join(" "));
        }
        out.push(String::new());
    }
    out
}

fn beam_width() -> usize {
    std::env::var("L6_W").ok().and_then(|v| v.parse().ok()).unwrap_or(60)
}

/// Line key of grid cell `(y, x)` in family `f` (0 rows, 1 SE diagonals, 2 SW diagonals);
/// adjacent lines differ by 1.
fn line_key(r: usize, f: usize, y: usize, x: usize) -> i32 {
    let (y, x, r) = (y as i32, x as i32, r as i32);
    match f {
        0 => y,
        1 => (x - y - r) / 2,
        _ => (x + y - r) / 2,
    }
}

const NOLINE: i32 = i32::MIN;
const WORDS: usize = 8;

/// Line sweep: emitters `f` and `f+3` sit on the same line of family `f`, so the whole line gets
/// two hits and becomes matter; the other four emitters ("killers") put a third beam on the
/// skirting cells of that line. A beam search plans all moves with the exact matter rules.
struct Sweep {
    n: usize,
    np: usize,
    nrel: usize,
    /// rbeam[e][p] = relevant (pattern or skirting) cells, compact indices, on that beam.
    rbeam: Vec<Vec<Vec<u16>>>,
    /// Line key (family `f`) of each relevant cell.
    key: Vec<i32>,
    /// For the two D emitters: line key per ring position.
    dline: [Vec<i32>; 2],
    dpos: [std::collections::BTreeMap<i32, usize>; 2],
    de: [usize; 2],
    lmin: i32,
    lmax: i32,
    start: [usize; 6],
    /// distc[e][p * np + c] = ring steps for emitter `e` from `p` until its beam covers pattern cell `c`.
    distc: Vec<Vec<u8>>,
}

#[derive(Clone)]
struct Node {
    pos: [u8; 6],
    act: u8,
    bits: [u64; WORDS],
    made: u16,
    copies: u16,
    parent: u32,
    line: [u8; 6],
}

fn ring_dist(n: usize, a: usize, b: usize) -> usize {
    let d = (a + n - b) % n;
    d.min(n - d)
}

impl Sweep {
    fn new(geo: &Geo, pat: &Pattern, f: usize) -> Sweep {
        let r = pat.board.r;
        let cols = geo.cols;
        let mut compact = vec![u16::MAX; geo.class.len()];
        let mut key = Vec::new();
        let mut np = 0;
        for cls in [1u8, 2] {
            for (i, &c) in geo.class.iter().enumerate() {
                if c == cls {
                    compact[i] = key.len() as u16;
                    key.push(line_key(r, f, i / cols, i % cols));
                    if cls == 1 {
                        np += 1;
                    }
                }
            }
        }
        assert!(np <= WORDS * 64);
        let rbeam: Vec<Vec<Vec<u16>>> = geo
            .beams
            .iter()
            .map(|pe| {
                pe.iter()
                    .map(|cells| cells.iter().map(|&c| compact[c as usize]).filter(|&c| c != u16::MAX).collect())
                    .collect()
            })
            .collect();
        let de = [f, f + 3];
        let dline: [Vec<i32>; 2] = std::array::from_fn(|i| {
            geo.beams[de[i]]
                .iter()
                .map(|cells| match cells.first() {
                    Some(&c) => line_key(r, f, c as usize / cols, c as usize % cols),
                    None => NOLINE,
                })
                .collect()
        });
        let dpos = std::array::from_fn(|i| {
            let mut m = std::collections::BTreeMap::new();
            for (p, &l) in dline[i].iter().enumerate() {
                if l != NOLINE {
                    m.insert(l, p);
                }
            }
            m
        });
        let lmin = key[..np].iter().copied().min().unwrap();
        let lmax = key[..np].iter().copied().max().unwrap();
        let n = geo.n;
        let distc = (0..6)
            .map(|e| {
                let mut d = vec![u8::MAX; n * np];
                for (q, cells) in rbeam[e].iter().enumerate() {
                    for &c in cells {
                        let c = c as usize;
                        if c >= np {
                            continue;
                        }
                        for p in 0..n {
                            let v = ring_dist(n, p, q) as u8;
                            if v < d[p * np + c] {
                                d[p * np + c] = v;
                            }
                        }
                    }
                }
                d
            })
            .collect();
        Sweep { n, np, nrel: key.len(), rbeam, key, dline, dpos, de, lmin, lmax, start: geo.start, distc }
    }

    fn is_d(&self, e: usize) -> bool {
        e == self.de[0] || e == self.de[1]
    }

    /// D line if both D emitters are active on the same line.
    fn d_line(&self, pos: &[u8; 6], act: u8) -> Option<i32> {
        let [a, b] = self.de;
        if act >> a & 1 == 1 && act >> b & 1 == 1 {
            let la = self.dline[0][pos[a] as usize];
            if la != NOLINE && la == self.dline[1][pos[b] as usize] {
                return Some(la);
            }
        }
        None
    }

    /// Applies one tick's beams to `bits`. None if a skirting cell would get matter.
    fn apply(&self, pos: &[u8; 6], act: u8, bits: &mut [u64; WORDS], cnt: &mut [u8], touched: &mut Vec<u16>) -> bool {
        touched.clear();
        for e in 0..6 {
            if act >> e & 1 == 1 {
                for &c in &self.rbeam[e][pos[e] as usize] {
                    if cnt[c as usize] == 0 {
                        touched.push(c);
                    }
                    cnt[c as usize] += 1;
                }
            }
        }
        let mut ok = true;
        for &c in touched.iter() {
            let k = cnt[c as usize];
            cnt[c as usize] = 0;
            let c = c as usize;
            if c >= self.np {
                if k == 2 {
                    ok = false;
                }
            } else if k == 2 {
                bits[c / 64] |= 1 << (c % 64);
            } else if k >= 3 {
                bits[c / 64] &= !(1 << (c % 64));
            }
        }
        ok
    }

    /// Ranking penalty: how badly the killers fit the next useful line.
    fn badness(&self, nd: &Node, l0: i32, cnt: &mut [u8], touched: &mut Vec<u16>) -> u32 {
        let [a, b] = self.de;
        let both = nd.act >> a & 1 == 1 && nd.act >> b & 1 == 1;
        let cands: Vec<i32> = match both {
            false => vec![l0],
            true => {
                let la = self.dline[0][nd.pos[a] as usize];
                let lb = self.dline[1][nd.pos[b] as usize];
                let unmade = |line: i32| {
                    (0..self.np).any(|c| self.key[c] == line && nd.bits[c / 64] >> (c % 64) & 1 == 0)
                };
                let mut v: Vec<i32> = [la, lb]
                    .into_iter()
                    .filter(|&l| l != NOLINE)
                    .flat_map(|l| [l - 1, l, l + 1])
                    .filter(|&x| x >= self.lmin && x <= self.lmax && unmade(x))
                    .collect();
                if v.is_empty() {
                    v.push(if la != NOLINE { la } else { lb });
                }
                v
            }
        };
        // cnt marks cells crossed by an active killer
        touched.clear();
        for e in 0..6 {
            if self.is_d(e) || nd.act >> e & 1 == 0 {
                continue;
            }
            for &c in &self.rbeam[e][nd.pos[e] as usize] {
                if cands.contains(&self.key[c as usize]) {
                    if cnt[c as usize] == 0 {
                        touched.push(c);
                    }
                    cnt[c as usize] += 1;
                }
            }
        }
        let mut best = u32::MAX;
        for &l in &cands {
            let mut bad = 0;
            for c in 0..self.nrel {
                if self.key[c] != l {
                    continue;
                }
                let crossed = cnt[c] > 0;
                if c >= self.np && !crossed {
                    bad += 1;
                }
                if c < self.np && crossed {
                    bad += 1;
                }
            }
            best = best.min(bad);
        }
        for &c in touched.iter() {
            cnt[c as usize] = 0;
        }
        best
    }

    fn setup_left(&self, nd: &Node, l0: i32) -> u32 {
        let mut s = 0;
        for i in 0..2 {
            let e = self.de[i];
            if nd.act >> e & 1 == 1 {
                continue;
            }
            s += ring_dist(self.n, nd.pos[e] as usize, self.dpos[i][&l0]) as u32 + 1;
        }
        s
    }

    /// Candidate instruction pairs for the two D emitters.
    fn d_options(&self, nd: &Node, l0: i32, free: bool) -> Vec<(u8, u8)> {
        let all = || {
            let mut v = Vec::new();
            for &x in &ACTIONS {
                for &y in &ACTIONS {
                    v.push((x, y));
                }
            }
            v
        };
        if free {
            return all();
        }
        let n = self.n;
        let toward = |_i: usize, p: usize, target: usize| -> u8 {
            if p == target {
                b'-'
            } else if (target + n - p) % n <= n / 2 {
                b'F'
            } else {
                b'B'
            }
        };
        let [a, b] = self.de;
        if nd.act >> a & 1 == 1 && nd.act >> b & 1 == 1 {
            let mut per: [Vec<u8>; 2] = [vec![b'-'], vec![b'-']];
            let cur = [self.dline[0][nd.pos[a] as usize], self.dline[1][nd.pos[b] as usize]];
            if cur.contains(&NOLINE) {
                return all();
            }
            for i in 0..2 {
                let p = nd.pos[self.de[i]] as usize;
                for (act, np) in [(b'F', (p + 1) % n), (b'B', (p + n - 1) % n)] {
                    let nl = self.dline[i][np];
                    if nl != NOLINE && nl >= self.lmin && nl <= self.lmax && (nl - cur[1 - i]).abs() <= 2 {
                        per[i].push(act);
                    }
                }
            }
            let mut v = Vec::new();
            for &x in &per[0] {
                for &y in &per[1] {
                    v.push((x, y));
                }
            }
            return v;
        }
        let mut per: [Vec<u8>; 2] = [vec![b'-'], vec![b'-']];
        for i in 0..2 {
            let e = self.de[i];
            let p = nd.pos[e] as usize;
            let target = self.dpos[i][&l0];
            if nd.act >> e & 1 == 1 {
                continue;
            }
            if p == target {
                per[i].push(b'T');
            } else {
                per[i].push(toward(i, p, target));
            }
        }
        let mut v = Vec::new();
        for &a in &per[0] {
            for &b in &per[1] {
                v.push((a, b));
            }
        }
        v
    }

    /// Ticks until two emitters could cross on some unmade pattern cell (ignoring skirting).
    fn finish_dist(&self, nd: &Node) -> u32 {
        let mut best = u32::MAX;
        for c in 0..self.np {
            if nd.bits[c / 64] >> (c % 64) & 1 == 1 {
                continue;
            }
            let (mut m1, mut m2) = (u32::MAX, u32::MAX);
            for e in 0..6 {
                let d = self.distc[e][nd.pos[e] as usize * self.np + c];
                if d == u8::MAX {
                    continue;
                }
                let v = d as u32 + (nd.act >> e & 1 == 0) as u32;
                if v < m1 {
                    m2 = m1;
                    m1 = v;
                } else if v < m2 {
                    m2 = v;
                }
            }
            best = best.min(m2);
        }
        if best == u32::MAX { 0 } else { best }
    }

    fn search(&self, count: usize, from_max: bool, width: usize) -> Option<Vec<[u8; 6]>> {
        let l0 = if from_max { self.lmax } else { self.lmin };
        if !self.dpos[0].contains_key(&l0) || !self.dpos[1].contains_key(&l0) {
            return None;
        }
        let n = self.n;
        let killers: Vec<usize> = (0..6).filter(|&e| !self.is_d(e)).collect();
        let mut cnt = vec![0u8; self.nrel];
        let mut touched = Vec::new();
        let root = Node {
            pos: std::array::from_fn(|e| self.start[e] as u8),
            act: 0,
            bits: [0; WORDS],
            made: 0,
            copies: 0,
            parent: u32::MAX,
            line: [b'-'; 6],
        };
        let mut layers: Vec<Vec<Node>> = vec![vec![root]];
        let max_ticks = 60 + count * (self.np + 10);
        let (mut best_prog, mut best_at) = (0i64, 0usize);
        let patience = 4 * self.n / 6 + 12;
        while layers.len() <= max_ticks {
            if layers.len() - best_at > patience {
                harness::trace!("  abort f? from_max={from_max} tick={} best={} of {}", layers.len(), best_prog, self.np * count);
                return None;
            }
            if harness::budget::expired() {
                return None;
            }
            let cur = layers.last().unwrap();
            let stalled = best_prog > 0 && layers.len() - best_at >= 3;
            let free_all = std::env::var("L6_FREE").is_ok() && best_prog > 0;
            let mut cands: Vec<(u64, Node)> = Vec::new();
            let mut seen = std::collections::HashSet::new();
            for (pi, nd) in cur.iter().enumerate() {
                for (da, db) in self.d_options(nd, l0, free_all || stalled || (best_prog > 0 && nd.act >> self.de[0] & 1 == 0) || (best_prog > 0 && nd.act >> self.de[1] & 1 == 0)) {
                    for combo in 0..256usize {
                        let mut line = [b'-'; 6];
                        line[self.de[0]] = da;
                        line[self.de[1]] = db;
                        for (k, &e) in killers.iter().enumerate() {
                            line[e] = ACTIONS[(combo >> (2 * k)) & 3];
                        }
                        let mut pos = nd.pos;
                        let mut act = nd.act;
                        for e in 0..6 {
                            match line[e] {
                                b'T' => act ^= 1 << e,
                                a => pos[e] = step_pos(n, pos[e] as usize, a) as u8,
                            }
                        }
                        let mut bits = nd.bits;
                        if !self.apply(&pos, act, &mut bits, &mut cnt, &mut touched) {
                            continue;
                        }
                        let mut made: u32 = bits.iter().map(|w| w.count_ones()).sum();
                        let mut copies = nd.copies;
                        if made as usize == self.np {
                            copies += 1;
                            made = 0;
                            bits = [0; WORDS];
                        }
                        let mut h: u64 = 0xcbf29ce484222325;
                        for &x in pos.iter().chain([act].iter()) {
                            h = (h ^ x as u64).wrapping_mul(0x100000001b3);
                        }
                        for &w in &bits {
                            h = (h ^ w).wrapping_mul(0x100000001b3);
                        }
                        h = (h ^ copies as u64).wrapping_mul(0x100000001b3);
                        if !seen.insert(h) {
                            continue;
                        }
                        let child = Node { pos, act, bits, made: made as u16, copies, parent: pi as u32, line };
                        if copies as usize >= count {
                            let mut prog = vec![line];
                            let mut p = pi;
                            for layer in layers.iter().rev() {
                                let nd = &layer[p];
                                if nd.parent == u32::MAX {
                                    break;
                                }
                                prog.push(nd.line);
                                p = nd.parent as usize;
                            }
                            prog.reverse();
                            if std::env::var("L6_TRACE").is_ok() {
                                let mut path = vec![];
                                let mut p = pi;
                                for layer in layers.iter().rev() {
                                    let nd = &layer[p];
                                    path.push((nd.pos, nd.act, nd.made, nd.copies));
                                    if nd.parent == u32::MAX { break; }
                                    p = nd.parent as usize;
                                }
                                path.reverse();
                                let f = self.de[0];
                                for (t, (pos, act, made, copies)) in path.iter().enumerate() {
                                    let la = self.dline[0][pos[self.de[0]] as usize];
                                    let lb = self.dline[1][pos[self.de[1]] as usize];
                                    eprintln!("f={f} t={t} D=({la},{lb}) act={act:06b} made={made} copies={copies}");
                                }
                            }
                            return Some(prog);
                        }
                        cands.push((h, child));
                    }
                }
            }
            if cands.is_empty() {
                harness::trace!("  dead from_max={from_max} tick={} best={} of {}", layers.len(), best_prog, self.np * count);
                return None;
            }
            // rank: progress desc, setup left asc, badness asc, hash
            let mut keyed: Vec<(i64, u32, u32, u32, u64, usize)> = cands
                .iter()
                .enumerate()
                .map(|(i, (h, c))| {
                    let prog = c.copies as i64 * self.np as i64 + c.made as i64;
                    let sl = if best_prog > 0 { 0 } else { self.setup_left(c, l0) };
                    (-prog, sl, 0, 0, *h, i)
                })
                .collect();
            // badness only for the plausible top part
            keyed.sort_unstable();
            if -keyed[0].0 > best_prog {
                best_prog = -keyed[0].0;
                best_at = layers.len();
            }
            let keep = (width * 8).min(keyed.len());
            for k in keyed[..keep].iter_mut() {
                let nd = &cands[k.5].1;
                let bad = self.badness(nd, l0, &mut cnt, &mut touched);
                let fin = self.finish_dist(nd);
                (k.2, k.3) = if stalled { (fin, bad) } else { (bad, fin) };
            }
            keyed.truncate(keep);
            keyed.sort_unstable();
            keyed.truncate(width);
            let mut taken: Vec<Option<Node>> = cands.into_iter().map(|(_, c)| Some(c)).collect();
            layers.push(keyed.iter().map(|k| taken[k.5].take().unwrap()).collect());
        }
        None
    }
}

/// Port of the teammate's C++ beam search (Archive.zip, beam.cpp): per tick, every beam state tries
/// all 4^6 instruction combinations; moves that put matter on skirting are discarded; states are
/// ranked by completed copies, then unmade pattern cells and the ring distance the emitters still
/// need to reach a crossing for each unmade cell.
mod zip_beam {
    use super::Case;
    use crate::model::Rig;
    use std::collections::{BTreeMap, HashSet};

    const WORDS: usize = 8;
    type Bits = [u64; WORDS];

    pub struct Params {
        pub width: usize,
        /// Weights scaled by 1000 (C++ defaults: Wu = 3, Wc = 1).
        pub wu: i64,
        pub wc: i64,
        /// 0: never put matter on skirting (original). >0: allow it temporarily, penalised by
        /// this weight (x1000) per polluted skirting cell; detection still needs clean skirting.
        pub wk: i64,
        pub max_ticks: usize,
        /// Give up on a case after this many seconds (the caller falls back to another solver).
        pub max_secs: f64,
        /// 1: zip scoring (distance heuristic, skirting forbidden unless wk > 0).
        /// 2: friend's newer beam.py scoring (skirting allowed, penalised; beam-cover tie-break).
        pub mode: u8,
    }

    impl Params {
        pub fn from_env() -> Params {
            let get = |k: &str, d: f64| std::env::var(k).ok().and_then(|v| v.parse().ok()).unwrap_or(d);
            Params {
                width: get("L6_ZW", 100.0) as usize,
                wu: (get("L6_WU", 3.0) * 1000.0) as i64,
                wc: (get("L6_WC", 1.0) * 1000.0) as i64,
                wk: (get("L6_SKIRT", 0.0) * 1000.0) as i64,
                max_ticks: 100_000,
                max_secs: get("L6_TMAX", 60.0),
                mode: get("L6_MODE", 1.0) as u8,
            }
        }
    }

    #[derive(Clone, Copy, PartialEq, Eq, Hash)]
    struct State {
        idx: [u8; 6],
        act: u8,
        acc: u32,
        m: Bits,
    }

    struct Solver {
        p: usize,
        nwords: usize,
        n_s: usize,
        smask: Bits,
        kmask: Bits,
        /// ray[i * 6 + t]: universe cells hit by emitter t at ring position i.
        ray: Vec<Bits>,
        /// cost[(t * p + i) * 2 + active][s]: ring distance of emitter t at i to a position whose
        /// beam covers pattern cell s, plus 1 when it still has to be switched on.
        cost: Vec<Vec<u8>>,
        start: [usize; 6],
    }

    fn bit(b: &Bits, i: usize) -> bool {
        b[i >> 6] >> (i & 63) & 1 == 1
    }

    impl Solver {
        fn new(c: &Case) -> Option<Solver> {
            let pat = &c.pattern;
            let n_s = pat.cells.len();
            let n_u = n_s + pat.skirting.len();
            if n_s == 0 || n_u > WORDS * 64 {
                return None;
            }
            let nwords = n_u.div_ceil(64);
            let mut uid = BTreeMap::new();
            for (i, &cell) in pat.cells.iter().chain(&pat.skirting).enumerate() {
                uid.insert(cell, i);
            }
            let mut smask = [0u64; WORDS];
            let mut kmask = [0u64; WORDS];
            for i in 0..n_u {
                if i < n_s {
                    smask[i >> 6] |= 1 << (i & 63);
                } else {
                    kmask[i >> 6] |= 1 << (i & 63);
                }
            }
            let rig = Rig::new(pat.board.r);
            let p = rig.ring.len();
            let mut ray = vec![[0u64; WORDS]; p * 6];
            for (i, &(y, x)) in rig.ring.iter().enumerate() {
                for t in 0..6 {
                    for cell in pat.board.beam_cells(y, x, t as u8 + 1) {
                        if let Some(&u) = uid.get(&cell) {
                            ray[i * 6 + t][u >> 6] |= 1 << (u & 63);
                        }
                    }
                }
            }
            let mut cost = vec![vec![200u8; n_s]; 6 * p * 2];
            for t in 0..6 {
                for s in 0..n_s {
                    let Some(pos) = (0..p).find(|&i| bit(&ray[i * 6 + t], s)) else { continue };
                    for i in 0..p {
                        let d = i.abs_diff(pos);
                        let d = d.min(p - d) as u8;
                        cost[(t * p + i) * 2 + 1][s] = d;
                        cost[(t * p + i) * 2][s] = d + 1;
                    }
                }
            }
            Some(Solver { p, nwords, n_s, smask, kmask, ray, cost, start: rig.pos })
        }

        /// Next state and score for `action` (2 bits per emitter: 0 '-', 1 'T', 2 'F', 3 'B'),
        /// or None if it puts matter on skirting.
        fn apply(&self, s: &State, action: usize, prm: &Params, best: &mut [u8]) -> Option<(State, i64)> {
            let mut o = *s;
            let (mut c1, mut c2, mut c3) = ([0u64; WORDS], [0u64; WORDS], [0u64; WORDS]);
            for t in 0..6 {
                let mut ii = s.idx[t] as usize;
                let mut ac = s.act >> t & 1;
                match action >> (2 * t) & 3 {
                    1 => ac ^= 1,
                    2 => ii = (ii + 1) % self.p,
                    3 => ii = (ii + self.p - 1) % self.p,
                    _ => {}
                }
                o.idx[t] = ii as u8;
                o.act = (o.act & !(1 << t)) | (ac << t);
                if ac == 1 {
                    let m = &self.ray[ii * 6 + t];
                    for w in 0..self.nwords {
                        c3[w] |= c2[w] & m[w];
                        c2[w] |= c1[w] & m[w];
                        c1[w] |= m[w];
                    }
                }
            }
            let mut full = true;
            let mut m2 = [0u64; WORDS];
            let mut polluted = 0i64;
            for w in 0..self.nwords {
                let two = c2[w] & !c3[w];
                if prm.mode == 1 && prm.wk == 0 && two & self.kmask[w] != 0 {
                    return None;
                }
                m2[w] = ((s.m[w] & !c3[w]) | two) & (self.smask[w] | self.kmask[w]);
                if m2[w] & self.smask[w] != self.smask[w] || m2[w] & self.kmask[w] != 0 {
                    full = false;
                }
                polluted += (m2[w] & self.kmask[w]).count_ones() as i64;
            }
            if full {
                o.acc += 1;
                m2 = [0u64; WORDS];
            }
            o.m = m2;
            if prm.mode == 2 {
                let n_s = self.n_s as i64;
                let mut missing = 0i64;
                let mut cover = 0i64;
                for w in 0..self.nwords {
                    let miss = self.smask[w] & !m2[w];
                    missing += miss.count_ones() as i64;
                    cover += (c1[w] & miss).count_ones() as i64;
                }
                let present = if full { 0 } else { n_s - missing };
                let f = o.acc as i64 * (4 * n_s + 8) + 4 * present - 6 * polluted;
                return Some((o, f * 64 + cover.min(63)));
            }
            // Heuristic: per unmade cell, the cheapest pair of emitters on different axes.
            let a: [&[u8]; 6] = std::array::from_fn(|t| {
                self.cost[(t * self.p + o.idx[t] as usize) * 2 + (o.act >> t & 1) as usize].as_slice()
            });
            best.fill(u8::MAX);
            for x in 0..6 {
                for y in x + 1..6 {
                    if x % 3 == y % 3 {
                        continue;
                    }
                    for ((b, &u), &v) in best.iter_mut().zip(a[x]).zip(a[y]) {
                        *b = (*b).min(u.max(v));
                    }
                }
            }
            let mut unmade = 0i64;
            let mut cost = 0i64;
            for si in 0..self.n_s {
                if !bit(&m2, si) {
                    unmade += 1;
                    cost += best[si] as i64;
                }
            }
            let score = o.acc as i64 * 1_000_000_000_000 - (prm.wu * unmade + prm.wc * cost + prm.wk * polluted);
            Some((o, score))
        }

        fn solve(&self, count: usize, prm: &Params) -> Option<Vec<[u8; 6]>> {
            let init = State {
                idx: std::array::from_fn(|t| self.start[t] as u8),
                act: 0,
                acc: 0,
                m: [0u64; WORDS],
            };
            let mut beam = vec![init];
            let mut hist: Vec<Vec<(u32, u16)>> = Vec::new();
            let mut best = vec![0u8; self.n_s];
            let t0 = std::time::Instant::now();
            for tick in 0..prm.max_ticks {
                if t0.elapsed().as_secs_f64() > prm.max_secs {
                    harness::trace!("TIMEOUT after {tick} ticks ({} cells, count {count})", self.n_s);
                    return None;
                }
                // (score, parent, action); ties broken by (parent, action) for determinism.
                let mut cands: Vec<(i64, u32, u16)> = Vec::with_capacity(beam.len() * 4096);
                for (bi, st) in beam.iter().enumerate() {
                    for act in 0..4096usize {
                        if let Some((_, sc)) = self.apply(st, act, prm, &mut best) {
                            cands.push((sc, bi as u32, act as u16));
                        }
                    }
                }
                if cands.is_empty() {
                    return None;
                }
                let order = |x: &(i64, u32, u16), y: &(i64, u32, u16)| y.0.cmp(&x.0).then(x.1.cmp(&y.1)).then(x.2.cmp(&y.2));
                let keep = cands.len().min(prm.width * 3);
                if keep < cands.len() {
                    cands.select_nth_unstable_by(keep - 1, order);
                    cands.truncate(keep);
                }
                cands.sort_unstable_by(order);
                let mut next = Vec::with_capacity(prm.width);
                let mut h = Vec::with_capacity(prm.width);
                let mut seen = HashSet::new();
                for &(_, parent, act) in &cands {
                    if next.len() >= prm.width {
                        break;
                    }
                    let (ns, _) = self.apply(&beam[parent as usize], act as usize, prm, &mut best).unwrap();
                    if seen.insert(ns) {
                        next.push(ns);
                        h.push((parent, act));
                    }
                }
                hist.push(h);
                beam = next;
                if let Some(win) = beam.iter().position(|s| s.acc as usize >= count) {
                    let mut prog = vec![[b'-'; 6]; tick + 1];
                    let mut cur = win;
                    for tk in (0..=tick).rev() {
                        let (parent, act) = hist[tk][cur];
                        for t in 0..6 {
                            prog[tk][t] = b"-TFB"[(act as usize >> (2 * t)) & 3];
                        }
                        cur = parent as usize;
                    }
                    return Some(prog);
                }
            }
            None
        }
    }

    /// Program for one case, or None when the pattern is too big for the bitsets or the search dies.
    pub fn solve_case(c: &Case, prm: &Params) -> Option<Vec<[u8; 6]>> {
        Solver::new(c)?.solve(c.count, prm)
    }
}
