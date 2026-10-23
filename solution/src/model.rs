//! Parsing and data model shared between levels.
//!
//! Later levels reuse the input format and data model of earlier ones. When something recurs,
//! move it here (a struct with a `parse` function, a geometry helper, ...) and use it from every
//! level as `crate::model::...` instead of copying code between level files.
#![allow(dead_code)]

/// Hex board of radius `r` as character rows: row `i` (0..=2r) holds `2r+1-d` tokens
/// (`d = |i-r|`) joined by '-', padded by `d` dashes each side. `cell(i, j)` gives token `j`.
pub fn render_hex(r: usize, mut cell: impl FnMut(usize, usize) -> char) -> Vec<String> {
    (0..=2 * r)
        .map(|i| {
            let d = i.abs_diff(r);
            let k = 2 * r + 1 - d;
            let mut s = "-".repeat(d);
            for j in 0..k {
                if j > 0 {
                    s.push('-');
                }
                s.push(cell(i, j));
            }
            s.push_str(&"-".repeat(d));
            s
        })
        .collect()
}

/// Is token `j` of row `i` on the border of a radius-`r` board?
pub fn hex_is_border(r: usize, i: usize, j: usize) -> bool {
    let k = 2 * r + 1 - i.abs_diff(r);
    i == 0 || i == 2 * r || j == 0 || j == k - 1
}

/// A board as its character grid (rows of bytes, exactly as in the input).
#[derive(Clone, Debug)]
pub struct Board {
    pub r: usize,
    pub grid: Vec<Vec<u8>>,
}

impl Board {
    pub fn rows(&self) -> usize {
        self.grid.len()
    }
    pub fn cols(&self) -> usize {
        self.grid[0].len()
    }
    pub fn get(&self, y: i64, x: i64) -> Option<u8> {
        if y < 0 || x < 0 {
            return None;
        }
        self.grid.get(y as usize)?.get(x as usize).copied()
    }
    pub fn lines(&self) -> Vec<String> {
        self.grid.iter().map(|row| String::from_utf8(row.clone()).unwrap()).collect()
    }
    /// Positions `(y, x, digit)` of all emitters ('1'..='6').
    pub fn emitters(&self) -> Vec<(i64, i64, u8)> {
        let mut v = Vec::new();
        for (y, row) in self.grid.iter().enumerate() {
            for (x, &c) in row.iter().enumerate() {
                if c.is_ascii_digit() && c != b'0' {
                    v.push((y as i64, x as i64, c - b'0'));
                }
            }
        }
        v
    }
}

/// Grid step `(dy, dx)` for emitter direction 1..=6: → ↘ ↙ ← ↖ ↗.
pub fn dir_delta(d: u8) -> (i64, i64) {
    match d {
        1 => (0, 2),
        2 => (1, 1),
        3 => (1, -1),
        4 => (0, -2),
        5 => (-1, -1),
        6 => (-1, 1),
        _ => panic!("bad direction {d}"),
    }
}

/// Parses "N" then N times: "r rows cols" header + `rows` grid lines (blank lines between).
pub fn parse_boards(input: &str) -> Vec<Board> {
    let mut lines = input.lines().filter(|l| !l.trim().is_empty());
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    (0..n)
        .map(|_| {
            let h = harness::parse::ints(lines.next().unwrap());
            let (r, rows, cols) = (h[0] as usize, h[1] as usize, h[2] as usize);
            let grid: Vec<Vec<u8>> =
                (0..rows).map(|_| lines.next().unwrap().trim().as_bytes().to_vec()).collect();
            assert!(grid.iter().all(|g| g.len() == cols), "bad board width");
            Board { r, grid }
        })
        .collect()
}

impl Board {
    /// Cells `(y, x)` ('O' or 'M') on the straight beam from the emitter at `(y0, x0)` in direction `d`.
    pub fn beam_cells(&self, y0: i64, x0: i64, d: u8) -> Vec<(usize, usize)> {
        let (dy, dx) = dir_delta(d);
        let (mut y, mut x) = (y0 + dy, x0 + dx);
        let mut v = Vec::new();
        while let Some(c) = self.get(y, x) {
            if c == b'O' || c == b'M' {
                v.push((y as usize, x as usize));
            }
            y += dy;
            x += dx;
        }
        v
    }

    /// Number of beams hitting each grid position, over all emitters.
    pub fn beam_counts(&self) -> Vec<Vec<u32>> {
        let mut cnt = vec![vec![0u32; self.cols()]; self.rows()];
        for (y, x, d) in self.emitters() {
            for (cy, cx) in self.beam_cells(y, x, d) {
                cnt[cy][cx] += 1;
            }
        }
        cnt
    }
}

/// Empty board of radius `r`: '*' border, 'O' cells.
pub fn empty_board(r: usize) -> Board {
    let lines = render_hex(r, |i, j| if hex_is_border(r, i, j) { '*' } else { 'O' });
    Board { r, grid: lines.into_iter().map(|l| l.into_bytes()).collect() }
}

/// Grid position `(y, x)` of token `j` in row `i` of a radius-`r` board.
pub fn token_pos(r: usize, i: usize, j: usize) -> (i64, i64) {
    (i as i64, (i.abs_diff(r) + 2 * j) as i64)
}

/// Border positions in clockwise order, starting at the left corner (emitter 1's corner).
/// Length `6r`.
pub fn border_ring(r: usize) -> Vec<(i64, i64)> {
    let last = |i: usize| 2 * r - i.abs_diff(r);
    let mut v = Vec::new();
    // left corner, up the upper-left side
    for i in (1..=r).rev() {
        v.push(token_pos(r, i, 0));
    }
    // top row, left to right
    for j in 0..r {
        v.push(token_pos(r, 0, j));
    }
    // down the right side
    for i in 0..2 * r {
        v.push(token_pos(r, i, last(i)));
    }
    // bottom row, right to left
    for j in (1..=r).rev() {
        v.push(token_pos(r, 2 * r, j));
    }
    // up the lower-left side
    for i in (r + 1..=2 * r).rev() {
        v.push(token_pos(r, i, 0));
    }
    assert_eq!(v.len(), 6 * r);
    v
}

/// Ring index of emitter `d`'s starting corner (1 left, 2 top-left, 3 top-right, 4 right,
/// 5 bottom-right, 6 bottom-left).
pub fn start_corner(r: usize, d: u8) -> usize {
    match d {
        1 => 0,
        2 => r,
        3 => 2 * r,
        4 => 3 * r,
        5 => 4 * r,
        6 => 5 * r,
        _ => panic!("bad emitter {d}"),
    }
}

impl Board {
    /// Applies one tick of matter rules for beams from `(y, x, dir)` emitters:
    /// 2 beams create matter, 3+ destroy it.
    pub fn apply_beams(&mut self, emitters: &[(i64, i64, u8)]) {
        let mut cnt = vec![vec![0u32; self.cols()]; self.rows()];
        for &(y, x, d) in emitters {
            for (cy, cx) in self.beam_cells(y, x, d) {
                cnt[cy][cx] += 1;
            }
        }
        for (y, row) in cnt.iter().enumerate() {
            for (x, &c) in row.iter().enumerate() {
                if c == 2 {
                    self.grid[y][x] = b'M';
                } else if c >= 3 {
                    self.grid[y][x] = b'O';
                }
            }
        }
    }
}

/// The six emitters on the border rail (index `e` has direction `e + 1`).
#[derive(Clone, Debug)]
pub struct Rig {
    pub ring: Vec<(i64, i64)>,
    pub pos: [usize; 6],
    pub active: [bool; 6],
}

impl Rig {
    pub fn new(r: usize) -> Self {
        Rig {
            ring: border_ring(r),
            pos: std::array::from_fn(|e| start_corner(r, e as u8 + 1)),
            active: [false; 6],
        }
    }

    /// Executes one instruction line (F/B/T/- per emitter).
    pub fn exec(&mut self, line: &[u8; 6]) {
        let n = self.ring.len();
        for (e, &ins) in line.iter().enumerate() {
            match ins {
                b'F' => self.pos[e] = (self.pos[e] + 1) % n,
                b'B' => self.pos[e] = (self.pos[e] + n - 1) % n,
                b'T' => self.active[e] = !self.active[e],
                b'-' => {}
                c => panic!("bad instruction {}", c as char),
            }
        }
    }

    /// Active emitters as `(y, x, direction)`.
    pub fn beams(&self) -> Vec<(i64, i64, u8)> {
        (0..6)
            .filter(|&e| self.active[e])
            .map(|e| (self.ring[self.pos[e]].0, self.ring[self.pos[e]].1, e as u8 + 1))
            .collect()
    }
}

/// Grid offsets of the six hex neighbours.
pub const NEIGHBOURS: [(i64, i64); 6] = [(0, 2), (0, -2), (1, 1), (1, -1), (-1, 1), (-1, -1)];

/// Parses one instruction line "F T - T B -".
pub fn parse_instr(line: &str) -> [u8; 6] {
    let toks: Vec<u8> = line.split_whitespace().map(|t| t.as_bytes()[0]).collect();
    assert_eq!(toks.len(), 6, "bad instruction line {line:?}");
    std::array::from_fn(|i| toks[i])
}

/// A pattern to produce: its matter cells and the cells that must stay clear (skirting).
#[derive(Clone, Debug)]
pub struct Pattern {
    pub board: Board,
    pub cells: Vec<(usize, usize)>,
    pub skirting: Vec<(usize, usize)>,
}

impl Pattern {
    pub fn new(board: Board) -> Self {
        let mut cells = Vec::new();
        for (y, row) in board.grid.iter().enumerate() {
            for (x, &c) in row.iter().enumerate() {
                if c == b'M' {
                    cells.push((y, x));
                }
            }
        }
        let mut skirting = std::collections::BTreeSet::new();
        for &(y, x) in &cells {
            for (dy, dx) in NEIGHBOURS {
                let (ny, nx) = (y as i64 + dy, x as i64 + dx);
                if board.get(ny, nx) == Some(b'O') {
                    skirting.insert((ny as usize, nx as usize));
                }
            }
        }
        Pattern { board, cells, skirting: skirting.into_iter().collect() }
    }

    /// All pattern matter present on `b`, and no matter on the skirting.
    pub fn detected(&self, b: &Board) -> bool {
        !self.cells.is_empty()
            && self.cells.iter().all(|&(y, x)| b.grid[y][x] == b'M')
            && self.skirting.iter().all(|&(y, x)| b.grid[y][x] != b'M')
    }

    /// Removes the pattern's matter from `b`.
    pub fn remove(&self, b: &mut Board) {
        for &(y, x) in &self.cells {
            b.grid[y][x] = b'O';
        }
    }
}

/// Runs `program` from the initial state and counts accepted patterns (level 5 rules).
pub fn count_accepted(pattern: &Pattern, program: &[[u8; 6]]) -> usize {
    let r = pattern.board.r;
    let mut b = empty_board(r);
    let mut rig = Rig::new(r);
    let mut count = 0;
    for line in program {
        rig.exec(line);
        b.apply_beams(&rig.beams());
        if pattern.detected(&b) {
            pattern.remove(&mut b);
            count += 1;
        }
    }
    count
}
