# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Python FastAPI/FastMCP service for recommending Jeju oreum records.

- `oreum_mcp/`: MCP server package. `app.py` wires FastAPI into FastMCP; `modules/routes.py` defines tool/API behavior; `modules/data.py` loads and filters oreum data; `modules/shared.py` holds shared app setup.
- `oreum_mcp/test_tools.py`: manual MCP smoke tests that call a running server.
- `data/`: canonical local data files, including `oreum.json`, `oreum.db`, and the source CSV.
- `scripts/`: one-off and repeatable data build/migration utilities, such as `build_oreum_json.py` and `sync_json_to_db.py`.
- `map_editor/`: local FastAPI/static editor for updating coordinate and trail data in `data/oreum.json`.
- `db/schema.sql`, `docs/`, and `icon/`: database schema, session notes, and static assets.

## Build, Test, and Development Commands

Create an environment and install service dependencies:

```bash
cd oreum_mcp
python -m venv .venv
pip install -r requirements.txt
```

Run the MCP server locally:

```bash
python app.py --host 0.0.0.0 --port 11010 --reload
```

Run the map editor:

```bash
python ../map_editor/app.py
```

Run the manual MCP smoke tests after starting the server:

```bash
python test_tools.py
```

Docker Compose is available from `oreum_mcp/`:

```bash
docker compose up --build
```

## Coding Style & Naming Conventions

Use Python 3.11+ syntax, 4-space indentation, type hints for request/response models and helper functions, and `pathlib.Path` for filesystem paths. Keep route handlers thin and move reusable filtering/loading logic into `oreum_mcp/modules/`. Use snake_case for functions, variables, and JSON helper names. Preserve UTF-8 handling when reading or writing Korean data; use `encoding="utf-8"` and `ensure_ascii=False`.

## Testing Guidelines

There is no formal pytest suite yet. Treat `oreum_mcp/test_tools.py` as the current regression check for the three MCP tools: `recommend_oreum`, `get_oreum_detail`, and `recommend_linked_oreums`. Add focused tests when changing ranking, filtering, identifier matching, or output shape. If adding pytest, place tests under `tests/` and name files `test_*.py`.

## Commit & Pull Request Guidelines

Recent history uses short imperative messages and occasional Conventional Commit prefixes, for example `fix: Improve record saving mechanism` and `docs: ...`. Prefer `type: summary` for docs, fixes, and features when practical. Pull requests should describe behavior changes, list validation commands, note data migrations, and include screenshots only for `map_editor` UI changes.

## Data & Configuration Notes

The MCP service reads `data/oreum.json` by default and supports `OREUM_DATA_PATH` and `OREUM_MCP_PORT`. Avoid committing generated scratch files or local environment files. When changing data scripts, document the source file and expected output path.
