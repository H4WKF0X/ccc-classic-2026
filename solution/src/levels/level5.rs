use crate::model::{empty_board, parse_instr, Board, Rig, NEIGHBOURS};
use std::collections::BTreeSet;

struct Case {
    pattern: Board,
    program: Vec<[u8; 6]>,
}

fn parse(input: &str) -> Vec<Case> {
    let mut lines = input.lines().filter(|l| !l.trim().is_empty());
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    (0..n)
        .map(|_| {
            let h = harness::parse::ints(lines.next().unwrap());
            let (r, rows) = (h[0] as usize, h[1] as usize);
            let grid = (0..rows).map(|_| lines.next().unwrap().trim().as_bytes().to_vec()).collect();
            let l: usize = lines.next().unwrap().trim().parse().unwrap();
            let program = (0..l).map(|_| parse_instr(lines.next().unwrap())).collect();
            Case { pattern: Board { r, grid }, program }
        })
        .collect()
}

/// Matter positions of the pattern.
fn matter(b: &Board) -> Vec<(usize, usize)> {
    let mut v = Vec::new();
    for (y, row) in b.grid.iter().enumerate() {
        for (x, &c) in row.iter().enumerate() {
            if c == b'M' {
                v.push((y, x));
            }
        }
    }
    v
}

/// Pattern present in place, with no other matter adjacent to it.
fn detected(b: &Board, pat: &[(usize, usize)], in_pat: &BTreeSet<(usize, usize)>) -> bool {
    pat.iter().all(|&(y, x)| b.grid[y][x] == b'M')
        && pat.iter().all(|&(y, x)| {
            NEIGHBOURS.iter().all(|&(dy, dx)| {
                let (ny, nx) = (y as i64 + dy, x as i64 + dx);
                b.get(ny, nx) != Some(b'M') || in_pat.contains(&(ny as usize, nx as usize))
            })
        })
}

fn count_submissions(case: &Case) -> usize {
    let r = case.pattern.r;
    let pat = matter(&case.pattern);
    let in_pat: BTreeSet<_> = pat.iter().copied().collect();
    let mut b = empty_board(r);
    assert_eq!(b.rows(), case.pattern.rows());
    assert_eq!(b.cols(), case.pattern.cols());
    let mut rig = Rig::new(r);
    let mut count = 0;
    for line in &case.program {
        rig.exec(line);
        b.apply_beams(&rig.beams());
        if !pat.is_empty() && detected(&b, &pat, &in_pat) {
            for &(y, x) in &pat {
                b.grid[y][x] = b'O';
            }
            count += 1;
        }
    }
    count
}

pub fn solve(input: &str) -> Vec<String> {
    parse(input).iter().map(|c| count_submissions(c).to_string()).collect()
}
