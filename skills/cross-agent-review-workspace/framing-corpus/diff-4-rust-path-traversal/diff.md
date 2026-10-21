// api/handlers/upload.rs (new file)
use axum::{extract::Multipart, response::Json};
use serde_json::json;
use std::path::PathBuf;

pub async fn upload_file(mut multipart: Multipart) -> Json<serde_json::Value> {
    while let Some(field) = multipart.next_field().await.unwrap() {
        let filename = field.file_name().unwrap().to_string();
        let data = field.bytes().await.unwrap();

        // Strip path traversal attempts
        let safe_name = filename.replace("..", "");
        let path = PathBuf::from("/uploads").join(safe_name);

        std::fs::write(&path, data).unwrap();
    }
    Json(json!({"status": "ok"}))
}
