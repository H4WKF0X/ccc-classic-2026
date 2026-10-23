use crate::model::{hex_is_border, render_hex};
use harness::parse::Tokens;

pub fn solve(input: &str) -> Vec<String> {
    let mut t = Tokens::new(input);
    let n: usize = t.next();
    let mut out = Vec::new();
    for _ in 0..n {
        let r: usize = t.next();
        out.extend(render_hex(r, |i, j| if hex_is_border(r, i, j) { '*' } else { 'O' }));
        out.push(String::new());
    }
    out
}
