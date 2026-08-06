"""data/oreum.db -> data/oreum.json 내보내기.

DB의 모든 컬럼/행을 그대로 JSON 배열로 덤프한다 (사람이 직접 열어서 읽고 고치기 쉽도록 pretty-print).
map_editor에서 좌표를 찍을 때마다 자동으로 갱신되는 파일과 동일한 포맷.
수동으로 다시 뽑고 싶을 때(DB를 스크립트로 재생성한 직후 등) 이 스크립트를 실행한다.
"""
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "oreum.db"
JSON_PATH = BASE_DIR / "data" / "oreum.json"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM oreum ORDER BY id").fetchall()
        records = [dict(r) for r in rows]
    finally:
        conn.close()

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"내보내기 완료: {len(records)}건 -> {JSON_PATH}")


if __name__ == "__main__":
    main()
