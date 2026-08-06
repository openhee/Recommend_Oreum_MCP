"""data/오름_dataset.csv -> data/oreum.db (SQLite) 로더.

원본 CSV(CP949)를 정제해 db/schema.sql의 oreum 테이블에 적재한다.
"""
import csv
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "오름_dataset.csv"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
DB_PATH = BASE_DIR / "data" / "oreum.db"

SHAPE_RE = re.compile(r"^(?P<type>[^()]+?)(\((?P<direction>[^)]+)\))?$")
CLIMB_SINGLE_RE = re.compile(r"^(\d+)\s*분$")
CLIMB_RANGE_RE = re.compile(r"^(\d+)\s*분\s*[~-]\s*(\d+)\s*분$")


def to_float(v: str) -> float | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def to_none(v: str) -> str | None:
    v = (v or "").strip()
    return v or None


def parse_shape(v: str) -> tuple[str | None, str | None]:
    v = (v or "").strip()
    if not v:
        return None, None
    m = SHAPE_RE.match(v)
    if not m:
        return v, None
    return m.group("type").strip(), (m.group("direction") or None)


def parse_climb_time(v: str) -> int | None:
    v = (v or "").strip()
    if not v:
        return None
    m = CLIMB_SINGLE_RE.match(v)
    if m:
        return int(m.group(1))
    m = CLIMB_RANGE_RE.match(v)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return round((lo + hi) / 2)
    return None


def fix_coord_swap(lng: float | None, lat: float | None) -> tuple[float | None, float | None]:
    """정상_경도/정상_위도 칸이 뒤바뀐 행(경도칸에 위도값)을 정정한다."""
    if lng is not None and lat is not None and 32 < lng < 35 and 125 < lat < 128:
        return lat, lng
    return lng, lat


def load_rows() -> list[dict]:
    with open(CSV_PATH, encoding="cp949", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    data = [r for r in rows[1:] if any(c.strip() for c in r)]
    records = []
    for r in data:
        shape_type, shape_direction = parse_shape(r[7])
        peak_lng, peak_lat = fix_coord_swap(to_float(r[8]), to_float(r[9]))
        entrance_lng, entrance_lat = fix_coord_swap(to_float(r[21]), to_float(r[22]))

        records.append(
            {
                "source_seq": int(r[0]),
                "name": r[1].strip(),
                "region": r[2].strip(),
                "address": to_none(r[3]),
                "relative_height_m": to_float(r[4]),
                "elevation_m": to_float(r[5]),
                "area_sqm": to_float(r[6]),
                "shape_type": shape_type,
                "shape_direction": shape_direction,
                "peak_lng": peak_lng,
                "peak_lat": peak_lat,
                "entrance_lng": entrance_lng,
                "entrance_lat": entrance_lat,
                "kakao_map_url": to_none(r[10]),
                "difficulty": to_none(r[11]),
                "distance_km": to_float(r[12]),
                "climb_time_min": parse_climb_time(r[13]),
                "surface": to_none(r[14]),
                "parking": to_none(r[15]),
                "restroom": to_none(r[16]),
                "trail_info": to_none(r[17]),
                "recommended_season": to_none(r[18]),
                "notes": to_none(r[19]),
                "hours_fee": to_none(r[20]),
            }
        )
    return records


def main() -> None:
    records = load_rows()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executemany(
            """
            INSERT INTO oreum (
                source_seq, name, region, address, relative_height_m, elevation_m,
                area_sqm, shape_type, shape_direction, peak_lng, peak_lat,
                entrance_lng, entrance_lat, kakao_map_url, difficulty, distance_km,
                climb_time_min, surface, parking, restroom, trail_info,
                recommended_season, notes, hours_fee
            ) VALUES (
                :source_seq, :name, :region, :address, :relative_height_m, :elevation_m,
                :area_sqm, :shape_type, :shape_direction, :peak_lng, :peak_lat,
                :entrance_lng, :entrance_lat, :kakao_map_url, :difficulty, :distance_km,
                :climb_time_min, :surface, :parking, :restroom, :trail_info,
                :recommended_season, :notes, :hours_fee
            )
            """,
            records,
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM oreum").fetchone()[0]
        print(f"적재 완료: {count}건 -> {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
