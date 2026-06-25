// A clean library module with no serialization guard. Must NOT be flagged.
pub fn add(a: i64, b: i64) -> i64 {
    if a > b {
        a + b
    } else {
        b - a
    }
}
