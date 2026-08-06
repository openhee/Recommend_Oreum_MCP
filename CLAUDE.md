# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repo builds the **오름(Oreum) dataset** that will back a Jeju oreum-recommendation MCP server: a SQLite database (`data/oreum.db`) derived from a raw CSV, plus a small FastAPI admin tool (`map_editor/`) for manually collecting POI coordinates (entrance/restroom/parking) on top of Kakao Maps. There is no MCP server implemented in this repo yet — the data pipeline and coordinate-collection tooling come first.

Note: `app.py` at the repo root is an unrelated leftover (a "Web Search MCP Server" wrapping SearXNG) that imports from a `modules/` package which does not exist in this repo — it will not run as-is and is not part of the oreum pipeline. Don't treat it as a template for new work unless the user asks about it specifically.

## Data pipeline

Three scripts move data between three representations. Run them from the repo root with Python 3.10+ (uses `X | None` type hints).

```
data/오름_dataset.csv (raw, CP949, 328 rows)
        │  scripts/build_oreum_db.py   (rebuild DB from scratch)
        ▼
data/oreum.db (SQLite, table `oreum`, schema in db/schema.sql)
        │  scripts/export_oreum_json.py  (dump DB -> JSON)
        ▼
data/oreum.json (pretty-printed, hand-editable mirror of the DB)
        │  scripts/sync_json_to_db.py   (write hand-edits back)
        ▲
        └── map_editor keeps DB and JSON in sync automatically on every POI save
```

- `python scripts/build_oreum_db.py` — **destructive**: deletes and recreates `data/oreum.db` from `db/schema.sql`, reloads all rows from the CSV. Coordinate/POI edits made via `map_editor` or `sync_json_to_db.py` are lost when this is re-run, since the CSV has no POI columns. Only run when the raw CSV itself changes.
- `python scripts/export_oreum_json.py` — regenerates `data/oreum.json` from the current DB. Use after rebuilding the DB, or any time you want a fresh full dump.
- `python scripts/sync_json_to_db.py` — after hand-editing free-text fields (참고글, 등산로 정보, etc.) directly in `data/oreum.json`, run this to push those edits back into the DB. Matches rows by `id`; only updates columns present in the JSON record and valid in the schema.
- `map_editor/app.py` writes POI coordinates to **both** the DB and `data/oreum.json` immediately (see `sync_row_to_json`), so no manual export/sync step is needed after using the map editor.

There is no requirements.txt/pyproject.toml in the repo; dependencies (`fastapi`, `uvicorn`, `pydantic`) must be available in the environment already.

## Running the map editor

```
python map_editor/app.py
```

Serves on `http://0.0.0.0:8010`: the static UI (`map_editor/static/index.html`, a single-file Kakao-Maps page) at `/`, and a small JSON API at `/api/oreum*` for searching oreums and PATCH/DELETE-ing POI coordinates (`entrance`, `restroom`, `parking`).

Key behavior to preserve when touching this code:
- `GET` endpoints always read from `data/oreum.json` (source of truth for reads); `PATCH`/`DELETE` write to the SQLite DB first, then call `sync_row_to_json` to mirror the updated row into the JSON file. Keep both stores consistent if you extend this API — don't write to one without the other.
- `POI_COLUMNS` maps the three POI types to their `*_lng`/`*_lat` column pairs; add new POI types here and in the `Literal` types on `PoiUpdate` / `clear_poi` together.

## Schema notes (`db/schema.sql`)

- Coordinates are stored as separate `_lng`/`_lat` REAL columns per point (peak, entrance, restroom, parking), not as a combined geometry type.
- `build_oreum_db.py` corrects a known data bug: some rows have 정상_경도/정상_위도 (peak lng/lat) swapped in the source CSV. `fix_coord_swap()` detects the swap by checking whether the "longitude" value falls in Jeju's latitude range (32–35) and vice versa (125–128), and un-swaps it. Apply the same fix if extending coordinate parsing elsewhere.
- `climb_time_min` is parsed from free-text Korean duration strings (e.g. `"30분~50분"`) via `parse_climb_time`; ranges are averaged and rounded.
- `region` is constrained to `'제주시'`/`'서귀포시'`; `difficulty` to `'쉬움'/'보통'/'어려움'`/NULL — keep new data conforming to these CHECK constraints.
