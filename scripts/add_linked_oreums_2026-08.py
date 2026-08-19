"""연계오름(linked_oreums) 구조화 — 2026-08 일회성 패치.

trails[].note 등에만 "연계" 문구가 남아있고 notes.linked_oreums에는
반영되지 않았던 6개 레코드를 구조화한다. 기존 데이터(밧돌오름->안돌오름,
소록산->대록산 등)와 동일하게 단방향으로만 채운다 — 연계 문구가 실제로
적힌 오름에만 상대 오름 이름을 추가.

한 번 실행하면 끝나는 마이그레이션이라 재실행해도 안전하도록(이미 들어간
이름은 중복 추가하지 않음) 만들었지만, data/oreum.json이 이미 이 상태라면
다시 돌릴 필요 없음.
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "data" / "oreum.json"

# id -> 추가할 연계 오름 이름 목록
LINKS_TO_ADD: dict[int, list[str]] = {
    2: ["누운오름"],          # 가메오름
    40: ["당오름(송당)"],      # 괭이모루
    181: ["괴오름"],          # 북돌아진오름
    303: ["큰노리손이"],       # 족은노리손이
    309: ["좌보미알오름"],      # 좌보미
    310: ["좌보미"],          # 좌보미알오름
}

EMPTY_NOTES = {
    "raw_note": None,
    "access": {"status": None, "detail": None, "fee": None, "hours": None},
    "trail_condition": None,
    "caution": [],
    "recommend_for": None,
    "highlights": [],
    "directions": None,
    "trivia": None,
    "linked_oreums": [],
}


def load_records() -> list[dict]:
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_records(records: list[dict]) -> None:
    tmp_path = JSON_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, JSON_PATH)


def main() -> None:
    records = load_records()
    by_id = {r.get("id"): r for r in records}

    for oreum_id, names_to_add in LINKS_TO_ADD.items():
        record = by_id.get(oreum_id)
        if record is None:
            print(f"[SKIP] id={oreum_id} 레코드를 찾지 못함")
            continue

        if record.get("notes") is None:
            record["notes"] = dict(EMPTY_NOTES)
            record["notes"]["access"] = dict(EMPTY_NOTES["access"])
            record["notes"]["caution"] = []
            record["notes"]["highlights"] = []
            record["notes"]["linked_oreums"] = []

        linked = record["notes"].setdefault("linked_oreums", [])
        for name in names_to_add:
            if name not in linked:
                linked.append(name)

        print(f"id={oreum_id} {record.get('name')}: linked_oreums={linked}")

    save_records(records)
    print(f"\n저장 완료: {JSON_PATH}")


if __name__ == "__main__":
    main()
