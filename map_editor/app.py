"""오름 POI(입구/화장실/주차장) 좌표 + 등산로 수집용 로컬 편집기.

카카오맵을 클릭해 좌표를 찍고 data/oreum.json에 즉시 저장하는 관리자 도구.
data/oreum.db는 전혀 읽거나 쓰지 않는다 — data/oreum.json이 유일한 저장소다.
정적 페이지(map_editor/static/index.html)와 API를 같은 프로세스에서 서빙해 CORS를 피한다.
"""
import json
import math
import os
import sys
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "data" / "oreum.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# scripts/compute_trail_difficulty.py의 DEM 샘플링/경로 보간 로직을 그대로 재사용한다
# (난이도 점수 계산 부분은 아직 리워크 중이라 가져오지 않음 — geometry/DEM 부분만 사용).
sys.path.insert(0, str(BASE_DIR / "scripts"))
from compute_trail_difficulty import DEM_PATH, DemSampler, compute_total_gain, interpolate_path  # noqa: E402

app = FastAPI(title="Oreum Map Editor")

_dem_sampler: DemSampler | None = None


def get_dem_sampler() -> DemSampler:
    global _dem_sampler
    if _dem_sampler is None:
        _dem_sampler = DemSampler(DEM_PATH)
    return _dem_sampler


class PoiUpdate(BaseModel):
    poi_type: Literal["restroom"]
    lat: float
    lng: float
    note: str | None = None


class EntranceUpdate(BaseModel):
    lat: float
    lng: float
    address: str | None = None
    note: str | None = None


class ParkingUpdate(BaseModel):
    lat: float
    lng: float
    address: str | None = None
    note: str | None = None


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
    points: list[TrailPoint]
    surface_type: Literal[1, 2, 3, 4, 5] | None = None
    note: str | None = None


class ElevationProfileRequest(BaseModel):
    points: list[TrailPoint]


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
    tmp_path = JSON_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, JSON_PATH)


def resolve_linked_oreums(row: dict, records: list[dict]) -> list[dict]:
    """row와 연계된 오름들을 양방향으로 찾는다.

    notes.linked_oreums는 저장 시 한쪽에만 적히는 단방향 데이터라서(예:
    가메오름 -> 누운오름은 적혀있지만 누운오름 -> 가메오름은 없음), row 자신의
    linked_oreums(forward)뿐 아니라 다른 레코드가 row를 linked_oreums로
    지목한 경우(reverse)도 함께 찾아 어느 쪽 오름을 보든 연계 관계가 보이게
    한다. oreum_mcp/modules/data.py의 resolve_linked_oreums()와 같은 로직 —
    map_editor는 oreum_mcp 모듈을 import하지 않는 별도 앱이라 여기 별도로 둔다.
    """
    name = row.get("name")
    by_name = {r.get("name"): r for r in records}
    seen_ids: set = set()
    results: list[dict] = []

    for linked_name in (row.get("notes") or {}).get("linked_oreums") or []:
        match = by_name.get(linked_name)
        if match is not None:
            if match.get("id") in seen_ids:
                continue
            seen_ids.add(match.get("id"))
        results.append({"id": match.get("id") if match else None, "name": linked_name, "direction": "forward", "resolved": match is not None})

    for other in records:
        if other.get("id") == row.get("id"):
            continue
        if name in ((other.get("notes") or {}).get("linked_oreums") or []):
            if other.get("id") in seen_ids:
                continue
            seen_ids.add(other.get("id"))
            results.append({"id": other.get("id"), "name": other.get("name"), "direction": "reverse", "resolved": True})

    return results


def find_record(records: list[dict], oreum_id: int) -> dict:
    for r in records:
        if r.get("id") == oreum_id:
            return r
    raise HTTPException(status_code=404, detail="oreum not found")


def find_trail(row: dict, trail_id: int) -> dict:
    for t in row.setdefault("trails", []):
        if t.get("id") == trail_id:
            return t
    raise HTTPException(status_code=404, detail="trail not found")


def find_entrance(row: dict, entrance_id: int) -> dict:
    for e in row["coordinates"].setdefault("entrances", []):
        if e.get("id") == entrance_id:
            return e
    raise HTTPException(status_code=404, detail="entrance not found")


def find_parking(row: dict, parking_id: int) -> dict:
    for p in row["coordinates"].setdefault("parking", []):
        if p.get("id") == parking_id:
            return p
    raise HTTPException(status_code=404, detail="parking not found")


SEARCH_FIELDS = ("id", "name", "region")

# 지도 편집기가 실제로 수집하는 4개 항목만 진행률에 반영한다. CSV 원본 필드(basic_info 등)는
# 이미 대부분 채워져 있어 진행률로서 의미가 없어 제외.
PROGRESS_FIELD_LABELS = {
    "entrance": "입구",
    "parking": "주차장",
    "restroom": "화장실",
    "trail": "등산로",
}


def compute_progress(row: dict) -> dict[str, bool]:
    coords = row.get("coordinates", {})
    restroom = coords.get("restroom", {})
    return {
        "entrance": bool(coords.get("entrances")),
        "parking": bool(coords.get("parking")),
        "restroom": restroom.get("lat") is not None and restroom.get("lng") is not None,
        "trail": bool(row.get("trails")),
    }


# CSV 원본상 등산로 정보가 "있음"이라고 적혀 있는데도 아직 map_editor로 등산로를 하나도
# 수집하지 못한 오름 — 수집 우선순위를 표시하기 위한 파생 플래그 (별도 저장 필드 아님).
def needs_trail(row: dict) -> bool:
    return row.get("facilities", {}).get("trail_info") == "있음" and not row.get("trails")


def reverse_linked_names(all_records: list[dict]) -> set:
    """다른 레코드가 linked_oreums로 지목한 이름들의 집합.

    notes.linked_oreums는 한쪽에만 적히는 단방향 데이터라, 검색 목록에서
    "연계오름 있음" 배지를 정확히 표시하려면 이 역방향까지 봐야 한다
    (resolve_linked_oreums와 같은 이유 — 목록 배지는 이름만 필요해 가볍게 집합으로 계산).
    """
    names = set()
    for r in all_records:
        names.update((r.get("notes") or {}).get("linked_oreums") or [])
    return names


def has_linked_oreum(row: dict, reverse_names: set) -> bool:
    return bool((row.get("notes") or {}).get("linked_oreums")) or row.get("name") in reverse_names


@app.get("/api/oreum")
def search_oreum(q: str = "", needs_trail_only: bool = False, linked_oreum_only: bool = False):
    all_records = load_records()
    reverse_names = reverse_linked_names(all_records)
    records = all_records
    if q:
        records = [r for r in records if q in (r.get("name") or "")]
    if needs_trail_only:
        records = [r for r in records if needs_trail(r)]
    if linked_oreum_only:
        records = [r for r in records if has_linked_oreum(r, reverse_names)]
    records = sorted(records, key=lambda r: r.get("name") or "")
    return [
        {
            **{k: r.get(k) for k in SEARCH_FIELDS},
            "facilities": {
                "restroom": r.get("facilities", {}).get("restroom"),
                "parking": r.get("facilities", {}).get("parking"),
            },
            "needs_trail": needs_trail(r),
            "has_linked_oreum": has_linked_oreum(r, reverse_names),
            "collected": sum(compute_progress(r).values()),
            "total": len(PROGRESS_FIELD_LABELS),
        }
        for r in records
    ]


@app.get("/api/oreum/progress")
def get_progress():
    records = load_records()
    fields = {key: {"label": label, "count": 0} for key, label in PROGRESS_FIELD_LABELS.items()}
    for r in records:
        progress = compute_progress(r)
        for key, done in progress.items():
            if done:
                fields[key]["count"] += 1
    return {"total": len(records), "fields": fields}


@app.get("/api/oreum/{oreum_id}")
def get_oreum(oreum_id: int):
    return find_record(load_records(), oreum_id)


@app.get("/api/oreum/{oreum_id}/linked")
def get_linked_oreums(oreum_id: int):
    records = load_records()
    row = find_record(records, oreum_id)
    return resolve_linked_oreums(row, records)


@app.patch("/api/oreum/{oreum_id}/poi")
def update_poi(oreum_id: int, body: PoiUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    coord = row["coordinates"][body.poi_type]
    coord["lat"] = body.lat
    coord["lng"] = body.lng
    if body.note is not None:
        coord["note"] = body.note
    save_records(records)
    return row


@app.delete("/api/oreum/{oreum_id}/poi/{poi_type}")
def clear_poi(oreum_id: int, poi_type: Literal["restroom"]):
    records = load_records()
    row = find_record(records, oreum_id)
    coord = row["coordinates"][poi_type]
    coord["lat"] = None
    coord["lng"] = None
    save_records(records)
    return row


@app.post("/api/oreum/{oreum_id}/entrances")
def create_entrance(oreum_id: int, body: EntranceUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    entrances = row["coordinates"].setdefault("entrances", [])
    new_id = max((e["id"] for e in entrances), default=0) + 1
    entrances.append(
        {"id": new_id, "lat": body.lat, "lng": body.lng, "address": body.address, "note": body.note}
    )
    save_records(records)
    return row


@app.patch("/api/oreum/{oreum_id}/entrances/{entrance_id}")
def update_entrance(oreum_id: int, entrance_id: int, body: EntranceUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    entrance = find_entrance(row, entrance_id)
    entrance["lat"] = body.lat
    entrance["lng"] = body.lng
    if body.address is not None:
        entrance["address"] = body.address
    if body.note is not None:
        entrance["note"] = body.note
    save_records(records)
    return row


@app.delete("/api/oreum/{oreum_id}/entrances/{entrance_id}")
def delete_entrance(oreum_id: int, entrance_id: int):
    records = load_records()
    row = find_record(records, oreum_id)
    entrance = find_entrance(row, entrance_id)
    row["coordinates"]["entrances"].remove(entrance)
    save_records(records)
    return row


@app.post("/api/oreum/{oreum_id}/parking")
def create_parking(oreum_id: int, body: ParkingUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    parking = row["coordinates"].setdefault("parking", [])
    new_id = max((p["id"] for p in parking), default=0) + 1
    parking.append(
        {"id": new_id, "lat": body.lat, "lng": body.lng, "address": body.address, "note": body.note}
    )
    save_records(records)
    return row


@app.patch("/api/oreum/{oreum_id}/parking/{parking_id}")
def update_parking(oreum_id: int, parking_id: int, body: ParkingUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    parking = find_parking(row, parking_id)
    parking["lat"] = body.lat
    parking["lng"] = body.lng
    if body.address is not None:
        parking["address"] = body.address
    if body.note is not None:
        parking["note"] = body.note
    save_records(records)
    return row


@app.delete("/api/oreum/{oreum_id}/parking/{parking_id}")
def delete_parking(oreum_id: int, parking_id: int):
    records = load_records()
    row = find_record(records, oreum_id)
    parking = find_parking(row, parking_id)
    row["coordinates"]["parking"].remove(parking)
    save_records(records)
    return row


@app.get("/api/trail-surface-types")
def get_trail_surface_types():
    return SURFACE_TYPE_LABELS


@app.post("/api/oreum/{oreum_id}/trails")
def create_trail(oreum_id: int, body: TrailUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    trails = row.setdefault("trails", [])
    new_id = max((t["id"] for t in trails), default=0) + 1
    trails.append(
        {
            "id": new_id,
            "path": [{"lat": p.lat, "lng": p.lng} for p in body.points],
            "surface_type": body.surface_type,
            "length_m": round(trail_length_meters(body.points), 1),
            "note": body.note,
        }
    )
    save_records(records)
    return row


@app.patch("/api/oreum/{oreum_id}/trails/{trail_id}")
def update_trail(oreum_id: int, trail_id: int, body: TrailUpdate):
    records = load_records()
    row = find_record(records, oreum_id)
    trail = find_trail(row, trail_id)
    trail["path"] = [{"lat": p.lat, "lng": p.lng} for p in body.points]
    trail["surface_type"] = body.surface_type
    trail["length_m"] = round(trail_length_meters(body.points), 1)
    trail["note"] = body.note
    save_records(records)
    return row


@app.delete("/api/oreum/{oreum_id}/trails/{trail_id}")
def delete_trail(oreum_id: int, trail_id: int):
    records = load_records()
    row = find_record(records, oreum_id)
    trail = find_trail(row, trail_id)
    row["trails"].remove(trail)
    save_records(records)
    return row


@app.post("/api/oreum/{oreum_id}/trails/{trail_id}/copy-to/{target_oreum_id}")
def copy_trail_to_oreum(oreum_id: int, trail_id: int, target_oreum_id: int):
    """연계오름끼리 물리적으로 같은 등산로를 공유하는 경우(예: A-B 연계코스), 한쪽에
    그린 등산로를 다시 그릴 필요 없이 그대로 상대 오름에도 복사해 넣는다.
    path/surface_type/length_m/note를 그대로 복사하고, target 쪽에서 새 id를
    발급한다 (기존 trails 배열 append 로직과 동일)."""
    if target_oreum_id == oreum_id:
        raise HTTPException(status_code=400, detail="복사 대상이 원본과 같은 오름입니다")

    records = load_records()
    source_row = find_record(records, oreum_id)
    trail = find_trail(source_row, trail_id)
    target_row = find_record(records, target_oreum_id)

    target_trails = target_row.setdefault("trails", [])
    new_id = max((t["id"] for t in target_trails), default=0) + 1
    target_trails.append(
        {
            "id": new_id,
            "path": list(trail.get("path") or []),
            "surface_type": trail.get("surface_type"),
            "length_m": trail.get("length_m"),
            "note": trail.get("note"),
        }
    )
    save_records(records)
    return target_row


@app.post("/api/elevation-profile")
def get_elevation_profile(body: ElevationProfileRequest):
    """등산로 경로(저장 전 초안이어도 무관)의 누적거리-고도 프로파일을 실시간 DEM 샘플링으로 계산한다.

    trail_id를 받지 않고 좌표 배열을 그대로 받는 것은 /api/oreum/{id}/trails 생성과 같은
    패턴 — map_editor에서 그리는 중인 트레일도 저장 전에 미리보기할 수 있게 하기 위함.
    """
    if len(body.points) < 2:
        raise HTTPException(status_code=422, detail="점이 2개 이상 있어야 고도 프로파일을 계산할 수 있습니다")

    dem = get_dem_sampler()
    path = [{"lat": p.lat, "lng": p.lng} for p in body.points]

    for p in path:
        if not dem.in_bounds(p["lat"], p["lng"]):
            raise HTTPException(status_code=422, detail="DEM 범위를 벗어난 좌표가 있어 고도를 계산할 수 없습니다")

    resampled = interpolate_path(path)
    elevations = [dem.sample(lat, lng) for lat, lng, _ in resampled]
    if any(e is None for e in elevations):
        raise HTTPException(status_code=422, detail="DEM 데이터가 없는(nodata) 좌표가 있어 고도를 계산할 수 없습니다")

    return {
        "points": [
            {"distance_m": round(dist, 1), "lat": lat, "lng": lng, "elevation": round(elev, 1)}
            for (lat, lng, dist), elev in zip(resampled, elevations)
        ],
        "total_distance_m": round(resampled[-1][2], 1),
        "total_gain_m": round(compute_total_gain(elevations), 1),
    }


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8010)
