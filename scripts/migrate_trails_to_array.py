"""data/oreum.json: 단일 `trail` 객체 -> `trails` 배열로 1회성 마이그레이션.

각 레코드의 `trail` 키를 읽어 path가 있으면 trails: [{id: 1, start, path,
surface_type, length_m}]로, 없으면 trails: []로 바꾸고 `trail` 키를 제거한다.
표준 파이프라인(build_oreum_json.py)에는 편입되지 않는 1회성 스크립트 — 재실행 시
이미 `trails` 필드가 있는 레코드는 건드리지 않는다.
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "data" / "oreum.json"


def migrate_record(rec: dict) -> bool:
    if "trail" not in rec:
        return False
    trail = rec.pop("trail")
    if trail.get("path"):
        rec["trails"] = [
            {
                "id": 1,
                "start": trail.get("start"),
                "path": trail.get("path"),
                "surface_type": trail.get("surface_type"),
                "length_m": trail.get("length_m"),
            }
        ]
    else:
        rec["trails"] = []
    return True


def main() -> None:
    with open(JSON_PATH, encoding="utf-8") as f:
        records = json.load(f)

    migrated = sum(migrate_record(r) for r in records)
    with_trails = sum(1 for r in records if r.get("trails"))

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"migrated {migrated}/{len(records)} records; {with_trails} now have a non-empty trails array")


if __name__ == "__main__":
    main()
