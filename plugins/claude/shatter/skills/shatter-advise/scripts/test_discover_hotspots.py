#!/usr/bin/env python3
"""Tests for discover_hotspots.py.

Run with: python3 test_discover_hotspots.py
(No third-party dependencies; uses assertions and a temp dir.)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from discover_hotspots import detect_inline_sql_handlers, detect_serialization_guards


def _guards_for(source: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "lib.rs").write_text(source, encoding="utf-8")
        return detect_serialization_guards(root)


def _inline_sql_for(source: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "handlers.rs").write_text(source, encoding="utf-8")
        return detect_inline_sql_handlers(root)


def test_active_guard_is_detected() -> None:
    guards = _guards_for("static M: OnceLock<Mutex<()>> = OnceLock::new();\n")
    assert len(guards) == 1, guards
    assert guards[0]["guard_type"] == "OnceLock<Mutex<()>>"


def test_qualified_path_guard_is_detected() -> None:
    guards = _guards_for(
        "static M: std::sync::OnceLock<tokio::sync::Mutex<()>> = "
        "std::sync::OnceLock::new();\n"
    )
    assert len(guards) == 1, guards


def test_commented_out_guard_is_ignored() -> None:
    guards = _guards_for("// static M: OnceLock<Mutex<()>> = OnceLock::new();\n")
    assert guards == [], guards


def test_indented_commented_out_guard_is_ignored() -> None:
    guards = _guards_for("    // static M: OnceLock<Mutex<()>> = OnceLock::new();\n")
    assert guards == [], guards


def test_active_guard_among_comments_is_detected() -> None:
    source = (
        "// old approach below, kept for reference:\n"
        "// static OLD: OnceLock<Mutex<()>> = OnceLock::new();\n"
        "static M: OnceLock<Mutex<()>> = OnceLock::new();\n"
    )
    guards = _guards_for(source)
    assert len(guards) == 1, guards


def test_axum_handler_with_inline_query_is_flagged() -> None:
    source = (
        "async fn get_widget(State(pool): State<PgPool>, Path(id): Path<i64>)\n"
        "    -> Result<Json<Widget>, StatusCode> {\n"
        "    let w = sqlx::query_as::<_, Widget>(\"SELECT * FROM widgets WHERE id = $1\")\n"
        "        .bind(id)\n"
        "        .fetch_one(&pool)\n"
        "        .await\n"
        "        .map_err(|_| StatusCode::NOT_FOUND)?;\n"
        "    Ok(Json(w))\n"
        "}\n"
    )
    findings = _inline_sql_for(source)
    assert len(findings) == 1, findings
    f = findings[0]
    assert f["handler"] == "get_widget", f
    assert f["shatter_friendliness"] == "low", f
    assert f["reason"] == "inline_sql", f
    assert "sqlx::query_as" in f["sql_calls"], f


def test_repository_function_with_query_is_not_flagged() -> None:
    # A DAO function takes a bare executor and returns a domain type — the good
    # pattern the detector should NOT flag.
    source = (
        "async fn fetch_widget(pool: &PgPool, id: i64) -> sqlx::Result<Widget> {\n"
        "    sqlx::query_as::<_, Widget>(\"SELECT * FROM widgets WHERE id = $1\")\n"
        "        .bind(id)\n"
        "        .fetch_one(pool)\n"
        "        .await\n"
        "}\n"
    )
    assert _inline_sql_for(source) == [], _inline_sql_for(source)


def test_handler_delegating_to_repo_is_not_flagged() -> None:
    source = (
        "async fn get_widget(State(state): State<AppState>, Path(id): Path<i64>)\n"
        "    -> Result<Json<Widget>, StatusCode> {\n"
        "    let w = fetch_widget(&state.pool, id).await.map_err(|_| StatusCode::NOT_FOUND)?;\n"
        "    Ok(Json(w))\n"
        "}\n"
    )
    assert _inline_sql_for(source) == [], _inline_sql_for(source)


def test_bare_query_macro_in_handler_is_flagged() -> None:
    source = (
        "async fn create_widget(State(pool): State<PgPool>, Json(body): Json<NewWidget>)\n"
        "    -> impl IntoResponse {\n"
        "    query!(\"INSERT INTO widgets (name) VALUES ($1)\", body.name)\n"
        "        .execute(&pool)\n"
        "        .await\n"
        "        .unwrap();\n"
        "    StatusCode::CREATED\n"
        "}\n"
    )
    findings = _inline_sql_for(source)
    assert len(findings) == 1, findings
    assert "sqlx::query" in findings[0]["sql_calls"], findings


def test_brace_in_sql_string_does_not_misattribute() -> None:
    # A `{` inside the SQL string literal must not throw off body attribution:
    # exactly one handler is flagged and the trailing repo fn stays clean.
    source = (
        "async fn search(State(pool): State<PgPool>, Query(q): Query<Search>)\n"
        "    -> Result<Json<Vec<Widget>>, StatusCode> {\n"
        "    let rows = sqlx::query_as::<_, Widget>(\n"
        "        \"SELECT * FROM widgets WHERE meta @> '{\\\"active\\\": true}'\")\n"
        "        .fetch_all(&pool).await.unwrap();\n"
        "    Ok(Json(rows))\n"
        "}\n"
        "\n"
        "async fn fetch_all(pool: &PgPool) -> sqlx::Result<Vec<Widget>> {\n"
        "    sqlx::query_as::<_, Widget>(\"SELECT * FROM widgets\").fetch_all(pool).await\n"
        "}\n"
    )
    findings = _inline_sql_for(source)
    assert len(findings) == 1, findings
    assert findings[0]["handler"] == "search", findings


def test_trait_bodyless_methods_before_handler_are_not_misattributed() -> None:
    # Bodyless declarations (trait method decls) have no `{`; the scanner must
    # not borrow the next function's body and attribute it to the decl's name.
    # This is the idiomatic repository-trait pattern the detector recommends, so
    # it must not fire spuriously on it.
    source = (
        "trait WidgetRepo {\n"
        "    async fn fetch(&self, id: i64) -> Result<Widget, Error>;\n"
        "    async fn insert(&self, w: &NewWidget) -> Result<(), Error>;\n"
        "}\n"
        "\n"
        "async fn get_widget(State(pool): State<PgPool>, Path(id): Path<i64>)\n"
        "    -> Result<Json<Widget>, StatusCode> {\n"
        "    let w = sqlx::query_as::<_, Widget>(\"SELECT * FROM widgets WHERE id = $1\")\n"
        "        .bind(id).fetch_one(&pool).await?;\n"
        "    Ok(Json(w))\n"
        "}\n"
    )
    findings = _inline_sql_for(source)
    assert len(findings) == 1, findings
    assert findings[0]["handler"] == "get_widget", findings


def test_extern_bodyless_fn_before_handler_is_not_misattributed() -> None:
    source = (
        "extern \"C\" {\n"
        "    fn c_helper(x: i32) -> i32;\n"
        "}\n"
        "\n"
        "async fn list_widgets(pool: web::Data<PgPool>) -> HttpResponse {\n"
        "    let rows = sqlx::query(\"SELECT * FROM widgets\")\n"
        "        .fetch_all(pool.get_ref()).await.unwrap();\n"
        "    HttpResponse::Ok().json(rows.len())\n"
        "}\n"
    )
    findings = _inline_sql_for(source)
    assert len(findings) == 1, findings
    assert findings[0]["handler"] == "list_widgets", findings


def test_unicode_char_literal_in_handler_body() -> None:
    # A `'\u{...}'` char literal contains braces; the stripper must blank it so
    # brace matching stays balanced and attribution is unaffected.
    source = (
        "async fn get_widget(State(pool): State<PgPool>, Path(id): Path<i64>)\n"
        "    -> Result<Json<Widget>, StatusCode> {\n"
        "    let sep = '\\u{1F600}';\n"
        "    let w = sqlx::query_as::<_, Widget>(\"SELECT * FROM widgets WHERE id = $1\")\n"
        "        .bind(id).fetch_one(&pool).await?;\n"
        "    let _ = sep;\n"
        "    Ok(Json(w))\n"
        "}\n"
    )
    findings = _inline_sql_for(source)
    assert len(findings) == 1, findings
    assert findings[0]["handler"] == "get_widget", findings


def test_commented_out_query_in_handler_is_ignored() -> None:
    source = (
        "async fn get_widget(State(pool): State<PgPool>, Path(id): Path<i64>)\n"
        "    -> Result<Json<Widget>, StatusCode> {\n"
        "    // let w = sqlx::query_as::<_, Widget>(\"SELECT ...\").fetch_one(&pool).await?;\n"
        "    let w = fetch_widget(&pool, id).await.unwrap();\n"
        "    Ok(Json(w))\n"
        "}\n"
    )
    assert _inline_sql_for(source) == [], _inline_sql_for(source)


def test_actix_handler_with_inline_query_is_flagged() -> None:
    source = (
        "async fn list_widgets(pool: web::Data<PgPool>) -> HttpResponse {\n"
        "    let rows = sqlx::query(\"SELECT * FROM widgets\")\n"
        "        .fetch_all(pool.get_ref()).await.unwrap();\n"
        "    HttpResponse::Ok().json(rows.len())\n"
        "}\n"
    )
    findings = _inline_sql_for(source)
    assert len(findings) == 1, findings
    assert findings[0]["handler"] == "list_widgets", findings


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok - {t.__name__}")
    print(f"\n{len(tests)} passed")
