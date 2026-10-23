use crate::model::{border_ring, empty_board, start_corner, Board};
use harness::parse::Tokens;

/// Runs a program on an empty radius-`r` board.
fn simulate(r: usize, program: &[[u8; 6]]) -> Board {
    let ring = border_ring(r);
    let n = ring.len();
    let mut pos: Vec<usize> = (1..=6).map(|d| start_corner(r, d)).collect();
    let mut active = [false; 6];
    let mut b = empty_board(r);
    for line in program {
        for e in 0..6 {
            match line[e] {
                b'F' => pos[e] = (pos[e] + 1) % n,
                b'B' => pos[e] = (pos[e] + n - 1) % n,
                b'T' => active[e] = !active[e],
                b'-' => {}
                c => panic!("bad instruction {}", c as char),
            }
        }
        let em: Vec<(i64, i64, u8)> = (0..6)
            .filter(|&e| active[e])
            .map(|e| (ring[pos[e]].0, ring[pos[e]].1, e as u8 + 1))
            .collect();
        b.apply_beams(&em);
    }
    b
}

pub fn solve(input: &str) -> Vec<String> {
    let mut t = Tokens::new(input);
    let n: usize = t.next();
    let mut out = Vec::new();
    for _ in 0..n {
        let r: usize = t.next();
        let l: usize = t.next();
        let program: Vec<[u8; 6]> =
            (0..l).map(|_| std::array::from_fn(|_| t.next_str().as_bytes()[0])).collect();
        out.extend(simulate(r, &program).lines());
        out.push(String::new());
    }
    out
}

#[cfg(test)]
mod tests {
    use crate::model::{border_ring, empty_board, start_corner};

    #[test]
    fn corners_are_where_the_statement_draws_them() {
        let r = 3;
        let ring = border_ring(r);
        let b = empty_board(r);
        let w = b.cols() as i64 - 1;
        assert_eq!(ring[start_corner(r, 1)], (3, 0));
        assert_eq!(ring[start_corner(r, 2)], (0, 3));
        assert_eq!(ring[start_corner(r, 3)], (0, 9));
        assert_eq!(ring[start_corner(r, 4)], (3, w));
        assert_eq!(ring[start_corner(r, 5)], (6, 9));
        assert_eq!(ring[start_corner(r, 6)], (6, 3));
    }
}
