// shatter/stubs/rust/storage_delete_errors.rs
//
// A registered Shatter stub for the `Storage` port. It errors on
// `delete_object` so the pickpackit sweeper takes the "rows left for retry"
// branch instead of marking rows done. Gate this module out of release builds
// (e.g. behind a `shatter` cfg/feature) so it never ships in production.
use crate::storage::{Storage, StorageError}; // the project's port + error type
use async_trait::async_trait;

/// Registered in .shatter/config.yaml as "storage_delete_errors".
pub struct StorageDeleteErrors;

impl StorageDeleteErrors {
    pub fn new() -> Self {
        StorageDeleteErrors
    }
}

#[async_trait]
impl Storage for StorageDeleteErrors {
    /// The branch driver: deletes always fail, so the sweeper must leave rows
    /// for retry instead of marking them done.
    async fn delete_object(&self, _key: &str) -> Result<(), StorageError> {
        Err(StorageError::Io("simulated S3 delete failure".into()))
    }

    /// Other methods stay benign so they don't mask the branch under test.
    async fn put_object(&self, _key: &str, _bytes: &[u8]) -> Result<(), StorageError> {
        Ok(())
    }

    async fn object_exists(&self, _key: &str) -> Result<bool, StorageError> {
        Ok(true)
    }
}
