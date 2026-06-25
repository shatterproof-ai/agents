use std::sync::OnceLock;
use tokio::sync::{Mutex, MutexGuard};

fn serial_lock() -> &'static Mutex<()> {
    static M: OnceLock<Mutex<()>> = OnceLock::new();
    M.get_or_init(|| Mutex::new(()))
}

async fn acquire_serial() -> MutexGuard<'static, ()> {
    serial_lock().lock().await
}

#[tokio::test]
async fn drains_pending_deletions() {
    let _guard = acquire_serial().await;
    // serializes all sweeper tests around shared DB state
}
