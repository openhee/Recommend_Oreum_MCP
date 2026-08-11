"""data/oreum.json: 1회성 마이그레이션.

1) coordinates.parking(단일 객체) -> coordinates.parking(배열)로 전환.
   좌표가 있으면 [{id, lat, lng, address, note: null}] 하나짜리 배열로, 없으면 빈 배열로.
2) coordinates.entrances[]/coordinates.parking[]/coordinates.restroom/trails[] 각 항목에
   note: null 필드를 추가 (설명 입력용, 기존 최상위 notes 필드와는 무관).

표준 파이프라인에는 편입되지 않는 1회성 스크립트. 이미 마이그레이션된 파일에 재실행해도
안전하지만(멱등), 다시 실행할 필요는 없다.
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "data" / "oreum.json"


def migrate_record(rec: dict) -> None:
    coords = rec["coordinates"]

    parking = coords.get("parking")
    if isinstance(parking, dict):
        if parking.get("lat") is not None and parking.get("lng") is not None:
            coords["parking"] = [
                {
                    "id": 1,
                    "lat": parking["lat"],
                    "lng": parking["lng"],
                    "address": parking.get("address"),
                    "note": None,
                }
            ]
        else:
            coords["parking"] = []
    elif isinstance(parking, list):
        for p in parking:
            p.setdefault("note", None)
    else:
        coords["parking"] = []

    for entrance in coords.get("entrances", []):
        entrance.setdefault("note", None)

    coords.setdefault("restroom", {}).setdefault("note", None)

    for trail in rec.get("trails", []):
        trail.setdefault("note", None)


def main() -> None:
    with open(JSON_PATH, encoding="utf-8") as f:
        records = json.load(f)

    for rec in records:
        migrate_record(rec)

    with_multi_parking = sum(1 for r in records if len(r["coordinates"]["parking"]) > 1)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"migrated {len(records)} records; {with_multi_parking} already have >1 parking spot")


if __name__ == "__main__":
    main()
