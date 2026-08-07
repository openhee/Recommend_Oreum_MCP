# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repo builds the **오름(Oreum) dataset** that will back a Jeju oreum-recommendation MCP server: `data/oreum.json`, a hand-editable JSON file derived from a raw CSV, plus a small FastAPI admin tool (`map_editor/`) for manually collecting POI coordinates (entrance/restroom/parking), entrance/parking addresses, and a trail path on top of Kakao Maps. There is no MCP server implemented in this repo yet — the data pipeline and coordinate-collection tooling come first.

`data/oreum.json` is the **only** data store the active pipeline reads/writes. `data/oreum.db` (SQLite) and its scripts (`build_oreum_db.py`, `export_oreum_json.py`, `sync_json_to_db.py`) are a legacy path kept for reference — nothing in `map_editor/` touches them anymore. `data/no_oreum.json` is an old, unused snapshot; don't read from it or treat it as a data source.

## Data pipeline

```
data/오름_dataset.csv (raw, CP949, 328 rows)
        │  scripts/build_oreum_json.py
        ▼
data/oreum.json (pretty-printed JSON array, one grouped object per oreum)
        ▲
        └── map_editor writes POI/address/trail edits straight into this file
```

- `python scripts/build_oreum_json.py` — **destructive**: regenerates `data/oreum.json` from the CSV only, imports the CSV-parsing helpers (`load_rows`, `fix_coord_swap`, `parse_climb_time`, etc.) from `scripts/build_oreum_db.py`. All map_editor-collected fields (`coordinates.entrance/parking/restroom`, `coordinates.entrance.address`, `coordinates.parking.address`, `trail.start`, `trail.path`) are reset to `null`/empty — it does not merge in anything from the existing `data/oreum.json`, `data/oreum.db`, or `data/no_oreum.json`. Only run this when you intend to start POI/trail collection over from scratch (e.g. the raw CSV changed).
- `map_editor/app.py` reads and writes `data/oreum.json` directly on every POI/address/trail save — there is no separate export/sync step.
- The legacy SQLite path (`build_oreum_db.py` → `data/oreum.db` → `export_oreum_json.py`/`sync_json_to_db.py`) still works standalone if you need it, but it is decoupled from `data/oreum.json` and from map_editor.

There is no requirements.txt/pyproject.toml in the repo; dependencies (`fastapi`, `uvicorn`, `pydantic`) must be available in the environment already.

## `data/oreum.json` record shape

Each record is grouped into sections rather than one flat object:

```
{
  "id", "source_seq", "name", "region", "address",   // 기본 식별 정보 (CSV 원본)
  "basic_info": { relative_height_m, elevation_m, area_sqm, shape_type, shape_direction,
                   difficulty, distance_km, climb_time_min, recommended_season },
  "coordinates": {
    "peak":     { lat, lng },
    "entrance": { lat, lng, address },   // address: 카카오 역지오코딩 자동 채움 + 수동 수정
    "parking":  { lat, lng, address },
    "restroom": { lat, lng }
  },
  "trail": { "start": "entrance" | "parking" | null, "path": [{lat, lng}, ...] | null,
              "surface_type": 1|2|3|4|5|null, "length_m": number|null },  // surface_type/length_m only present after a trail save (see below)
  "facilities": { surface, parking, restroom, trail_info, hours_fee },  // CSV 자유서술 텍스트
  "kakao_map_url", "notes", "created_at"
}
```

`facilities.parking`/`facilities.restroom` are free-text CSV descriptions (e.g. `"길가 주차"`, `"없음"`) — distinct from the collected `coordinates.parking`/`coordinates.restroom` points; don't conflate them.

## Running the map editor

```
python map_editor/app.py
```

Serves on `http://0.0.0.0:8010`: the static UI (`map_editor/static/index.html`, a single-file Kakao-Maps page) at `/`, and a small JSON API at `/api/oreum*`.

Key behavior to preserve when touching this code:
- All endpoints read/write `data/oreum.json` directly via `load_records()`/`save_records()` — no SQLite involved. Keep it that way.
- `PATCH /api/oreum/{id}/poi` (`entrance`/`restroom`/`parking`) sets `coordinates.<type>.lat/lng`, and `coordinates.<type>.address` when `address` is provided and the type is in `ADDRESSABLE_POI_TYPES` (`entrance`, `parking`). `DELETE /api/oreum/{id}/poi/{type}` clears the same fields.
- `PATCH /api/oreum/{id}/trail` sets `trail.start`/`trail.path`/`trail.surface_type` from a `{start, points: [{lat, lng}, ...], surface_type}` body, and server-computes `trail.length_m` (haversine sum over `points`, see `trail_length_meters`) — the client never sends a length. `DELETE /api/oreum/{id}/trail` clears all four fields. The frontend only calls PATCH on an explicit "등산로 저장" click — trail points are **not** saved per-click the way POI pins are, since a path is built from many clicks that shouldn't each persist a half-drawn route.
- `surface_type` is an int 1–5 matching the "노면상태" row of the manager grading table (관리자용 등급구분표): 1=단단·매끈한 포장(목재데크/콘크리트), 2=거의 흙길, 3=비교적 흙길(50~80%), 4=비교적 돌길(50~80%), 5=거의 돌길. Labels live server-side in `SURFACE_TYPE_LABELS` (`map_editor/app.py`) and are exposed via `GET /api/trail-surface-types`; the frontend fetches them at load instead of hardcoding, though it keeps a matching hardcoded copy as a pre-fetch fallback. These fields (plus geometry-derived slope/distance) feed the grading table's weighted difficulty formula — 경사도 0.286 / 거리 0.196 / 암릉·암반 0.193 / 노면상태 0.169 / 소요시간 0.154 — which is not yet implemented anywhere in this repo.
- Frontend: entrance/parking pins trigger a Kakao `Geocoder.coord2Address` reverse-geocode (see `reverseGeocodeAddress`) that fills the address input and is sent along with the coordinate save; the user can still hand-edit the text and save it separately via the "주소 저장" button without moving the pin. Trail-start (`입구`/`주차장`) defaults to whichever is farther-from-the-other by more than 150m (`recommendTrailStart`/`TRAIL_START_DISTANCE_THRESHOLD_M`), always overridable via the radio toggle.

## Schema notes (legacy `db/schema.sql` / SQLite path)

Only relevant if you're working with the standalone `data/oreum.db` pipeline, not `map_editor`.

- Coordinates are stored as separate `_lng`/`_lat` REAL columns per point (peak, entrance, restroom, parking), not as a combined geometry type.
- `build_oreum_db.py` corrects a known data bug: some rows have 정상_경도/정상_위도 (peak lng/lat) swapped in the source CSV. `fix_coord_swap()` detects the swap by checking whether the "longitude" value falls in Jeju's latitude range (32–35) and vice versa (125–128), and un-swaps it. Apply the same fix if extending coordinate parsing elsewhere (`scripts/build_oreum_json.py` reuses this same helper).
- `climb_time_min` is parsed from free-text Korean duration strings (e.g. `"30분~50분"`) via `parse_climb_time`; ranges are averaged and rounded.
- `region` is constrained to `'제주시'`/`'서귀포시'`; `difficulty` to `'쉬움'/'보통'/'어려움'`/NULL — keep new data conforming to these CHECK constraints.
