# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repo builds the **오름(Oreum) dataset** that will back a Jeju oreum-recommendation MCP server: `data/oreum.json`, a hand-editable JSON file derived from a raw CSV, plus a small FastAPI admin tool (`map_editor/`) for manually collecting POI coordinates (entrance/restroom/parking), entrance/parking addresses, and a trail path on top of Kakao Maps. There is no MCP server implemented in this repo yet — the data pipeline and coordinate-collection tooling come first.

`data/oreum.json` is the **only** data store the active pipeline reads/writes. `data/oreum.db` (SQLite) and its scripts (`build_oreum_db.py`, `export_oreum_json.py`, `sync_json_to_db.py`) are a legacy path kept for reference — nothing in `map_editor/` touches them anymore. `data/no_oreum.json` is an old, unused snapshot; don't read from it or treat it as a data source.

## Commands

- `python map_editor/app.py` — start the map editor on `http://0.0.0.0:8010`. Check the port isn't already in use first (`netstat -ano | findstr :8010` on Windows), and stop your own instance when done.
- `python scripts/build_oreum_json.py` — rebuild `data/oreum.json` from the raw CSV. **Destructive** to all map_editor-collected data; see below before running.
- No requirements.txt/pyproject.toml, no test suite, and no lint config exist in this repo — dependencies (`fastapi`, `uvicorn`, `pydantic`, `requests`) must already be available in the environment.

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
- `surface_type` is an int 1–5 matching the "노면상태" row of the manager grading table (관리자용 등급구분표): 1=단단·매끈한 포장(목재데크/콘크리트), 2=거의 흙길, 3=비교적 흙길(50~80%), 4=비교적 돌길(50~80%), 5=거의 돌길. Labels live server-side in `SURFACE_TYPE_LABELS` (`map_editor/app.py`) and are exposed via `GET /api/trail-surface-types`; the frontend fetches them at load instead of hardcoding, though it keeps a matching hardcoded copy as a pre-fetch fallback. These fields (plus geometry-derived slope/distance) feed the grading table's weighted difficulty formula — 경사도 0.286 / 거리 0.196 / 암릉·암반 0.193 / 노면상태 0.169 / 소요시간 0.154 — which is not yet implemented anywhere in this repo.
- Frontend: entrance/parking pins trigger a Kakao `Geocoder.coord2Address` reverse-geocode (see `reverseGeocodeAddress`) that fills the address input and is sent along with the coordinate save; the user can still hand-edit the text and save it separately via each item's "주소 저장" button without moving the pin. Restroom has no address (no reverse-geocode), but does have a `note` field editable via a dedicated input/save button in its section.

## Schema notes (legacy `db/schema.sql` / SQLite path)

Only relevant if you're working with the standalone `data/oreum.db` pipeline, not `map_editor`.

- Coordinates are stored as separate `_lng`/`_lat` REAL columns per point (peak, entrance, restroom, parking), not as a combined geometry type.
- `build_oreum_db.py` corrects a known data bug: some rows have 정상_경도/정상_위도 (peak lng/lat) swapped in the source CSV. `fix_coord_swap()` detects the swap by checking whether the "longitude" value falls in Jeju's latitude range (32–35) and vice versa (125–128), and un-swaps it. Apply the same fix if extending coordinate parsing elsewhere (`scripts/build_oreum_json.py` reuses this same helper).
- `climb_time_min` is parsed from free-text Korean duration strings (e.g. `"30분~50분"`) via `parse_climb_time`; ranges are averaged and rounded.
- `region` is constrained to `'제주시'`/`'서귀포시'`; `difficulty` to `'쉬움'/'보통'/'어려움'`/NULL — keep new data conforming to these CHECK constraints.
