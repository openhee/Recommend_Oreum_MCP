"""오름 POI(입구/화장실/주차장) 좌표 수집용 로컬 편집기.

카카오맵을 클릭해 좌표를 찍고 data/oreum.db, json에 즉시 저장하는 관리자 도구.
정적 페이지(map_editor/static/index.html)와 API를 같은 프로세스에서 서빙해 CORS를 피한다.
"""
import json
import sqlite3
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "oreum.db"
JSON_PATH = BASE_DIR / "data" / "oreum.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

POI_COLUMNS = {
    "entrance": ("entrance_lng", "entrance_lat"),
    "restroom": ("restroom_lng", "restroom_lat"),
    "parking": ("parking_lng", "parking_lat"),
}

app = FastAPI(title="Oreum Map Editor")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class PoiUpdate(BaseModel):
    poi_type: Literal["entrance", "restroom", "parking"]
    lat: float
    lng: float


def load_records() -> list[dict]:
    """조회는 항상 data/oreum.json을 기준으로 한다 (쓰기는 DB+JSON 동시 반영)."""
    if not JSON_PATH.exists():
        return []
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def sync_row_to_json(row: dict) -> None:
    """DB에서 UPDATE된 오름 1건을 data/oreum.json에도 즉시 반영한다."""
    if JSON_PATH.exists():
        with open(JSON_PATH, encoding="utf-8") as f:
            records = json.load(f)
    else:
        records = []

    for i, r in enumerate(records):
        if r.get("id") == row["id"]:
            records[i] = row
            break
    else:
        records.append(row)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


SEARCH_FIELDS = ("id", "name", "region", "restroom", "parking", "peak_lat", "peak_lng")


@app.get("/api/oreum")
def search_oreum(q: str = ""):
    records = load_records()
    if q:
        records = [r for r in records if q in (r.get("name") or "")]
    records = sorted(records, key=lambda r: r.get("name") or "")
    return [{k: r.get(k) for k in SEARCH_FIELDS} for r in records]


@app.get("/api/oreum/{oreum_id}")
def get_oreum(oreum_id: int):
    for r in load_records():
        if r.get("id") == oreum_id:
            return r
    raise HTTPException(status_code=404, detail="oreum not found")


@app.patch("/api/oreum/{oreum_id}/poi")
def update_poi(oreum_id: int, body: PoiUpdate):
    lng_col, lat_col = POI_COLUMNS[body.poi_type]
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE oreum SET {lng_col} = ?, {lat_col} = ? WHERE id = ?",
            (body.lng, body.lat, oreum_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="oreum not found")
        conn.commit()
        row = dict(conn.execute("SELECT * FROM oreum WHERE id = ?", (oreum_id,)).fetchone())
        sync_row_to_json(row)
        return row
    finally:
        conn.close()


@app.delete("/api/oreum/{oreum_id}/poi/{poi_type}")
def clear_poi(oreum_id: int, poi_type: Literal["entrance", "restroom", "parking"]):
    lng_col, lat_col = POI_COLUMNS[poi_type]
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE oreum SET {lng_col} = NULL, {lat_col} = NULL WHERE id = ?",
            (oreum_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="oreum not found")
        conn.commit()
        row = dict(conn.execute("SELECT * FROM oreum WHERE id = ?", (oreum_id,)).fetchone())
        sync_row_to_json(row)
        return row
    finally:
        conn.close()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8010)
