# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repo builds and serves the **오름(Oreum) dataset** for a Jeju oreum-recommendation MCP server. Two Python apps share `data/oreum.json`:

- `map_editor/` — a FastAPI admin tool for manually collecting POI coordinates (entrance/restroom/parking), entrance/parking addresses, and trail paths on top of Kakao Maps. Reads **and writes** `data/oreum.json`.
- `oreum_mcp/` — the recommendation MCP server itself (FastAPI wrapped into MCP tools via `FastMCP.from_fastapi()`). Read-only: it never writes `data/oreum.json`, and re-reads it on every request so collection work in `map_editor` shows up without a server restart.

`data/oreum.json` is the **only** data store either app reads/writes. `data/oreum.db` (SQLite) and its scripts (`build_oreum_db.py`, `export_oreum_json.py`, `sync_json_to_db.py`) are a legacy path kept for reference — nothing in `map_editor/` or `oreum_mcp/` touches them anymore. `data/no_oreum.json` is an old, unused snapshot; don't read from it or treat it as a data source. `sample_MCP/` and `sample_MCP2/` are reference samples (not our code) that `oreum_mcp/` was originally modeled on — gitignored, don't edit.

## Commands

- `python map_editor/app.py` — start the map editor on `http://0.0.0.0:8010`. Check the port isn't already in use first (`netstat -ano | findstr :8010` on Windows), and stop your own instance when done.
- `python oreum_mcp/app.py [--host 0.0.0.0] [--port 11010] [--reload]` — start the MCP server (port also overridable via `OREUM_MCP_PORT` env var). Streamable-http transport, stateless (no session state — safe to restart during dev without client-side "Session not found" errors). `GET /health` for a liveness check; MCP endpoint mounted at `/`.
- `python scripts/build_oreum_json.py` — rebuild `data/oreum.json` from the raw CSV. **Destructive** to all map_editor-collected data; see below before running.
- `oreum_mcp/` has its own `requirements.txt` (`fastapi`, `fastmcp`, `uvicorn[standard]`, `python-dotenv`); `oreum_mcp/docker-compose.yml` + `Dockerfile` run it in a container with `data/` mounted read-only and `OREUM_DATA_PATH` pointing at the mounted `oreum.json` (an optional `ngrok` sidecar service exposes it externally for MCP tool registration — needs `NGROK_AUTHTOKEN` in `oreum_mcp/.env`, copy from `.env.example`). No requirements.txt/pyproject.toml or lint config exists at the repo root for `map_editor`/`scripts` — their dependencies (`fastapi`, `uvicorn`, `pydantic`, `requests`) must already be available in the environment. `oreum_mcp/test_tools.py` — regression cases run against a live server via `fastmcp.Client` (`python oreum_mcp/test_tools.py`, requires the MCP server already running) — is the closest thing to a test suite; no pytest config exists at the repo root.

## Conventions

- All Korean-text JSON I/O (reading/writing `data/oreum.json`, the CSV, etc.) must use `encoding="utf-8"` and, on writes, `ensure_ascii=False` — dropping either mangles the 오름 names/addresses.
- Commit messages: short imperative subject, optionally prefixed Conventional-Commit-style (`fix:`, `docs:`, `feat:`) — see `git log` for examples.

## Data pipeline

```
data/오름_dataset.csv (raw, CP949, 328 rows)
        │  scripts/build_oreum_json.py
        ▼
data/oreum.json (pretty-printed JSON array, one grouped object per oreum)
        ▲
        └── map_editor writes POI/address/trail edits straight into this file
```

- `python scripts/build_oreum_json.py` — **destructive**: regenerates `data/oreum.json` from the CSV only, imports the CSV-parsing helpers (`load_rows`, `fix_coord_swap`, `parse_climb_time`, etc.) from `scripts/build_oreum_db.py`. All map_editor-collected fields (`coordinates.entrances`, `coordinates.parking/restroom`, `coordinates.parking.address`, `trails`) are reset to empty (`coordinates.entrances`/`trails` become `[]`) — it does not merge in anything from the existing `data/oreum.json`, `data/oreum.db`, or `data/no_oreum.json`. The one exception: `coordinates.entrances` is seeded from the CSV's original entrance lat/lng as a single-item array (`address: null`) when present, since that's the raw source data rather than a map_editor collection. Only run this when you intend to start POI/trail collection over from scratch (e.g. the raw CSV changed).
- `map_editor/app.py` reads and writes `data/oreum.json` directly on every POI/address/trail save — there is no separate export/sync step.
- The legacy SQLite path (`build_oreum_db.py` → `data/oreum.db` → `export_oreum_json.py`/`sync_json_to_db.py`) still works standalone if you need it, but it is decoupled from `data/oreum.json` and from map_editor.

There is no requirements.txt/pyproject.toml in the repo; dependencies (`fastapi`, `uvicorn`, `pydantic`, `requests`) must be available in the environment already.

`scripts/migrate_entrances_and_drop_trail_start.py`, `scripts/migrate_trails_to_array.py`, and `scripts/migrate_parking_to_array_and_add_notes.py` are one-off, already-applied migrations that reshaped older `data/oreum.json` schemas (single `entrance`/`trail`/`parking` objects → arrays; `note` fields backfilled) into the current shape described below. They are not part of the regular pipeline — don't re-run them against a `data/oreum.json` that already matches the current schema.

## `data/oreum.json` record shape

Each record is grouped into sections rather than one flat object:

```
{
  "id", "name", "region", "address",   // 기본 식별 정보 (CSV 원본)
  "basic_info": { relative_height_m, elevation_m, area_sqm, shape_type, shape_direction,
                   difficulty, distance_km, climb_time_min, recommended_season },
  "coordinates": {
    "peak":      { lat, lng },
    "entrances": [ { "id": number, lat, lng, address, note }, ... ],  // 0..N per oreum (an oreum can have multiple entrances)
    "parking":   [ { "id": number, lat, lng, address, note }, ... ],  // 0..N per oreum (2+ parking areas are common); address: 카카오 역지오코딩 자동 채움 + 수동 수정
    "restroom":  { lat, lng, note }
  },
  "trails": [ { "id": number, "path": [{lat, lng}, ...] | null,
                "surface_type": 1|2|3|4|5|null, "length_m": number|null, "note": string|null }, ... ],  // 0..N per oreum, see below
  "facilities": { surface, parking, restroom, trail_info, hours_fee },  // CSV 자유서술 텍스트
  "kakao_map_url", "notes", "created_at"
}
```

`facilities.parking`/`facilities.restroom` are free-text CSV descriptions (e.g. `"길가 주차"`, `"없음"`) — distinct from the collected `coordinates.parking`/`coordinates.restroom` points; don't conflate them.

Each of `coordinates.entrances[]`, `coordinates.parking[]`, `coordinates.restroom`, and `trails[]` carries its own `note` field — a short free-text description collected in the map editor (e.g. "우천시 진입 불가", "비포장, 4륜 권장"). This is a distinct field from the top-level per-record `notes` — don't conflate the two.

`notes` is either `null` (no remark) or a structured object (migrated 2026-08-13 from a single free-text string, since the original blob mixed access rules, trail condition, safety cautions, marketing highlights, directions, trivia, and cross-oreum recommendations in one unstructured sentence — unusable for filtering). Shape:

```
"notes": {
  "raw_note": string,        // original free-text, preserved verbatim for reference/re-classification
  "access": {
    "status": "open" | "reservation_required" | "restricted" | "prohibited" | null,
    "detail": string | null, // why access is limited (사유지/군사기지/자연휴식년제 등)
    "fee": string | null,    // entrance fee text, e.g. "어른 1,000원 / 청소년 600원 / 어린이 300원"
    "hours": string | null   // operating hours text, e.g. "매일 09:00~17:00"
  },
  "trail_condition": "well_maintained" | "poor" | "unclear" | "none" | null,
  "caution": [string],       // safety warnings (경사/미끄러움/계절 등)
  "recommend_for": string | null,  // who it suits or doesn't (초보자 적합, 관광객 비추천 등)
  "highlights": [string],    // scenic/marketing draws (전망, 포토존, 웨딩촬영지 등)
  "directions": string | null,     // parking/access-route guidance distinct from coordinates
  "trivia": string | null,   // historical/name-origin trivia, not actionable for filtering
  "linked_oreums": [string]  // names of other oreums this one is commonly recommended to pair with
}
```

This was a one-off manual classification (`scripts/build_oreum_json.py` does **not** reproduce it — CSV rebuilds reset `notes` to `null` per its documented destructive behavior, so this structure would need re-deriving from `raw_note`-equivalent source text if the CSV pipeline is ever re-run). Not read/written by `map_editor` (confirmed no `notes` references in `app.py`/`index.html`) — it exists purely for downstream recommendation-engine consumption.

## Running the map editor

```
python map_editor/app.py
```

Serves on `http://0.0.0.0:8010`: the static UI (`map_editor/static/index.html`, a single-file Kakao-Maps page) at `/`, and a small JSON API at `/api/oreum*`.

Key behavior to preserve when touching this code:
- All endpoints read/write `data/oreum.json` directly via `load_records()`/`save_records()` — no SQLite involved. Keep it that way.
- `PATCH /api/oreum/{id}/poi` is **restroom-only** — sets `coordinates.restroom.lat/lng`, and `coordinates.restroom.note` when `note` is provided (restroom has no address). `DELETE /api/oreum/{id}/poi/{poi_type}` (also restroom-only) clears `lat`/`lng` but leaves `note` untouched. Entrances and parking each have their own collection endpoints (see below) — they never go through this generic POI path.
- An oreum can have zero or more entrances (`coordinates.entrances: []` array — some oreums genuinely have multiple physical entrances). Each entrance is addressed by its own `id` (unique within the oreum, assigned server-side as `max(existing ids) + 1`, stable across other entrances' edits/deletes). `POST /api/oreum/{id}/entrances` creates a new entrance from a `{lat, lng, address, note}` body. `PATCH /api/oreum/{id}/entrances/{entrance_id}` updates an existing entrance's `lat`/`lng`, and `address`/`note` when non-null. `DELETE /api/oreum/{id}/entrances/{entrance_id}` removes that entrance from the array. Frontend: clicking "입구 찍기" activates entrance-adding mode and every subsequent map click while active POSTs a new entrance (not an overwrite) — each entrance gets its own row in the sidebar `#entrance-list` with its own address/note input+save, roadview, and delete controls, rendered by `renderEntranceList`.
- An oreum can have zero or more parking spots (`coordinates.parking: []` array — some oreums genuinely have 2+ parking areas). This mirrors entrances exactly: own `id` (`max(existing ids) + 1`), `POST /api/oreum/{id}/parking` creates from `{lat, lng, address, note}`, `PATCH /api/oreum/{id}/parking/{parking_id}` updates `lat`/`lng` and non-null `address`/`note`, `DELETE /api/oreum/{id}/parking/{parking_id}` removes it. Frontend: "주차장 찍기" is a multi-add mode button (like entrances, not a single-overwrite pin) backed by `#parking-list`/`renderParkingList`/`addParking`/`saveParkingAddress`/`saveParkingNote`/`deleteParking`.
- An oreum can have zero or more trails (`trails: []` array, e.g. a summit route and a loop trail). Each trail is addressed by its own `id` (unique within the oreum, assigned server-side as `max(existing ids) + 1`, stable across other trails' edits/deletes — never reused as an array index). `POST /api/oreum/{id}/trails` creates a new trail from a `{points: [{lat, lng}, ...], surface_type, note}` body. `PATCH /api/oreum/{id}/trails/{trail_id}` updates an existing trail's `path`/`surface_type`/`note` the same way — unlike entrance/parking, `note` (like `surface_type`) is unconditionally overwritten on every save rather than only-when-non-null, since the frontend always sends the trail's full current state. Both server-compute `length_m` (haversine sum over `points`, see `trail_length_meters`) — the client never sends a length. `DELETE /api/oreum/{id}/trails/{trail_id}` removes that trail entirely from the array (not a field-clearing operation like the POI `DELETE` endpoints). Trails have no `start`/label field — where a trail begins is just the first point of `path`, drawn wherever the user first clicks on the map (not auto-seeded from any POI coordinate), which is what makes multiple entrances actually usable (a trail can start at any of them, or nowhere near one). The frontend only calls POST/PATCH on an explicit "등산로 저장" click for the active trail tab — trail points are **not** saved per-click the way POI pins are, since a path is built from many clicks that shouldn't each persist a half-drawn route.
- Frontend state mirrors this as `draftTrails` (an array, one entry per trail tab, each `{id, points, surfaceType, note}`) plus `activeTrailIndex` (which tab is being edited). All trails in `draftTrails` are drawn on the map simultaneously, each in a distinct color from a fixed `TRAIL_COLORS` palette (cycled by array index); only the active tab's trail shows per-point number overlays and receives new points from map clicks. A trail with `id: null` in `draftTrails` hasn't been saved yet — the save button POSTs to create it and back-fills the returned `id`; a trail with an `id` already assigned PATCHes in place.
- `GET /api/oreum` (search/list) and `GET /api/oreum/progress` (aggregate) expose a collection-progress dashboard over four map_editor-collected fields only (`entrance`/`parking`/`restroom`/`trail` — CSV-derived `basic_info` fields are excluded since those are already mostly complete): `compute_progress()` in `app.py` marks each field done per-record (`coordinates.entrances`/`coordinates.parking` non-empty, `coordinates.restroom.lat/lng` both set, `trails` non-empty), `GET /api/oreum` adds `collected`/`total` (0–4) to each search result for the sidebar's per-item badge, and `GET /api/oreum/progress` returns dataset-wide counts per field (keyed by `PROGRESS_FIELD_LABELS`) for the top summary panel (`#progress-summary`). Both recompute from `data/oreum.json` on every call — there's no cached/stored progress state.
- `needs_trail(row)` in `app.py` is a derived flag (not a stored field) for `row.facilities.trail_info == "있음"` (CSV says a trail exists) but `row.trails` is still empty — i.e. known-collectible trails that haven't been walked/digitized yet. `GET /api/oreum?needs_trail_only=1` filters the search results to only these; each result also carries `needs_trail` so the sidebar can badge it regardless of the filter.
- `surface_type` is an int 1–5 matching the "노면상태" row of the manager grading table (관리자용 등급구분표): 1=단단·매끈한 포장(목재데크/콘크리트), 2=거의 흙길, 3=비교적 흙길(50~80%), 4=비교적 돌길(50~80%), 5=거의 돌길. Labels live server-side in `SURFACE_TYPE_LABELS` (`map_editor/app.py`) and are exposed via `GET /api/trail-surface-types`; the frontend fetches them at load instead of hardcoding, though it keeps a matching hardcoded copy as a pre-fetch fallback. These fields (plus geometry-derived slope/distance) feed the grading table's weighted difficulty formula — 경사도 0.286 / 거리 0.196 / 암릉·암반 0.193 / 노면상태 0.169 / 소요시간 0.154 — which is not yet implemented anywhere in this repo.
- Frontend: entrance/parking pins trigger a Kakao `Geocoder.coord2Address` reverse-geocode (see `reverseGeocodeAddress`) that fills the address input and is sent along with the coordinate save; the user can still hand-edit the text and save it separately via each item's "주소 저장" button without moving the pin. Restroom has no address (no reverse-geocode), but does have a `note` field editable via a dedicated input/save button in its section.
- `GET /api/oreum/{id}/linked` returns this oreum's linked oreums via `resolve_linked_oreums()` (`map_editor/app.py`) — the same one-directional-storage/bidirectional-resolution logic as `oreum_mcp/modules/data.py`'s function of the same name (duplicated rather than shared, since map_editor doesn't import `oreum_mcp`). `GET /api/oreum?linked_oreum_only=1` filters search results the same way `needs_trail_only` does; every result also carries `has_linked_oreum` for a sidebar badge regardless of the filter.
- `POST /api/oreum/{id}/trails/{trail_id}/copy-to/{target_id}` copies one trail's `path`/`surface_type`/`length_m`/`note` onto another oreum as a new trail (fresh `id` assigned on the target) — for linked-oreum pairs that physically share a trail, so it doesn't need to be redrawn on both sides.
- `POST /api/elevation-profile` takes a raw `{points: [{lat, lng}, ...]}` body (no `trail_id` — same "accept unsaved draft coordinates" pattern as trail creation, so an in-progress draft trail can be previewed before saving) and returns a resampled distance/elevation profile plus `total_distance_m`/`total_gain_m`, computed by draping the path over the DEM via `DemSampler`/`interpolate_path`/`compute_total_gain` imported from `scripts/compute_trail_difficulty.py` (geometry/sampling helpers only — the difficulty-scoring part of that script is not used here, see below). Raises 422 if any point falls outside the DEM bounds or lands on nodata.
- `scripts/add_linked_oreums_2026-08.py` is a one-off, already-applied migration that structured `notes.linked_oreums` for 6 records whose "연계" (linked-course) mention had only ever been left in free text (e.g. a trail's `note`) and never written into `notes.linked_oreums`. Idempotent (skips names already present) but shouldn't need re-running against a `data/oreum.json` already in this state.

## Running the MCP server (`oreum_mcp/`)

```
python oreum_mcp/app.py
```

`oreum_mcp/app.py` builds a plain FastAPI app (`modules/routes.py` + `modules/shared.py`), then converts it to an MCP server with `FastMCP.from_fastapi()` — **one FastAPI route = one MCP tool**, so adding a tool means adding a route in `register_routes()`, not writing separate MCP boilerplate. `modules/data.py` is the only module that touches `data/oreum.json` (`load_oreums()`, re-read fresh every call; path from `OREUM_DATA_PATH` env var or `data/oreum.json` relative to repo root).

Three tools currently exist, all read-only:
- `recommend_oreum` (`POST /recommend`) — filters by region (partial match against the full `address` string, not just the `region` field, so sub-district names like "한림"/"구좌" work), `difficulty`, `max_distance_km` (`gt=0`), `max_climb_time_min` (`gt=0`), `season`, free-text `keyword`, `access_open_only`, `restroom_required` (hard filter on `coordinates.restroom` having lat/lng), and `has_elderly_or_child_companion` (bool; if true and `difficulty` was left unspecified, a second `model_validator(mode="after")` defaults `difficulty` to `"쉬움"` — an explicitly-passed `difficulty` is respected as-is and never overridden). `difficulty` matches against `oreum_trail_difficulties()` (`modules/data.py`, see Trail-difficulty scoring below) — **not** `basic_info.difficulty` — so a record is included if **any** of its trails has that computed difficulty (an oreum with both an easy loop and a hard summit trail matches both `difficulty="쉬움"` and `difficulty="어려움"` queries). `RecommendRequest` has a `model_validator(mode="before")` that normalizes `""` → `None` and strips units off numeric-field strings (e.g. `"30분"` → `30`) since form-based MCP clients (Inspector) send those; the route also defaults its body param (`= RecommendRequest()`) so a no-argument call doesn't 422. Filtered candidates are always sorted by `completeness_score()` (`modules/data.py`) descending, tie-broken by `distance_km` ascending — "matches the filters, and has the most info collected, first." When **only** `region` is given (every other filter left at its default — a "region-only" recommendation), the route caps the result to 3 regardless of `limit`, since an unconstrained region query can otherwise return dozens of barely-collected oreums; `limit` defaults to 3 and otherwise caps normal filtered results at up to 50. `to_summary()` no longer trims fields — despite the name, it now returns the full record as-is (recommend results and `get_oreum_detail`/`recommend_linked_oreums` candidates all want the complete record, not a summary).
- `get_oreum_detail` (`POST /oreum`) — looks up by `id` or name via `find_oreum()` (exact name match, else unique partial match, else returns `candidates` for the LLM to disambiguate). Returns actual coordinate arrays (not counts) for entrances/parking/restroom/trails, flattened out of `basic_info`, via the shared `entrance_coords()`/`parking_coords()`/`restroom_coord()` helpers in `modules/data.py` (also used to build recommend-mode summaries). `parking_coords[].official` cross-checks `coordinates.parking` (map_editor-collected) against the CSV free-text `facilities.parking` via `is_official_parking()` — `false` means the CSV said "no official parking" so any collected coordinate is likely an informal shoulder/lot, not a real parking area. The top-level `difficulty` scalar has been replaced by `trail_difficulties` (`oreum_trail_difficulties()` — a list, one entry per trail that has a computed difficulty, so it can contain duplicate/differing values across multiple trails) since one CSV-style scalar can't represent an oreum whose trails differ in difficulty; each entry in the `trails` array also carries its own `difficulty` (`trail_difficulty()`, `modules/data.py`) alongside `path_coords`/`surface_type`/`length_m`/`note`.
- `recommend_linked_oreums` (`POST /linked`) — resolves linked oreums via `resolve_linked_oreums()` (`modules/data.py`), not just `record.notes.linked_oreums` directly. `notes.linked_oreums` is written one-directionally at collection time (e.g. 가메오름's notes list 누운오름, but 누운오름's notes don't list 가메오름 back), so `resolve_linked_oreums()` also scans every other record's `linked_oreums` for a reference back to this one and merges both directions at query time (dedup by id) — this way the pairing shows up no matter which side of the pair you look up. Each result carries a `direction` (`"forward"`: this record points at it; `"reverse"`: the other record points at this one) alongside the existing `resolved`/`name` fields. `LinkedOreumRequest.identifier` is optional: when given, behaves as above (top-level `base`/`linked`, unchanged shape for backward compatibility); when **omitted** (e.g. "연계코스로 갈 수 있는 오름 추천해줘" with no oreum named), the route instead scans every record for one with a non-empty `resolve_linked_oreums()` result (same bidirectional criterion `map_editor/app.py`'s `has_linked_oreum()` uses), sorts candidates by `completeness_score()` descending (tie-broken by `distance_km` ascending, same key as `recommend_oreum`'s region-only mode), and returns the top `limit` (default 3, max 10) as a `results` array of `{base, linked, map_url}` groups — the same per-oreum group shape either mode produces, built by the shared `_build_linked_group()` helper in `routes.py`. Both modes now strip coordinates out of each `linked[]` entry via `strip_coordinates()` (same helper `recommend_oreum` uses) and return a `map_url` (via the shared `_build_map_url()` helper, also used by `recommend_oreum`) pointing at the `/view` map page with the base oreum + its resolved linked oreums as marker ids, instead of embedding raw coordinates/trail paths in the response.

`access_open_only` deliberately only excludes oreums with an explicitly confirmed restrictive `notes.access.status` (`reservation_required`/`restricted`/`prohibited`); records with `status: null` (the large majority — most oreums have unclassified `notes`) pass through, since treating "unknown" as "unsafe" collapses the result set to near-zero. Don't tighten this without checking the current status-value distribution in `data/oreum.json` first — the two got conflated once already. It also now runs `has_access_restriction_keyword()` (`modules/data.py`) as a second, independent check: it searches the record's full JSON text for the literal string "출입제한" and excludes on a hit regardless of `notes.access.status` — added because some records (e.g. 살핀오름/성진이오름) have `notes: null` but carry "출입제한" inside `facilities.hours_fee` free text, which the status-based check alone misses.

`recommend_oreum`'s response also carries `map_url`: a link to a read-only "추천 오름 지도" page (`oreum_mcp/static/index.html`, mounted at `/view` on the outer wrapper `app` in `oreum_mcp/app.py` — a plain FastAPI route/StaticFiles mount added directly to `app`, not to `api_app`/`register_routes()`, so it isn't converted into an MCP tool) that plots the recommended oreums' peak coordinates as Kakao-map markers, built from a small `/view/data?ids=...` JSON endpoint (also on `app`, reads via `load_oreums()`, never writes). It's `null` when there are no results. This page is intentionally separate from `map_editor` — no save/edit capability, so exposing it externally carries none of `map_editor`'s write-access risk. The link's host comes from `OREUM_MCP_PUBLIC_URL` (falls back to `http://localhost:$OREUM_MCP_PORT`, which won't resolve for a remote MCP client) — set it to the server's externally-reachable address (e.g. the ngrok domain from `oreum_mcp/docker-compose.yml`'s `ngrok` service) for the link to actually open outside the host machine. The page's Kakao JS app key is the same one hardcoded in `map_editor/static/index.html`; whatever domain serves `/view` (localhost:11010 for dev, the public URL in production) must be separately registered in the Kakao Developers console's Web-platform domain allowlist, same as `map_editor`'s `localhost:8010` already is.

`completeness_score()` (`modules/data.py`) counts how many of 8 fields are populated on a record — trail-computed difficulty (`bool(oreum_trail_difficulties(record))`)/`distance_km`/`climb_time_min`/`recommended_season` (the last three still from `basic_info`) plus `coordinates.entrances`/`parking`/`restroom`/`trails` (map_editor-collected) — equally weighted (1 point each) for now, though a future pass may reweight these (e.g. trail/entrance/parking data is more practically useful than a recommended-season string); since the sort key lives in one place (`register_routes()` in `routes.py`), changing the weights there is enough to repropagate everywhere.

The `difficulty` field returned/filtered by `recommend_oreum`/`get_oreum_detail` is the **trail-level DEM-computed value** (see Trail-difficulty scoring below), not `basic_info.difficulty` — the CSV field is still stored on each record (untouched, ~41% null) but no longer read by any `oreum_mcp` tool; it's kept around for audit/comparison only (`scripts/compare_difficulty.py`/`analyze_mismatch.py`).

## Trail-difficulty scoring (server-integrated; scoring formula still has known gaps)

`scripts/compute_trail_difficulty.py` computes a slope-based difficulty score per trail by draping `trail.path` over a Copernicus DEM (`output_hh.tif`, gitignored but present locally — regeneratable, ~9.65MB at repo root, EPSG:4326, no reprojection needed): resamples the path every 10m (`interpolate_path`), bilinear-samples elevation at each point (`DemSampler.sample`), smooths with a moving average, then derives 4 metrics (total elevation gain via `compute_total_gain` — only counts contiguous ascending runs ≥3m to filter DEM noise, average/max slope %, share of steep (>30%) segments, total distance) that are weighted and summed into a 0–100 `score`, bucketed at 33/66 into `쉬움`/`보통`/`어려움`. Each trail's result is written in-place as `trail.difficulty_metrics = {total_gain, avg_slope, max_slope, steep_ratio, total_dist, score, difficulty}` (each `path` point also gets an `elevation` field). It's a **repeatable batch script**, not a one-off migration — it reads and overwrites both `data/oreum.json` (what `map_editor`/`oreum_mcp` actually read) and `data/oreum_with_elevation.json` (a duplicate output kept for `compare_difficulty.py`/`analyze_mismatch.py`, which diff the computed value against the old `basic_info.difficulty` for QA and are otherwise unaffected by this). **Must be re-run manually** (`python scripts/compute_trail_difficulty.py`) whenever `map_editor` collects new/changed trail paths — there's no automatic trigger, and a trail with no `path` (or one outside the DEM bounds/hitting nodata) is skipped and left without `difficulty_metrics` (`modules/data.py`'s `trail_difficulty()` returns `None` for these — `oreum_mcp` treats a trail with no computed difficulty as simply not matching any `difficulty` filter, same as before with null `basic_info.difficulty`).

Known gap (**not fixed** — deliberately deferred): the score doesn't normalize gain/slope by distance, so a long-but-gentle trail's `total_gain` term can outscore a short-but-steep trail's terms. The fuller grading-table formula mentioned in older notes (경사도/거리/암릉·암반/노면상태/소요시간 weights) is not what's implemented — 노면상태 (`trail.surface_type`) in particular is populated on only ~1% of trails today, too sparse to fold into scoring. The CSV-parsing `fix_coord_swap`/interpolation helpers this script's sibling scripts reuse can carry the same longitude/latitude-swap risk noted below if extended. `map_editor/app.py`'s `/api/elevation-profile` endpoint imports and reuses this script's `DEM_PATH`/`DemSampler`/`interpolate_path`/`compute_total_gain` — just the DEM-geometry plumbing, not `compute_score`/`compute_difficulty_metrics` — to show a live elevation profile while collecting a trail; it does not write `difficulty_metrics`, only `oreum_mcp`'s batch script does that.

## Schema notes (legacy `db/schema.sql` / SQLite path)

Only relevant if you're working with the standalone `data/oreum.db` pipeline, not `map_editor`.

- Coordinates are stored as separate `_lng`/`_lat` REAL columns per point (peak, entrance, restroom, parking), not as a combined geometry type.
- `build_oreum_db.py` corrects a known data bug: some rows have 정상_경도/정상_위도 (peak lng/lat) swapped in the source CSV. `fix_coord_swap()` detects the swap by checking whether the "longitude" value falls in Jeju's latitude range (32–35) and vice versa (125–128), and un-swaps it. Apply the same fix if extending coordinate parsing elsewhere (`scripts/build_oreum_json.py` reuses this same helper).
- `climb_time_min` is parsed from free-text Korean duration strings (e.g. `"30분~50분"`) via `parse_climb_time`; ranges are averaged and rounded.
- `region` is constrained to `'제주시'`/`'서귀포시'`; `difficulty` to `'쉬움'/'보통'/'어려움'`/NULL — keep new data conforming to these CHECK constraints.
