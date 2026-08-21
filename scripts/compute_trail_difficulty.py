"""오름 등산로에 DEM 고도값을 입히고 경사도 기반 난이도를 계산한다.

data/oreum.json의 각 trail.path에 elevation(m)을 추가하고, 경로를 따라
누적상승/경사도 지표를 계산해 difficulty_metrics를 붙여 저장한다.
data/oreum_with_elevation.json(비교/분석용, compare_difficulty.py·
analyze_mismatch.py가 읽음)과 data/oreum.json(map_editor/oreum_mcp가
실제로 읽는 파일) 양쪽에 동일한 결과를 쓴다 — map_editor로 새 등산로가
추가될 때마다 재실행해야 하는 배치 스크립트다(자동 트리거 없음).

DEM: output_hh.tif (Copernicus 30m DSM, EPSG:4326) — 좌표계 변환 불필요.
"""
import json
import math
from pathlib import Path

import numpy as np
import rasterio

BASE_DIR = Path(__file__).resolve().parent.parent
DEM_PATH = BASE_DIR / "output_hh.tif"
INPUT_JSON = BASE_DIR / "data" / "oreum.json"
OUTPUT_JSON = BASE_DIR / "data" / "oreum_with_elevation.json"

RESAMPLE_SPACING_M = 10.0
SMOOTH_WINDOW = 5
GAIN_THRESHOLD_M = 3.0
STEEP_SLOPE_PCT = 30.0
MAX_SLOPE_WINDOW = 5

SCORE_WEIGHTS = {
    "total_gain": (150.0, 35.0),
    "steep_ratio": (0.3, 30.0),
    "max_slope": (45.0, 20.0),
    "total_dist": (3000.0, 15.0),
}


# ---------------------------------------------------------------------------
# Step 1: DEM 샘플링
# ---------------------------------------------------------------------------
class DemSampler:
    def __init__(self, tif_path: Path):
        self._ds = rasterio.open(tif_path)
        self._band = self._ds.read(1)
        self._inv_transform = ~self._ds.transform
        self._height, self._width = self._band.shape
        self._nodata = self._ds.nodata
        self.bounds = self._ds.bounds

    def sample(self, lat: float, lng: float) -> float | None:
        """(lat, lng)의 고도를 bilinear 보간으로 반환. 범위 밖/nodata면 None."""
        col, row = self._inv_transform * (lng, lat)
        col0, row0 = math.floor(col), math.floor(row)
        if col0 < 0 or row0 < 0 or col0 + 1 >= self._width or row0 + 1 >= self._height:
            return None

        dx, dy = col - col0, row - row0
        v00 = self._band[row0, col0]
        v10 = self._band[row0, col0 + 1]
        v01 = self._band[row0 + 1, col0]
        v11 = self._band[row0 + 1, col0 + 1]

        if self._nodata is not None:
            for v in (v00, v10, v01, v11):
                if v == self._nodata:
                    return None

        value = (
            v00 * (1 - dx) * (1 - dy)
            + v10 * dx * (1 - dy)
            + v01 * (1 - dx) * dy
            + v11 * dx * dy
        )
        return float(value)

    def in_bounds(self, lat: float, lng: float) -> bool:
        return (
            self.bounds.left <= lng <= self.bounds.right
            and self.bounds.bottom <= lat <= self.bounds.top
        )

    def close(self):
        self._ds.close()


# ---------------------------------------------------------------------------
# Step 2: 경로 보간 (10m 간격)
# ---------------------------------------------------------------------------
def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def interpolate_path(path: list[dict], spacing_m: float = RESAMPLE_SPACING_M) -> list[tuple[float, float, float]]:
    """path([{lat,lng},...])를 spacing_m 간격으로 재샘플링.

    반환: (lat, lng, cum_dist_m) 튜플 리스트. 마지막 원본 정점까지 정확히 포함한다.
    """
    if not path:
        return []
    if len(path) == 1:
        return [(path[0]["lat"], path[0]["lng"], 0.0)]

    resampled = [(path[0]["lat"], path[0]["lng"], 0.0)]
    cum_dist = 0.0
    dist_since_last = 0.0

    for a, b in zip(path, path[1:]):
        seg_dist = haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
        if seg_dist <= 0:
            continue
        traveled = 0.0
        while dist_since_last + (seg_dist - traveled) >= spacing_m:
            step = spacing_m - dist_since_last
            traveled += step
            t = traveled / seg_dist
            lat = a["lat"] + (b["lat"] - a["lat"]) * t
            lng = a["lng"] + (b["lng"] - a["lng"]) * t
            cum_dist += step
            resampled.append((lat, lng, cum_dist))
            dist_since_last = 0.0
        remainder = seg_dist - traveled
        dist_since_last += remainder
        cum_dist += remainder

    last = path[-1]
    if resampled[-1][0] != last["lat"] or resampled[-1][1] != last["lng"]:
        resampled.append((last["lat"], last["lng"], cum_dist))

    return resampled


# ---------------------------------------------------------------------------
# Step 3: 고도 스무딩 (이동평균)
# ---------------------------------------------------------------------------
def moving_average(values: list[float], window: int = SMOOTH_WINDOW) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if len(arr) < window:
        return arr
    pad = window // 2
    padded = np.pad(arr, (pad, pad), mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


# ---------------------------------------------------------------------------
# Step 4: 난이도 지표 계산
# ---------------------------------------------------------------------------
def compute_total_gain(elevations: np.ndarray, threshold_m: float = GAIN_THRESHOLD_M) -> float:
    """연속 상승분이 threshold_m 이상인 구간만 합산 (노이즈성 미세 상승 제외)."""
    total = 0.0
    run = 0.0
    for a, b in zip(elevations, elevations[1:]):
        diff = b - a
        if diff > 0:
            run += diff
        else:
            if run >= threshold_m:
                total += run
            run = 0.0
    if run >= threshold_m:
        total += run
    return total


def compute_difficulty_metrics(points: list[tuple[float, float, float]], elevations: np.ndarray) -> dict:
    total_dist = points[-1][2] if points else 0.0
    total_gain = compute_total_gain(elevations)
    avg_slope = (total_gain / total_dist * 100) if total_dist > 0 else 0.0

    seg_slopes = []
    for i in range(len(points) - 1):
        seg_dist = points[i + 1][2] - points[i][2]
        if seg_dist <= 0:
            continue
        seg_slopes.append((elevations[i + 1] - elevations[i]) / seg_dist * 100)

    if seg_slopes:
        if len(seg_slopes) >= MAX_SLOPE_WINDOW:
            window_avgs = [
                sum(seg_slopes[i : i + MAX_SLOPE_WINDOW]) / MAX_SLOPE_WINDOW
                for i in range(len(seg_slopes) - MAX_SLOPE_WINDOW + 1)
            ]
        else:
            window_avgs = [sum(seg_slopes) / len(seg_slopes)]
        max_slope = max(window_avgs)
        steep_ratio = sum(1 for s in seg_slopes if s > STEEP_SLOPE_PCT) / len(seg_slopes)
    else:
        max_slope = 0.0
        steep_ratio = 0.0

    return {
        "total_gain": round(total_gain, 1),
        "avg_slope": round(avg_slope, 2),
        "max_slope": round(max_slope, 2),
        "steep_ratio": round(steep_ratio, 3),
        "total_dist": round(total_dist, 1),
    }


# ---------------------------------------------------------------------------
# Step 5: 종합 난이도 점수 -> 등급
# ---------------------------------------------------------------------------
def compute_score(metrics: dict) -> tuple[float, str]:
    score = 0.0
    for key, (denom, weight) in SCORE_WEIGHTS.items():
        term = (metrics[key] / denom) * weight
        term = max(0.0, min(term, 100.0))
        score += term

    if score < 33:
        difficulty = "쉬움"
    elif score < 66:
        difficulty = "보통"
    else:
        difficulty = "어려움"

    return round(score, 2), difficulty


# ---------------------------------------------------------------------------
# Step 6: trail 처리 (고도 부여 + 지표 계산)
# ---------------------------------------------------------------------------
def process_trail(trail: dict, dem: DemSampler, oreum_name: str) -> bool:
    """trail을 in-place로 갱신. 성공하면 True, 스킵하면 False."""
    path = trail.get("path")
    if not path:
        print(f"  [SKIP] {oreum_name} trail {trail.get('id')}: path 없음")
        return False

    for p in path:
        if not dem.in_bounds(p["lat"], p["lng"]):
            print(f"  [SKIP] {oreum_name} trail {trail.get('id')}: 좌표가 DEM 범위 밖")
            return False

    points = interpolate_path(path)
    raw_elevations = [dem.sample(lat, lng) for lat, lng, _ in points]
    if any(e is None for e in raw_elevations):
        print(f"  [SKIP] {oreum_name} trail {trail.get('id')}: DEM 샘플링 실패(범위/nodata)")
        return False

    smoothed = moving_average(raw_elevations)

    # 원본 path 정점에는 보간 없이 직접 샘플링한 고도를 붙인다 (표시용 원본 좌표 보존).
    for p in path:
        elev = dem.sample(p["lat"], p["lng"])
        p["elevation"] = round(elev, 1) if elev is not None else None

    metrics = compute_difficulty_metrics(points, smoothed)
    score, difficulty = compute_score(metrics)
    trail["difficulty_metrics"] = {**metrics, "score": score, "difficulty": difficulty}
    trail["_interpolated_point_count"] = len(points)  # 검증 출력용, 최종 저장 전 제거
    return True


def main():
    print(f"DEM 로딩: {DEM_PATH}")
    dem = DemSampler(DEM_PATH)
    print(f"DEM bounds: {dem.bounds}")

    with open(INPUT_JSON, encoding="utf-8") as f:
        records = json.load(f)

    target_record = None  # 검증 출력용 (가세오름, id=7)
    processed = 0
    skipped_oreums = 0

    for record in records:
        trails = record.get("trails") or []
        if not trails:
            continue

        any_ok = False
        for trail in trails:
            ok = process_trail(trail, dem, record.get("name", f"id={record.get('id')}"))
            any_ok = any_ok or ok
            processed += 1 if ok else 0

        if not any_ok:
            skipped_oreums += 1

        if record.get("id") == 7:
            target_record = record

    dem.close()

    print(f"\n처리 완료: trail {processed}개 갱신, 전체 trail이 스킵된 오름 {skipped_oreums}개")

    # Step 7: 검증 출력 (가세오름 id=7)
    if target_record is not None:
        print("\n" + "=" * 60)
        print(f"검증: {target_record['name']} (id=7)")
        print(f"기존 난이도(basic_info.difficulty): {target_record.get('basic_info', {}).get('difficulty')}")
        for trail in target_record.get("trails", []):
            print(f"\n-- trail id {trail.get('id')} --")
            path = trail.get("path") or []
            print(f"정점별 고도값 (원본 {len(path)}개):")
            for i, p in enumerate(path):
                print(f"  [{i}] lat={p['lat']:.6f} lng={p['lng']:.6f} elevation={p.get('elevation')}")

            interp_count = trail.pop("_interpolated_point_count", None)
            if interp_count is not None:
                print(f"보간 후 정점 수: {interp_count}")

            dm = trail.get("difficulty_metrics")
            if dm:
                print("난이도 지표:")
                for k in ("total_gain", "avg_slope", "max_slope", "steep_ratio", "total_dist", "score"):
                    print(f"  {k}: {dm[k]}")
                print(f"최종 난이도: {dm['difficulty']}  (기존: {target_record.get('basic_info', {}).get('difficulty')})")
            else:
                print("difficulty_metrics 없음 (스킵된 trail)")
    else:
        print("\n[WARN] id=7 레코드를 찾지 못했습니다 (검증 출력 생략)")

    # 검증 출력용 임시 필드 정리
    for record in records:
        for trail in record.get("trails") or []:
            trail.pop("_interpolated_point_count", None)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {OUTPUT_JSON}")

    # map_editor/oreum_mcp가 실제로 읽는 파일에도 반영 — 이 스크립트가 이제
    # oreum.json의 trail.difficulty_metrics를 채우는 (재실행 가능한) 배치 스텝이다.
    with open(INPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {INPUT_JSON}")


if __name__ == "__main__":
    main()
