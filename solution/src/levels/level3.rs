use crate::model::{parse_boards, Board};

/// Two beams on a cell create matter, three or more destroy it.
fn fire(b: &mut Board) {
    let cnt = b.beam_counts();
    for (y, row) in cnt.iter().enumerate() {
        for (x, &c) in row.iter().enumerate() {
            if c == 2 {
                b.grid[y][x] = b'M';
            } else if c >= 3 {
                b.grid[y][x] = b'O';
            }
        }
    }
}

pub fn solve(input: &str) -> Vec<String> {
    let mut out = Vec::new();
    for mut b in parse_boards(input) {
        fire(&mut b);
        out.extend(b.lines());
        out.push(String::new());
    }
    out
}
