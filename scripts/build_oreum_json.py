"""data/오름_dataset.csv -> data/oreum.json 직접 생성 (DB 미사용, 완전히 새로 생성).

원본 CSV만을 기준으로 각 오름을 구역별(기본정보/좌표/등산로/편의시설)로 정리한 JSON을
새로 만든다. data/oreum.db, data/no_oreum.json은 읽지도 참조하지도 않는다 — 화장실/주차장
좌표, 입구·주차장 주소, 등산로 경로는 모두 비운 상태로 시작해서 map_editor로 다시 채운다.
"""
import datetime
import json
from pathlib import Path

from build_oreum_db import load_rows

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "data" / "oreum.json"


def build_record(csv_rec: dict, oreum_id: int, now: str) -> dict:
    return {
        "id": oreum_id,
        "name": csv_rec["name"],
        "region": csv_rec["region"],
        "address": csv_rec["address"],
        "basic_info": {
            "relative_height_m": csv_rec["relative_height_m"],
            "elevation_m": csv_rec["elevation_m"],
            "area_sqm": csv_rec["area_sqm"],
            "shape_type": csv_rec["shape_type"],
            "shape_direction": csv_rec["shape_direction"],
            "difficulty": csv_rec["difficulty"],
            "distance_km": csv_rec["distance_km"],
            "climb_time_min": csv_rec["climb_time_min"],
            "recommended_season": csv_rec["recommended_season"],
        },
        "coordinates": {
            "peak": {"lat": csv_rec["peak_lat"], "lng": csv_rec["peak_lng"]},
            "entrances": (
                [{"id": 1, "lat": csv_rec["entrance_lat"], "lng": csv_rec["entrance_lng"], "address": None}]
                if csv_rec["entrance_lat"] is not None
                else []
            ),
            "parking": {"lat": None, "lng": None, "address": None},
            "restroom": {"lat": None, "lng": None},
        },
        "trails": [],  # [{"id":.., "path":.., "surface_type":.., "length_m":..}, ...]
        "facilities": {
            "surface": csv_rec["surface"],
            "parking": csv_rec["parking"],
            "restroom": csv_rec["restroom"],
            "trail_info": csv_rec["trail_info"],
            "hours_fee": csv_rec["hours_fee"],
        },
        "kakao_map_url": csv_rec["kakao_map_url"],
        "notes": csv_rec["notes"],
        "created_at": now,
    }


def main() -> None:
    csv_records = load_rows()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    output = [build_record(rec, i, now) for i, rec in enumerate(csv_records, start=1)]

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"생성 완료: {len(output)}건 -> {JSON_PATH}")


if __name__ == "__main__":
    main()
