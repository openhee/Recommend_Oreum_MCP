"""data/oreum.json: 1회성 마이그레이션.

1) coordinates.entrance(단일 객체) -> coordinates.entrances(배열)로 전환.
   좌표가 있으면 [{id, lat, lng, address}] 하나짜리 배열로, 없으면 빈 배열로.
2) trails[].start 필드 제거 (등산로는 더 이상 입구/주차장 라벨을 갖지 않음. 등산로가
   어디서 시작하는지는 path의 첫 점으로만 표현됨).

표준 파이프라인에는 편입되지 않는 1회성 스크립트.
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "data" / "oreum.json"


def migrate_record(rec: dict) -> None:
    entrance = rec["coordinates"].pop("entrance", None)
    if entrance is not None and entrance.get("lat") is not None:
        rec["coordinates"]["entrances"] = [
            {"id": 1, "lat": entrance["lat"], "lng": entrance["lng"], "address": entrance.get("address")}
        ]
    else:
        rec["coordinates"]["entrances"] = []

    for trail in rec.get("trails", []):
        trail.pop("start", None)


def main() -> None:
    with open(JSON_PATH, encoding="utf-8") as f:
        records = json.load(f)

    for rec in records:
        migrate_record(rec)

    with_entrances = sum(1 for r in records if r["coordinates"]["entrances"])

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"migrated {len(records)} records; {with_entrances} now have a non-empty entrances array")


if __name__ == "__main__":
    main()
