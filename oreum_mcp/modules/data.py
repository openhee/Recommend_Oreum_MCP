"""data/oreum.json 로딩 + 조회 헬퍼.

이 MCP 서버는 map_editor와 동일하게 data/oreum.json을 유일한 데이터 소스로
읽는다 (읽기 전용, 쓰지 않음). 매 요청마다 파일을 새로 읽어 최신 상태를
반영한다 — map_editor에서 수집을 계속하는 동안 서버 재시작 없이도 반영되게
하기 위함.
"""
import json
import os
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# 로컬 실행 시 repo 루트 기준 data/oreum.json을 자동으로 찾는다.
# Docker 컨테이너에서는 디렉터리 구조가 달라지므로 OREUM_DATA_PATH로 오버라이드한다
# (docker-compose.yml에서 data/ 디렉터리를 마운트하고 이 값을 지정).
JSON_PATH = Path(os.getenv("OREUM_DATA_PATH") or (BASE_DIR / "data" / "oreum.json"))


def load_oreums() -> list[dict[str, Any]]:
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def entrance_coords(record: dict[str, Any]) -> list[dict[str, Any]]:
    coords = record.get("coordinates") or {}
    return [
        {"lat": e.get("lat"), "lng": e.get("lng"), "address": e.get("address"), "note": e.get("note")}
        for e in (coords.get("entrances") or [])
    ]


def parking_coords(record: dict[str, Any]) -> list[dict[str, Any]]:
    coords = record.get("coordinates") or {}
    facilities = record.get("facilities") or {}
    official = is_official_parking(facilities.get("parking"))
    return [
        {
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "address": p.get("address"),
            "note": p.get("note"),
            "official": official,
        }
        for p in (coords.get("parking") or [])
    ]


def restroom_coord(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    restroom = (record.get("coordinates") or {}).get("restroom") or {}
    if restroom.get("lat") is None:
        return None
    return {"lat": restroom.get("lat"), "lng": restroom.get("lng"), "note": restroom.get("note")}


def to_summary(record: dict[str, Any]) -> dict[str, Any]:
    """레코드를 data/oreum.json에 저장된 그대로 반환한다 (요약/축약 없음).

    이름은 과거 "요약본만 반환" 시절의 흔적으로 남아있지만, 지금은 recommend_oreum
    결과와 get_oreum_detail/recommend_linked_oreums의 candidates 양쪽 모두 필터링된
    오름의 전체 정보(basic_info/coordinates/facilities/trails/notes 등)를 그대로
    내려달라는 요청에 따라 record를 그대로 반환한다."""
    return record


def completeness_score(record: dict[str, Any]) -> int:
    """난이도/거리/소요시간/추천계절(basic_info) + 입구/주차장/화장실/등산로(map_editor
    수집 좌표), 8개 항목 중 채워진 개수(0~8)를 센다.

    "지역명만 넘어온" 추천 모드에서 쓴다. 화장실 좌표 수집률이 워낙 낮아서(예:
    서귀포 144개 중 15개, 한림읍 16개 중 0개) 8개를 전부 요구하는 하드 필터를 쓰면
    지역에 따라 결과가 통째로 0건이 되는 경우가 잦았다 — 그래서 있음/없음으로 걸러내는
    대신 점수로 매겨 "그나마 정보가 가장 많은 오름"을 우선 추천하는 방식으로 바꿨다.
    """
    basic = record.get("basic_info") or {}
    coords = record.get("coordinates") or {}
    restroom = coords.get("restroom") or {}

    checks = [
        basic.get("difficulty") is not None,
        basic.get("distance_km") is not None,
        basic.get("climb_time_min") is not None,
        bool(basic.get("recommended_season")),
        bool(coords.get("entrances")),
        bool(coords.get("parking")),
        restroom.get("lat") is not None and restroom.get("lng") is not None,
        bool(record.get("trails")),
    ]
    return sum(checks)


def has_access_restriction_keyword(record: dict[str, Any]) -> bool:
    """레코드 전체 JSON 텍스트 어디에든 "출입제한"이 있으면 True.

    notes.access.status로 분류된 것만 걸러내는 access_open_only 기본 로직은
    notes가 아예 미분류(null)인 레코드를 놓친다 — 예: "살핀오름"/"성진이오름"은
    notes가 null이지만 facilities.hours_fee에 "출입제한: 탐방불가"가 그대로
    적혀있다. status 필드 위치에 의존하지 않고 레코드 전체를 뒤져서 이런
    누락을 잡는다."""
    return "출입제한" in json.dumps(record, ensure_ascii=False)


def is_official_parking(facilities_parking_text: Optional[str]) -> Optional[bool]:
    """CSV 원본 facilities.parking 텍스트로 정식 주차장 여부를 판단.

    "없음" 계열 문구가 있으면 False(정식 주차장 아님 — coordinates.parking에
    좌표가 있어도 갓길/공터 등 비공식 공간일 가능성이 높다는 뜻), 텍스트가
    아예 없으면 판단 불가라 None, 그 외(전용 주차장/소규모 주차 가능 등)는 True.
    """
    if not facilities_parking_text:
        return None
    return "없음" not in facilities_parking_text


def find_oreum(
    records: list[dict[str, Any]],
    identifier: str,
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """id(숫자 문자열) 또는 이름으로 오름 하나를 찾는다.

    반환: (정확히 하나 찾은 경우 그 레코드, 그 외의 경우 후보 목록(부분일치 이름들))
    정확히 하나를 못 찾으면 첫 번째 값은 None이고, 두 번째 값에 이름이
    부분일치하는 후보들이 담긴다 (LLM이 재질의할 수 있도록).
    """
    identifier = identifier.strip()

    if identifier.isdigit():
        oreum_id = int(identifier)
        for r in records:
            if r.get("id") == oreum_id:
                return r, []
        return None, []

    exact = [r for r in records if r.get("name") == identifier]
    if len(exact) == 1:
        return exact[0], []

    partial = [r for r in records if identifier in (r.get("name") or "")]
    if len(partial) == 1:
        return partial[0], []

    return None, partial
