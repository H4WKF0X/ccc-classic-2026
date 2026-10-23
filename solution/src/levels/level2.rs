use crate::model::{dir_delta, parse_boards, Board};

/// Fires every emitter: walks its straight line across the grid, turning 'O' into 'M'.
fn fire(b: &mut Board) {
    for (y0, x0, d) in b.emitters() {
        let (dy, dx) = dir_delta(d);
        let (mut y, mut x) = (y0 + dy, x0 + dx);
        while let Some(c) = b.get(y, x) {
            if c == b'O' {
                b.grid[y as usize][x as usize] = b'M';
            }
            y += dy;
            x += dx;
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
