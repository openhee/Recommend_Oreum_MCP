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


def to_summary(record: dict[str, Any]) -> dict[str, Any]:
    """추천 목록용 요약 — 좌표 배열 등 부피가 큰 필드는 뺀다."""
    basic = record.get("basic_info") or {}
    notes = record.get("notes") or {}
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "region": record.get("region"),
        "address": record.get("address"),
        "difficulty": basic.get("difficulty"),
        "distance_km": basic.get("distance_km"),
        "climb_time_min": basic.get("climb_time_min"),
        "recommended_season": basic.get("recommended_season"),
        "highlights": notes.get("highlights") or [],
        "access_status": (notes.get("access") or {}).get("status"),
        "kakao_map_url": record.get("kakao_map_url"),
    }


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
