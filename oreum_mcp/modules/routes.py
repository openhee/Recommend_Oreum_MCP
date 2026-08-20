# FastAPI 라우트 1개는 MCP 도구 1개입니다.

import os
import re
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

from .data import (
    completeness_score,
    entrance_coords,
    find_oreum,
    has_access_restriction_keyword,
    load_oreums,
    parking_coords,
    resolve_linked_oreums,
    restroom_coord,
    strip_coordinates,
    to_summary,
)

_LEADING_NUMBER = re.compile(r"-?\d+(\.\d+)?")

# 사람이나 LLM이 폼/자연어로 채우다 보면 숫자 필드에도 "30분", "1.5km"처럼
# 단위가 붙은 문자열이 들어올 수 있다. 순수 숫자를 요구하는 대신, 앞의 숫자만
# 뽑아 쓰는 게 422로 막는 것보다 실사용에 낫다고 판단.
_NUMERIC_FIELDS = {"max_distance_km", "max_climb_time_min"}


def _normalize_request_dict(data: Any) -> Any:
    """MCP Inspector 등 폼 기반 클라이언트는 비워둔 optional 필드도 ""로 보낸다.
    "" 그대로면 float/int 필드가 파싱 에러(422)를 내므로 None으로 바꾸고,
    숫자 필드에 붙은 단위 텍스트("30분", "1.5km")는 앞의 숫자만 추출한다."""
    if not isinstance(data, dict):
        return data

    result = {}
    for k, v in data.items():
        if v == "":
            result[k] = None
        elif k in _NUMERIC_FIELDS and isinstance(v, str):
            match = _LEADING_NUMBER.match(v.strip())
            result[k] = match.group() if match else v
        else:
            result[k] = v
    return result


class RecommendRequest(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        return _normalize_request_dict(data)

    region: Optional[str] = Field(
        default=None,
        description=(
            "지역/위치 필터. 주소(address) 문자열에 대한 부분일치. "
            "'제주시'/'서귀포시' 같은 큰 단위는 물론, '한림'/'구좌'/'표선'처럼 "
            "읍·면·동 단위 지명으로도 필터링 가능 (예: '한림주변' 요청 -> '한림'만 넣으면 됨)."
        ),
    )
    difficulty: Optional[str] = Field(
        default=None,
        description="난이도 필터. '쉬움' / '보통' / '어려움' 중 하나. 생략하면 전체 난이도.",
    )
    max_distance_km: Optional[float] = Field(
        default=None,
        gt=0,
        description="편도 등산로 거리(km) 상한. 예: 1.0이면 1km 이하인 오름만.",
    )
    max_climb_time_min: Optional[int] = Field(
        default=None,
        gt=0,
        description="예상 등반 소요시간(분) 상한. 예: 30이면 30분 이내로 오를 수 있는 오름만.",
    )
    season: Optional[str] = Field(
        default=None,
        description="추천 계절 키워드 (예: '봄', '가을'). recommended_season 텍스트에 포함된 오름만 반환.",
    )
    keyword: Optional[str] = Field(
        default=None,
        description="자유 키워드. 오름 이름, 하이라이트(전망/포토존 등), 추천 대상 설명에서 검색.",
    )
    access_open_only: bool = Field(
        default=False,
        description=(
            "true면 access_status가 명시적으로 제한된(예약 필요/통제/금지) 오름만 제외하고 반환 "
            "(안전 우선 — 확실히 제한이 확인된 곳은 절대 추천하지 않음). 출입 제한 여부가 아직 "
            "미확인/미분류인 오름(대다수)은 위험이 확인된 게 아니므로 제외하지 않고 포함시킨다. "
            "추가로 notes.access.status 분류와 무관하게, 레코드 어디에든 '출입제한'이라는 "
            "문구가 있으면(미분류 레코드의 facilities.hours_fee 등에 남아있는 경우 포함) 무조건 제외한다."
        ),
    )
    restroom_required: bool = Field(
        default=False,
        description="true면 화장실 좌표(coordinates.restroom)가 수집된 오름만 반환한다 (하드 필터).",
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=50,
        description="반환할 최대 개수 (기본 3, 최대 50).",
    )


class OreumIdentifierRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="오름 이름(예: '가세오름') 또는 oreum.json의 id(숫자를 문자열로 전달, 예: '7').",
    )


def register_routes(app: FastAPI) -> None:
    @app.post(
        "/recommend",
        operation_id="recommend_oreum",
        summary="조건(지역/난이도/거리/소요시간/계절/키워드)에 맞는 오름을 추천한다",
    )
    def recommend_oreum(request: RecommendRequest = RecommendRequest()) -> Dict[str, Any]:
        records = load_oreums()

        # 지역명 외에 다른 필터를 하나도 안 준 경우: 난이도/거리/소요시간/추천계절 +
        # 입구/주차장/화장실/등산로 좌표, 8개 항목 중 채워진 개수(completeness_score)가
        # 높은 오름부터, 동점이면 거리가 짧은 오름부터 최대 3개를 추천한다. 8개를 전부
        # 요구하는 하드 필터였던 적이 있었는데 화장실 좌표 수집률이 낮아 지역에 따라
        # 결과가 통째로 0건이 되는 문제가 있어 점수 기반 랭킹으로 바꿨다. 그 외엔
        # 기존처럼 조건 필터링 후 거리순 limit개를 반환한다. access_open_only는 이
        # 판정에 영향을 주지 않는다(켜져 있어도 지역-only 모드가 그대로 적용됨).
        region_only = (
            request.region is not None
            and request.difficulty is None
            and request.max_distance_km is None
            and request.max_climb_time_min is None
            and request.season is None
            and request.keyword is None
        )

        # 필터링은 원본 레코드(r) 단위로 하고, 정렬/무작위추출까지 끝난 뒤 마지막에
        # to_summary()로 변환한다 — distance_km 등은 정렬용으로만 쓰고 응답엔 안 담기 때문에
        # 요약 딕셔너리가 아니라 레코드를 들고 있어야 정렬 키를 뽑을 수 있다.
        candidates = []
        for r in records:
            basic = r.get("basic_info") or {}
            notes = r.get("notes") or {}

            # region(제주시/서귀포시) 대신 address 전체에 대해 부분일치시킨다.
            # address엔 "제주특별자치도 OO시 OO읍 OO리 ..."가 다 들어있어서
            # region은 물론 "한림"/"구좌" 같은 읍면동 단위 지명도 걸러진다.
            if request.region and request.region not in (r.get("address") or ""):
                continue
            if request.difficulty and basic.get("difficulty") != request.difficulty:
                continue
            if request.max_distance_km is not None:
                dist = basic.get("distance_km")
                if dist is None or dist > request.max_distance_km:
                    continue
            if request.max_climb_time_min is not None:
                climb_time = basic.get("climb_time_min")
                if climb_time is None or climb_time > request.max_climb_time_min:
                    continue
            if request.season and request.season not in (basic.get("recommended_season") or ""):
                continue
            if request.access_open_only:
                # 안전 우선이지만 데이터 현실도 고려: "확실히 제한이 확인된"
                # (reservation_required/restricted/prohibited) 오름만 제외한다.
                # null(미확인·미분류, 329개 중 다수)까지 제외하면 결과가 1개로 줄어드니
                # null/open은 통과시키고, 명시적으로 위험이 확인된 것만 걸러낸다.
                status = (notes.get("access") or {}).get("status")
                if status not in (None, "open"):
                    continue
                # status 분류(notes.access.status)에 의존하는 위 체크는 notes 자체가
                # 미분류(null)인 레코드를 놓친다 — facilities.hours_fee 등 다른 필드에
                # "출입제한"이 그대로 적혀있는 경우가 실제로 있었다(예: 살핀오름/성진이오름).
                # 필드 위치를 안 가리고 레코드 전체에서 이 문구를 찾아 추가로 걸러낸다.
                if has_access_restriction_keyword(r):
                    continue
            if request.restroom_required:
                restroom = (r.get("coordinates") or {}).get("restroom") or {}
                if restroom.get("lat") is None or restroom.get("lng") is None:
                    continue
            if request.keyword:
                haystack = " ".join(
                    [
                        r.get("name") or "",
                        " ".join(notes.get("highlights") or []),
                        notes.get("recommend_for") or "",
                    ]
                )
                if request.keyword not in haystack:
                    continue

            candidates.append(r)

        # 어떤 필터 조합이든(지역-only든 키워드/난이도 등을 섞어 줬든) 정보 점수
        # (completeness_score) 내림차순, 동점이면 거리 오름차순으로 정렬한다 —
        # "조건에 맞으면서 그나마 정보가 가장 많은 오름"을 우선 추천. 지금은 8개 항목
        # 전부 동일 가중치(1점씩)지만, 실용성 차이(등산로/입구/주차장 vs 계절 텍스트 등)를
        # 반영해 가중치를 조정할 계획이라 completeness_score() 하나만 바꾸면 전체에
        # 반영되도록 정렬 로직을 여기 한 곳으로 통일해뒀다.
        candidates.sort(
            key=lambda r: (
                -completeness_score(r),
                (r.get("basic_info") or {}).get("distance_km") is None,
                (r.get("basic_info") or {}).get("distance_km"),
            )
        )
        picked = candidates[:3] if region_only else candidates[: request.limit]

        # 좌표(위경도)는 map_url 지도 페이지가 마커/등산로로 보여주므로 텍스트
        # 응답에서는 뺀다 — strip_coordinates()가 주소/난이도/메모 등 좌표가
        # 아닌 필드는 그대로 남기고 위경도 숫자값만 제거한다.
        results = [strip_coordinates(to_summary(r)) for r in picked]

        # 추천 결과를 카카오맵에 마커로 찍어 보여주는 읽기 전용 페이지 링크.
        # OREUM_MCP_PUBLIC_URL은 이 서버가 외부(ngrok 등)로 노출된 실제 주소를
        # 가리켜야 한다 — 미설정 시 로컬 개발 기본값(localhost:포트)으로 대체.
        picked_ids = [r.get("id") for r in picked if r.get("id") is not None]
        map_url = None
        if picked_ids:
            base_url = (
                os.getenv("OREUM_MCP_PUBLIC_URL")
                or f"http://localhost:{os.getenv('OREUM_MCP_PORT', '11010')}"
            ).rstrip("/")
            ids_param = ",".join(str(i) for i in picked_ids)
            map_url = f"{base_url}/view/?ids={ids_param}"

        return {
            "success": True,
            "count": len(results),
            "results": results,
            "map_url": map_url,
            "coordinates_note": "정확한 좌표(입구/주차장/화장실/등산로 경로)는 이 응답에 없습니다 — map_url 지도 페이지에서 확인하세요." if map_url else None,
        }

    @app.post(
        "/oreum",
        operation_id="get_oreum_detail",
        summary="특정 오름의 상세 정보를 조회한다 (기본정보 + 입구/주차장/화장실/등산로 실제 좌표 + 시설/노트)",
    )
    def get_oreum_detail(request: OreumIdentifierRequest) -> Dict[str, Any]:
        records = load_oreums()
        record, candidates = find_oreum(records, request.identifier)

        if record is None:
            if candidates:
                return {
                    "success": False,
                    "message": f"'{request.identifier}'와 정확히 일치하는 오름이 없습니다. 후보를 확인하세요.",
                    "candidates": [to_summary(c) for c in candidates],
                }
            return {
                "success": False,
                "message": f"'{request.identifier}'에 해당하는 오름을 찾지 못했습니다.",
                "candidates": [],
            }

        coords = record.get("coordinates") or {}
        basic = record.get("basic_info") or {}

        return {
            "success": True,
            "id": record.get("id"),
            "name": record.get("name"),
            "region": record.get("region"),
            "address": record.get("address"),
            "difficulty": basic.get("difficulty"),
            "distance_km": basic.get("distance_km"),
            "climb_time_min": basic.get("climb_time_min"),
            "recommended_season": basic.get("recommended_season"),
            "elevation_m": basic.get("elevation_m"),
            "relative_height_m": basic.get("relative_height_m"),
            "peak_coord": coords.get("peak"),
            # 실제 좌표값. 각 좌표는 map_editor로 수집된 것이고, 없으면 빈 배열/null.
            # official=False면 CSV 원본상 "정식 주차장 없음"으로 기재된 오름이라, 아래 좌표는
            # map_editor 답사 중 발견한 갓길/공터 등 비공식 주차 공간일 가능성이 높다는 뜻.
            # 안내할 때 "정식 주차장"이라 단정하지 말고 이 점을 밝힐 것.
            "entrance_coords": entrance_coords(record),
            "parking_coords": parking_coords(record),
            "restroom_coord": restroom_coord(record),
            # 등산로 경로 좌표. 오름 하나에 등산로가 여러 개(예: 정상 코스 + 둘레길)일 수 있다.
            "trails": [
                {
                    "id": t.get("id"),
                    "path_coords": t.get("path") or [],
                    "surface_type": t.get("surface_type"),
                    "length_m": t.get("length_m"),
                    "note": t.get("note"),
                }
                for t in (record.get("trails") or [])
            ],
            # CSV 원본 자유서술 텍스트. 위 좌표들과 별개로, 참고용 설명일 뿐 좌표 유무를 보장하지 않음
            # (예: 아래 값이 "없음"이어도 위 parking_coords에 실제 좌표가 있을 수 있음).
            "facility_description_from_csv": record.get("facilities"),
            "notes": record.get("notes"),
            "kakao_map_url": record.get("kakao_map_url"),
        }

    @app.post(
        "/linked",
        operation_id="recommend_linked_oreums",
        summary="특정 오름과 함께 방문하기 좋은 연계 오름 목록을 추천한다",
    )
    def recommend_linked_oreums(request: OreumIdentifierRequest) -> Dict[str, Any]:
        records = load_oreums()
        record, candidates = find_oreum(records, request.identifier)

        if record is None:
            if candidates:
                return {
                    "success": False,
                    "message": f"'{request.identifier}'와 정확히 일치하는 오름이 없습니다. 후보를 확인하세요.",
                    "candidates": [to_summary(c) for c in candidates],
                }
            return {
                "success": False,
                "message": f"'{request.identifier}'에 해당하는 오름을 찾지 못했습니다.",
                "candidates": [],
            }

        # linked_oreums는 저장 시 한쪽에만 적히는 단방향 데이터라(예: 가메오름 ->
        # 누운오름은 있어도 누운오름 -> 가메오름은 없음), resolve_linked_oreums가
        # 역방향(다른 레코드가 나를 지목한 경우)까지 합쳐서 어느 쪽으로 조회하든
        # 연계 관계가 보이게 한다.
        resolved = resolve_linked_oreums(record, records)
        if not resolved:
            return {
                "success": True,
                "base": {"id": record.get("id"), "name": record.get("name")},
                "linked": [],
                "message": "이 오름은 아직 수집된 연계 코스 추천 정보가 없습니다.",
            }

        linked = []
        for match, name, direction in resolved:
            if match:
                linked.append({**to_summary(match), "resolved": True, "direction": direction})
            else:
                linked.append({"name": name, "resolved": False, "direction": direction})

        return {
            "success": True,
            "base": {"id": record.get("id"), "name": record.get("name")},
            "linked": linked,
        }
