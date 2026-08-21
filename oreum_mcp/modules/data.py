"""data/oreum.json 로딩 + 조회 헬퍼.

이 MCP 서버는 map_editor와 동일하게 data/oreum.json을 유일한 데이터 소스로
읽는다 (읽기 전용, 쓰지 않음). 매 요청마다 파일을 새로 읽어 최신 상태를
반영한다 — map_editor에서 수집을 계속하는 동안 서버 재시작 없이도 반영되게
하기 위함.
"""
import copy
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


def strip_coordinates(record: dict[str, Any]) -> dict[str, Any]:
    """recommend_oreum처럼 map_url(지도 페이지)이 함께 나가는 응답에서, 위경도
    숫자값을 뺀 사본을 반환한다. 좌표는 이제 지도 페이지가 마커/등산로로
    시각적으로 보여주므로, LLM에게 넘기는 텍스트 응답에 그대로 중복해서 실을
    필요가 없다(특히 trails[].path는 점이 많으면 응답이 커진다) — 주소/메모/
    난이도 등 좌표가 아닌 필드는 그대로 남긴다. 원본 record는 건드리지 않는다
    (load_oreums()가 매 요청 새로 읽어오긴 하지만, candidates 정렬 등 같은
    요청 안에서 원본을 재사용할 수 있어 깊은 복사 후 수정한다)."""
    r = copy.deepcopy(record)
    coords = r.get("coordinates") or {}
    coords.pop("peak", None)
    for e in coords.get("entrances") or []:
        e.pop("lat", None)
        e.pop("lng", None)
    for p in coords.get("parking") or []:
        p.pop("lat", None)
        p.pop("lng", None)
    restroom = coords.get("restroom")
    if restroom:
        restroom.pop("lat", None)
        restroom.pop("lng", None)
    for t in r.get("trails") or []:
        t.pop("path", None)
    return r


def trail_difficulty(trail: dict[str, Any]) -> Optional[str]:
    """trail 하나의 DEM 기반 난이도 라벨(쉬움/보통/어려움). 미계산이면 None.

    scripts/compute_trail_difficulty.py가 배치로 채워두는 trail.difficulty_metrics.difficulty를
    읽는다 — path가 없거나 DEM 범위/nodata로 스킵된 trail은 이 필드 자체가 없다."""
    return (trail.get("difficulty_metrics") or {}).get("difficulty")


def oreum_trail_difficulties(record: dict[str, Any]) -> list[str]:
    """record의 등산로들 중 난이도가 계산된 것들의 라벨 목록 (중복 포함, trail 개수만큼).

    오름 하나에 등산로가 여러 개면 서로 다른 난이도가 섞여 나올 수 있다(예: 쉬운
    둘레길 + 어려운 정상코스) — basic_info.difficulty(CSV, 오름당 값 하나)를 대체하는
    새 난이도 출처. 이 record가 basic_info.difficulty를 갖고 있어도 여기서는 보지 않는다."""
    return [d for t in (record.get("trails") or []) if (d := trail_difficulty(t)) is not None]


def completeness_score(record: dict[str, Any]) -> int:
    """난이도(등산로 DEM 계산값)/거리/소요시간/추천계절(basic_info) + 입구/주차장/화장실/
    등산로(map_editor 수집 좌표), 8개 항목 중 채워진 개수(0~8)를 센다.

    "지역명만 넘어온" 추천 모드에서 쓴다. 화장실 좌표 수집률이 워낙 낮아서(예:
    서귀포 144개 중 15개, 한림읍 16개 중 0개) 8개를 전부 요구하는 하드 필터를 쓰면
    지역에 따라 결과가 통째로 0건이 되는 경우가 잦았다 — 그래서 있음/없음으로 걸러내는
    대신 점수로 매겨 "그나마 정보가 가장 많은 오름"을 우선 추천하는 방식으로 바꿨다.
    """
    basic = record.get("basic_info") or {}
    coords = record.get("coordinates") or {}
    restroom = coords.get("restroom") or {}

    checks = [
        bool(oreum_trail_difficulties(record)),
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


def resolve_linked_oreums(
    record: dict[str, Any],
    all_records: list[dict[str, Any]],
) -> list[tuple[Optional[dict[str, Any]], str, str]]:
    """record와 연계된 오름들을 양방향으로 찾는다.

    notes.linked_oreums는 저장 시 한쪽에만 적히는 단방향 데이터라서(예:
    가메오름 -> 누운오름은 적혀있지만 누운오름 -> 가메오름은 없음), record
    자신의 linked_oreums(forward)뿐 아니라 다른 레코드의 linked_oreums에
    record 이름이 적혀있는 경우(reverse)도 함께 찾아 어느 쪽 오름으로
    조회하든 연계 관계가 보이게 한다. 데이터 저장 방식 자체는 바꾸지 않고
    조회 시점에만 양방향으로 합친다.

    반환: (매칭된 레코드 또는 None(미해결), 이름, direction) 튜플 리스트.
    direction은 "forward"(record 자신의 linked_oreums에 적힌 이름) 또는
    "reverse"(다른 레코드가 record를 linked_oreums로 지목). 같은 오름이
    양쪽에서 겹치면(상호 연계로 이미 양쪽에 적혀있는 경우) 한 번만 남긴다.
    """
    name = record.get("name")
    by_name = {r.get("name"): r for r in all_records}

    seen_ids: set = set()
    results: list[tuple[Optional[dict[str, Any]], str, str]] = []

    for linked_name in (record.get("notes") or {}).get("linked_oreums") or []:
        match = by_name.get(linked_name)
        if match is not None and match.get("id") in seen_ids:
            continue
        if match is not None:
            seen_ids.add(match.get("id"))
        results.append((match, linked_name, "forward"))

    for other in all_records:
        if other.get("id") == record.get("id"):
            continue
        if name in ((other.get("notes") or {}).get("linked_oreums") or []):
            if other.get("id") in seen_ids:
                continue
            seen_ids.add(other.get("id"))
            results.append((other, other.get("name"), "reverse"))

    return results


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
