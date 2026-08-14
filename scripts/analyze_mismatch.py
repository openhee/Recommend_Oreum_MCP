"""불일치(원래 난이도 vs 신규 계산 난이도) 패턴을 분석한다.

- 방향별(쉬움->보통 등) 개수
- 각 방향에서 4개 가중치 항목 중 어떤 항목이 점수를 밀어올렸는지(항목별 평균 기여도)
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_JSON = BASE_DIR / "data" / "oreum_with_elevation.json"

WEIGHTS = {
    "total_gain": (150.0, 35.0),
    "steep_ratio": (0.3, 30.0),
    "max_slope": (45.0, 20.0),
    "total_dist": (3000.0, 15.0),
}


def term_contribs(dm):
    contribs = {}
    for key, (denom, weight) in WEIGHTS.items():
        term = (dm[key] / denom) * weight
        contribs[key] = max(0.0, min(term, 100.0))
    return contribs


def main():
    with open(INPUT_JSON, encoding="utf-8") as f:
        records = json.load(f)

    mismatches = []
    for record in records:
        original = record.get("basic_info", {}).get("difficulty")
        if not original:
            continue
        for trail in record.get("trails") or []:
            dm = trail.get("difficulty_metrics")
            if not dm:
                continue
            if dm["difficulty"] != original:
                mismatches.append((record["name"], record["id"], trail["id"], original, dm))

    by_direction = {}
    for name, oid, tid, original, dm in mismatches:
        key = f"{original} -> {dm['difficulty']}"
        by_direction.setdefault(key, []).append((name, oid, tid, dm))

    print(f"전체 불일치: {len(mismatches)}건\n")
    for direction, items in sorted(by_direction.items(), key=lambda kv: -len(kv[1])):
        print(f"[{direction}]  {len(items)}건")
        avg_contrib = {k: 0.0 for k in WEIGHTS}
        avg_score = 0.0
        for _, _, _, dm in items:
            c = term_contribs(dm)
            for k in WEIGHTS:
                avg_contrib[k] += c[k]
            avg_score += dm["score"]
        n = len(items)
        avg_score /= n
        for k in avg_contrib:
            avg_contrib[k] /= n
        print(f"  평균 score: {avg_score:.1f}")
        print("  항목별 평균 기여도 (가중치 반영 후, 0~100):")
        for k, v in sorted(avg_contrib.items(), key=lambda kv: -kv[1]):
            print(f"    {k:<12}: {v:5.1f}")
        # 이 방향에서 가장 큰 기여를 한 항목 상위 3건 예시
        examples = sorted(items, key=lambda it: -it[3]["score"])[:3]
        print("  예시:")
        for name, oid, tid, dm in examples:
            c = term_contribs(dm)
            top_key = max(c, key=c.get)
            print(
                f"    {name}(id={oid}): score={dm['score']} | "
                f"total_gain={dm['total_gain']}m avg_slope={dm['avg_slope']}% "
                f"max_slope={dm['max_slope']}% steep_ratio={dm['steep_ratio']} "
                f"total_dist={dm['total_dist']}m | 최대 기여항목={top_key}({c[top_key]:.1f})"
            )
        print()


if __name__ == "__main__":
    main()
