use std::sync::OnceLock;
use tokio::sync::RwLock;

// RwLock serialization guards are intentionally out of scope for OnceLock
// Mutex detection; this file must NOT be flagged.
fn shared_config() -> &'static RwLock<()> {
    static C: OnceLock<RwLock<()>> = OnceLock::new();
    C.get_or_init(|| RwLock::new(()))
}
