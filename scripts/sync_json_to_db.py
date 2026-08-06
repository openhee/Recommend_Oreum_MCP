"""data/oreum.json -> data/oreum.db 반영.

JSON 파일을 텍스트 에디터로 직접 고친 뒤(참고글, 등산로 정보 등 자유서술 필드 수정 등)
그 변경 내용을 DB에 반영하고 싶을 때 실행하는 수동 동기화 스크립트.
map_editor에서 좌표를 찍는 것처럼 실시간으로 자동 반영되지는 않으므로,
JSON을 수정한 뒤에는 이 스크립트를 직접 실행해야 한다.

각 레코드는 `id` 기준으로 매칭되며, JSON에 있는 모든 필드를 그대로 UPDATE한다.
`id`가 없는 레코드나 DB에 없는 id는 건너뛰고 경고를 출력한다.
"""
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "oreum.db"
JSON_PATH = BASE_DIR / "data" / "oreum.json"


def main() -> None:
    with open(JSON_PATH, encoding="utf-8") as f:
        records = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM pragma_table_info('oreum')")
        valid_columns = {row[0] for row in cur.fetchall()}

        updated, skipped = 0, 0
        for record in records:
            oreum_id = record.get("id")
            if oreum_id is None:
                skipped += 1
                continue

            fields = {k: v for k, v in record.items() if k != "id" and k in valid_columns}
            if not fields:
                skipped += 1
                continue

            set_clause = ", ".join(f"{col} = ?" for col in fields)
            result = cur.execute(
                f"UPDATE oreum SET {set_clause} WHERE id = ?",
                (*fields.values(), oreum_id),
            )
            if result.rowcount == 0:
                print(f"경고: id={oreum_id} 를 DB에서 찾지 못해 건너뜀")
                skipped += 1
            else:
                updated += 1

        conn.commit()
        print(f"동기화 완료: {updated}건 반영, {skipped}건 건너뜀")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
