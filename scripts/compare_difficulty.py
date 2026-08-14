"""기존 basic_info.difficulty와 새로 계산한 trail.difficulty_metrics.difficulty를 비교한다.

data/oreum_with_elevation.json을 읽어 오름별 원래 난이도(basic_info.difficulty)가
없는(null) 오름은 비교 대상에서 스킵하고, 나머지는 trail 단위로 원래/신규 난이도를
나란히 출력한다.
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_JSON = BASE_DIR / "data" / "oreum_with_elevation.json"


def main():
    with open(INPUT_JSON, encoding="utf-8") as f:
        records = json.load(f)

    rows = []
    skipped_no_original = 0
    skipped_no_trail_metrics = 0

    for record in records:
        original = record.get("basic_info", {}).get("difficulty")
        if not original:
            skipped_no_original += 1
            continue

        trails = record.get("trails") or []
        had_metrics = False
        for trail in trails:
            dm = trail.get("difficulty_metrics")
            if not dm:
                continue
            had_metrics = True
            rows.append(
                {
                    "id": record["id"],
                    "name": record["name"],
                    "trail_id": trail["id"],
                    "original": original,
                    "computed": dm["difficulty"],
                    "score": dm["score"],
                    "match": original == dm["difficulty"],
                }
            )
        if not had_metrics:
            skipped_no_trail_metrics += 1

    match_count = sum(1 for r in rows if r["match"])
    mismatch_count = len(rows) - match_count

    print(f"비교 대상 trail: {len(rows)}개")
    print(f"  일치: {match_count}개")
    print(f"  불일치: {mismatch_count}개")
    print(f"스킵 (원래 난이도 없음): {skipped_no_original}개 오름")
    print(f"스킵 (등산로/지표 없음): {skipped_no_trail_metrics}개 오름")

    print(f"\n{'id':>4} {'name':<14} {'trail':>5} {'원래':<6} {'신규':<6} {'score':>7}  일치")
    print("-" * 60)
    for r in rows:
        mark = "O" if r["match"] else "X"
        print(
            f"{r['id']:>4} {r['name']:<14} {r['trail_id']:>5} "
            f"{r['original']:<6} {r['computed']:<6} {r['score']:>7.1f}   {mark}"
        )

    print("\n=== 불일치 상세 ===")
    for r in rows:
        if not r["match"]:
            print(f"  {r['name']} (id={r['id']}, trail={r['trail_id']}): {r['original']} -> {r['computed']} (score={r['score']})")


if __name__ == "__main__":
    main()
