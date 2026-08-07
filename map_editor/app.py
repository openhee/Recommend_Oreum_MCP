"""오름 POI(입구/화장실/주차장) 좌표 + 등산로 수집용 로컬 편집기.

카카오맵을 클릭해 좌표를 찍고 data/oreum.json에 즉시 저장하는 관리자 도구.
data/oreum.db는 전혀 읽거나 쓰지 않는다 — data/oreum.json이 유일한 저장소다.
정적 페이지(map_editor/static/index.html)와 API를 같은 프로세스에서 서빙해 CORS를 피한다.
"""
import json
import math
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "data" / "oreum.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# 주소를 함께 관리하는 POI 타입 (입구/주차장은 네비게이션용 주소가 있음, 화장실은 없음)
ADDRESSABLE_POI_TYPES = ("entrance", "parking")

app = FastAPI(title="Oreum Map Editor")


class PoiUpdate(BaseModel):
    poi_type: Literal["entrance", "restroom", "parking"]
    lat: float
    lng: float
    address: str | None = None


class TrailPoint(BaseModel):
    lat: float
    lng: float


# 관리자용 등급구분표의 "노면상태" 행 (1~5점): 목재데크·콘크리트 같은 단단한 포장부터
# 대부분 돌로 이루어진 길까지, 난이도 점수 계산에 쓰이는 5단계 구분
SURFACE_TYPE_LABELS = {
    1: "단단·매끈한 포장 (목재데크, 콘크리트 등)",
    2: "거의 대부분 흙으로 이루어진 길",
    3: "비교적 흙으로 이루어진 길 (50~80%)",
    4: "비교적 돌로 이루어진 길 (50~80%)",
    5: "거의 대부분 돌로 이루어진 길",
}


class TrailUpdate(BaseModel):
    start: Literal["entrance", "parking"]
    points: list[TrailPoint]
    surface_type: Literal[1, 2, 3, 4, 5] | None = None


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def trail_length_meters(points: list[TrailPoint]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += haversine_meters(a.lat, a.lng, b.lat, b.lng)
    return total


def load_records() -> list[dict]:
    if not JSON_PATH.exists():
        return []
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_records(records: list[dict]) -> None:
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def find_record(records: list[dict], oreum_id: int) -> dict:
    for r in records:
        if r.get("id") == oreum_id:
            return r
    raise HTTPException(status_code=404, detail="oreum not found")


SEARCH_FIELDS = ("id", "name", "region")


@app.get("/api/oreum")
def search_oreum(q: str = ""):
    records = load_records()
    if q:
        records = [r for r in records if q in (r.get("name") or "")]
    records = sorted(records, key=lambda r: r.get("name") or "")
    return [
        {
            **{k: r.get(k) for k in SEARCH_FIELDS},
            "facilities": {
                "restroom": r.get("facilities", {}).get("restroom"),
                "parking": r.get("facilities", {}).get("parking"),
            },
        }
        for r in records
    ]


@app.get("/api/oreum/{oreum_id}")
def get_oreum(oreum_id: int):
    return find_record(load_records(), oreum_id)


@app.patch("/api/oreum/{oreum_id}/poi")
def update_poi(oreum_id: int, body: PoiUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    coord = row["coordinates"][body.poi_type]
    coord["lat"] = body.lat
    coord["lng"] = body.lng
    if body.poi_type in ADDRESSABLE_POI_TYPES and body.address is not None:
        coord["address"] = body.address
    save_records(records)
    return row


@app.delete("/api/oreum/{oreum_id}/poi/{poi_type}")
def clear_poi(oreum_id: int, poi_type: Literal["entrance", "restroom", "parking"]):
    records = load_records()
    row = find_record(records, oreum_id)
    coord = row["coordinates"][poi_type]
    coord["lat"] = None
    coord["lng"] = None
    if poi_type in ADDRESSABLE_POI_TYPES:
        coord["address"] = None
    save_records(records)
    return row


@app.get("/api/trail-surface-types")
def get_trail_surface_types():
    return SURFACE_TYPE_LABELS


@app.patch("/api/oreum/{oreum_id}/trail")
def update_trail(oreum_id: int, body: TrailUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    row["trail"]["start"] = body.start
    row["trail"]["path"] = [{"lat": p.lat, "lng": p.lng} for p in body.points]
    row["trail"]["surface_type"] = body.surface_type
    row["trail"]["length_m"] = round(trail_length_meters(body.points), 1)
    save_records(records)
    return row


@app.delete("/api/oreum/{oreum_id}/trail")
def clear_trail(oreum_id: int):
    records = load_records()
    row = find_record(records, oreum_id)
    row["trail"]["start"] = None
    row["trail"]["path"] = None
    row["trail"]["surface_type"] = None
    row["trail"]["length_m"] = None
    save_records(records)
    return row


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8010)
