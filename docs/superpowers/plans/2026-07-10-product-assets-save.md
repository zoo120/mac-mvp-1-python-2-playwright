# Product Assets Save Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local “one-click save product copy and images” workflow for Xianyu item links.

**Architecture:** Keep detail-page material capture separate from search crawling. `asset_saver.py` owns Playwright detail extraction and local file writing, `database.py` tracks saved material records, and `app.py` exposes a simple Streamlit page for selecting one candidate and saving it.

**Tech Stack:** Python, Playwright persistent Chromium profile, SQLite, Streamlit, pytest.

## Global Constraints

- Local Mac MVP only; no server deployment.
- No automated messages, orders, comments, or account actions.
- Detail saving is manual one-item-at-a-time, not high-frequency batch crawling.
- Missing detail fields must not crash the app; save what is available.
- Use the existing `.playwright-profile` login state.

---

### Task 1: Database record for saved material packages

**Files:**
- Modify: `database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Produces: `record_saved_asset(asset, db_path=DEFAULT_DB_PATH, connection=None) -> int`
- Produces: `list_saved_assets(db_path=DEFAULT_DB_PATH, limit=200) -> list[sqlite3.Row]`

- [ ] Write failing tests that initialize the DB, insert a saved asset record, update it by `item_url`, and list records newest first.
- [ ] Run the focused database tests and confirm they fail because the functions/table do not exist.
- [ ] Add `saved_product_assets` table and the two database functions.
- [ ] Re-run the focused database tests and confirm they pass.

### Task 2: Local material saving helper

**Files:**
- Create: `asset_saver.py`
- Test: `tests/test_asset_saver.py`

**Interfaces:**
- Produces: `safe_folder_name(value: str, fallback: str = "商品素材") -> str`
- Produces: `save_material_files(payload, image_files, output_root=SAVED_PRODUCTS_DIR) -> dict[str, Any]`
- Produces: `normalize_detail_payload(raw, item_url, title_hint="") -> dict[str, Any]`

- [ ] Write failing tests for safe folder naming, payload normalization, and writing `文案.txt`, `商品信息.json`, and image files.
- [ ] Run the focused asset tests and confirm they fail because `asset_saver.py` does not exist.
- [ ] Implement the minimal pure file helpers.
- [ ] Re-run the focused asset tests and confirm they pass.

### Task 3: Playwright detail extraction

**Files:**
- Modify: `asset_saver.py`
- Test: `tests/test_asset_saver.py`

**Interfaces:**
- Produces: `save_product_assets(item_url, title_hint="", db_path=DEFAULT_DB_PATH, output_root=SAVED_PRODUCTS_DIR) -> dict[str, Any]`

- [ ] Add tests for URL validation and image URL filtering.
- [ ] Implement visible Playwright detail-page extraction using the existing persistent profile.
- [ ] Download images through Playwright request context when possible; continue when one image fails.
- [ ] Save the material package and record it in SQLite.

### Task 4: Streamlit page

**Files:**
- Modify: `app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `query_candidates`, `save_product_assets`, `list_saved_assets`
- Produces: New page name `素材保存`

- [ ] Write failing app tests for page registration and the candidate choices query.
- [ ] Add page UI: select candidate, save button, saved material records table, link to local folder.
- [ ] Re-run app tests.

### Task 5: Documentation and verification

**Files:**
- Modify: `README.md`

- [ ] Document how to use the “素材保存” page.
- [ ] Run the full pytest suite.
- [ ] Report exact verification results.
