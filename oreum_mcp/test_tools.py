"""oreum_mcp 3개 도구(recommend_oreum / get_oreum_detail / recommend_linked_oreums)에
대한 회귀 테스트. fastmcp.Client로 실행 중인 서버에 실제 MCP 호출을 날린다.

사전 조건: 서버가 떠 있어야 한다 (`python app.py`, 기본 http://localhost:11010/).

실행: python test_tools.py
"""
import asyncio
import os
import sys

sys.path.insert(0, ".")

from fastmcp import Client

from modules.data import has_access_restriction_keyword

BASE_URL = f"http://localhost:{os.getenv('OREUM_MCP_PORT', '11010')}/"

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail))


async def call(client: Client, tool: str, args: dict) -> dict:
    result = await client.call_tool(tool, args)
    return result.structured_content or result.data


def basic_info(record: dict) -> dict:
    return record.get("basic_info") or {}


def coords(record: dict) -> dict:
    return record.get("coordinates") or {}


def is_full_record(record: dict) -> bool:
    """recommend_oreum/candidates가 요약이 아니라 data/oreum.json 원본 레코드
    그대로를 반환하는지 확인 (basic_info/coordinates/facilities/trails/notes 존재)."""
    return all(k in record for k in ("basic_info", "coordinates", "facilities", "trails", "notes"))


def rank_key(record: dict, restroom_ok: bool | None = None) -> tuple:
    """routes.py의 recommend_oreum 정렬 키(completeness_score desc, distance_km asc)를
    테스트 쪽에서 동일하게 재구현 — 서버 응답 순서 검증용.

    restroom_ok는 restroom_presence_map()으로 미리 조회해 넘겨야 한다 — recommend_oreum
    응답은 strip_coordinates()가 restroom lat/lng를 지워버려서, 응답만 보고는 restroom
    수집 여부를 알 수 없다(항상 None으로 보여 완전정보 점수를 과소평가하게 됨)."""
    dist = basic_info(record).get("distance_km")
    return (-completeness_score(record, restroom_ok), dist is None, dist)


def trail_difficulties(record: dict) -> list:
    """modules/data.py의 oreum_trail_difficulties()를 테스트 쪽에서 독립적으로
    재구현 — 등산로별 DEM 기반 난이도(중복 포함) 목록. basic_info.difficulty(CSV)는
    더 이상 난이도 출처가 아니므로 여기서 보지 않는다."""
    return [
        dm.get("difficulty")
        for t in (record.get("trails") or [])
        if (dm := t.get("difficulty_metrics"))
    ]


def completeness_score(record: dict, restroom_ok: bool | None = None) -> int:
    """routes.py의 completeness_score()와 동일한 8개 항목 채점을 테스트 쪽에서
    독립적으로 재구현 — 서버 정렬 결과를 검증하는 기준으로 쓴다.

    restroom_ok가 주어지면 그 값을 쓰고, 없으면(호출부에서 조회를 안 한 경우)
    record의 coordinates.restroom을 그대로 읽는다 — recommend_oreum 응답처럼
    이미 좌표가 지워진 레코드에 대해서는 restroom_ok를 반드시 넘겨야 정확하다."""
    basic = basic_info(record)
    c = coords(record)
    if restroom_ok is None:
        restroom = c.get("restroom") or {}
        restroom_ok = restroom.get("lat") is not None and restroom.get("lng") is not None
    checks = [
        bool(trail_difficulties(record)),
        basic.get("distance_km") is not None,
        basic.get("climb_time_min") is not None,
        bool(basic.get("recommended_season")),
        bool(c.get("entrances")),
        bool(c.get("parking")),
        restroom_ok,
        bool(record.get("trails")),
    ]
    return sum(checks)


async def restroom_presence_map(client: Client, records: list[dict]) -> dict:
    """레코드들의 id -> "restroom 좌표가 실제로 있는가"(bool) 매핑을
    get_oreum_detail(좌표 안 지워진 응답)로 조회해서 만든다. rank_key()에 넘겨
    recommend_oreum의 strip_coordinates()로 지워진 restroom 정보를 보정한다."""
    out: dict = {}
    for rec in records:
        oreum_id = rec.get("id")
        if oreum_id is None or oreum_id in out:
            continue
        detail = await call(client, "get_oreum_detail", {"identifier": str(oreum_id)})
        out[oreum_id] = detail.get("restroom_coord") is not None
    return out


async def run_tests() -> None:
    async with Client(BASE_URL) as client:

        # --- recommend_oreum: 지역-only 모드 (완전정보 점수 랭킹) ---

        r = await call(client, "recommend_oreum", {"region": "서귀포"})
        check("region-only(서귀포) success", r.get("success") is True)
        check("region-only(서귀포) count<=3", r.get("count", 99) <= 3)
        results = r.get("results", [])
        check("region-only(서귀포) 결과가 전부 완전 레코드", all(is_full_record(x) for x in results))
        restroom_map = await restroom_presence_map(client, results)
        keys = [rank_key(x, restroom_map.get(x.get("id"))) for x in results]
        check("region-only(서귀포) 랭킹 키 순서대로 정렬", keys == sorted(keys))

        # 화장실 좌표 수집률이 0%인 지역(한림)도 결과가 나와야 한다 (하드필터였다면 0건)
        r = await call(client, "recommend_oreum", {"region": "한림"})
        check("region-only(한림) success", r.get("success") is True)
        check("region-only(한림) 결과 0건 아님 (완전정보 하드필터 회귀 방지)", r.get("count", 0) > 0)
        for x in r.get("results", []):
            restroom = coords(x).get("restroom") or {}
            check(
                f"한림·{x.get('name')} restroom 실제로 비어있음(현재 데이터 기준)",
                restroom.get("lat") is None,
            )

        # access_open_only를 켜도 region-only 모드가 그대로 적용돼야 한다
        r = await call(client, "recommend_oreum", {"region": "서귀포", "access_open_only": True})
        check("region-only + access_open_only success", r.get("success") is True)
        check("region-only + access_open_only count<=3", r.get("count", 99) <= 3)
        for x in r.get("results", []):
            status = ((x.get("notes") or {}).get("access") or {}).get("status")
            check(
                f"region-only+access_open_only·{x.get('name')} 제한 상태 아님",
                status not in ("reservation_required", "restricted", "prohibited"),
            )

        # 존재하지 않는 지역명 -> 0건 (에러 아님)
        r = await call(client, "recommend_oreum", {"region": "존재하지않는지역명XYZ"})
        check("region-only(존재하지않는지역) success", r.get("success") is True)
        check("region-only(존재하지않는지역) count==0", r.get("count") == 0)

        # --- recommend_oreum: access_open_only의 '출입제한' 키워드 하드필터 ---
        # 살핀오름(id=199)/성진이오름(id=224)은 notes가 미분류(null)라 access.status로는
        # 못 걸러지지만, facilities.hours_fee에 "출입제한"이 그대로 적혀있다. 함수를
        # 직접 호출해 판정 자체를 검증(랭킹/limit에 좌우되지 않는 단위 테스트).
        r199 = await call(client, "get_oreum_detail", {"identifier": "199"})
        check("살핀오름 실존 확인(id=199)", r199.get("name") == "살핀오름")
        check("has_access_restriction_keyword(살핀오름)=True", has_access_restriction_keyword(r199))

        r224 = await call(client, "get_oreum_detail", {"identifier": "224"})
        check("성진이오름 실존 확인(id=224)", r224.get("name") == "성진이오름")
        check("has_access_restriction_keyword(성진이오름)=True", has_access_restriction_keyword(r224))

        # 위 두 오름을 name 매칭으로 확실히 후보에 포함시킨 뒤 access_open_only로 걸러지는지 확인
        r = await call(client, "recommend_oreum", {"keyword": "살핀오름", "limit": 5})
        check("access_open_only 없이는 살핀오름 후보에 있음", any(x.get("name") == "살핀오름" for x in r.get("results", [])))
        r = await call(client, "recommend_oreum", {"keyword": "살핀오름", "access_open_only": True, "limit": 5})
        check("access_open_only 켜면 살핀오름 제외됨", not any(x.get("name") == "살핀오름" for x in r.get("results", [])))

        # --- recommend_oreum: restroom_required 하드 필터 ---

        r = await call(client, "recommend_oreum", {"region": "한림", "restroom_required": True})
        check("restroom_required(한림) success", r.get("success") is True)
        check(
            "restroom_required(한림) 결과 0건 (한림 전체가 restroom 미수집)",
            r.get("count") == 0,
        )

        r = await call(client, "recommend_oreum", {"region": "서귀포", "restroom_required": True})
        check("restroom_required(서귀포) success", r.get("success") is True)
        for x in r.get("results", []):
            restroom = coords(x).get("restroom") or {}
            check(
                f"restroom_required·{x.get('name')} restroom 좌표 실제로 있음",
                restroom.get("lat") is not None and restroom.get("lng") is not None,
            )

        # --- recommend_oreum: 일반 모드 (region+difficulty 등 다른 필터 병행 시에도
        # region-only와 동일하게 완전정보 점수 내림차순 + 동점 시 거리 오름차순) ---

        r = await call(client, "recommend_oreum", {"region": "서귀포", "difficulty": "쉬움"})
        check("일반모드(region+difficulty) success", r.get("success") is True)
        results = r.get("results", [])
        check(
            "일반모드(region+difficulty) 전부 등산로 중 하나는 쉬움",
            all("쉬움" in trail_difficulties(x) for x in results),
        )
        restroom_map = await restroom_presence_map(client, results)
        keys = [rank_key(x, restroom_map.get(x.get("id"))) for x in results]
        check("일반모드(region+difficulty) 랭킹 키 순서대로 정렬", keys == sorted(keys))
        check("일반모드(region+difficulty) 기본 limit=3", len(results) <= 3)

        # region 없이 keyword/difficulty만 줘도 랭킹(정보량→거리)이 반영돼야 한다
        r = await call(client, "recommend_oreum", {"difficulty": "어려움", "limit": 10})
        check("일반모드(난이도만) success", r.get("success") is True)
        results = r.get("results", [])
        restroom_map = await restroom_presence_map(client, results)
        keys = [rank_key(x, restroom_map.get(x.get("id"))) for x in results]
        check("일반모드(난이도만) 랭킹 키 순서대로 정렬", keys == sorted(keys))

        # 필터 없음(region도 없음) -> region-only 아님, 정상적으로 거리순 limit=3
        r = await call(client, "recommend_oreum", {})
        check("무인자 호출 success", r.get("success") is True)
        check("무인자 호출 기본 limit=3", r.get("count", 99) <= 3)

        # limit 명시 시 존중되는지 (일반모드에서만)
        r = await call(client, "recommend_oreum", {"max_climb_time_min": 9999, "limit": 7})
        check("limit=7 명시 시 최대 7개", r.get("count", 99) <= 7)

        # 단위 붙은 문자열 파싱 ("30분")
        r = await call(client, "recommend_oreum", {"max_climb_time_min": "30분"})
        check("max_climb_time_min='30분' 파싱 성공(422 아님)", r.get("success") is True)
        check(
            "max_climb_time_min='30분' 필터 실제 적용",
            all((basic_info(x).get("climb_time_min") or 0) <= 30 for x in r.get("results", [])),
        )

        # 빈 문자열 -> None 정규화 (422 아님)
        r = await call(client, "recommend_oreum", {"difficulty": "", "region": ""})
        check("빈 문자열 필터 정규화 성공(422 아님)", r.get("success") is True)

        # --- recommend_oreum: has_elderly_or_child_companion (동반자 기반 난이도 기본값) ---

        r = await call(client, "recommend_oreum", {"has_elderly_or_child_companion": True, "limit": 10})
        check("동반자플래그(difficulty 미지정) success", r.get("success") is True)
        results = r.get("results", [])
        check(
            "동반자플래그(difficulty 미지정) 전부 쉬움으로 기본 적용",
            all("쉬움" in trail_difficulties(x) for x in results),
        )

        r = await call(
            client,
            "recommend_oreum",
            {"has_elderly_or_child_companion": True, "difficulty": "어려움", "limit": 10},
        )
        check("동반자플래그+difficulty 명시 success", r.get("success") is True)
        results = r.get("results", [])
        check(
            "동반자플래그+difficulty 명시 시 명시값(어려움) 존중, 덮어쓰지 않음",
            all("어려움" in trail_difficulties(x) for x in results),
        )

        # --- get_oreum_detail ---

        r = await call(client, "get_oreum_detail", {"identifier": "법정악"})
        check("get_oreum_detail(이름) success", r.get("success") is True)
        check("get_oreum_detail(이름) 이름 일치", r.get("name") == "법정악")
        check("get_oreum_detail trails에 path_coords 있음", bool((r.get("trails") or [{}])[0].get("path_coords")))
        check(
            "get_oreum_detail parking_coords[].official 필드 존재",
            all("official" in p for p in r.get("parking_coords", [])),
        )
        check(
            "get_oreum_detail trails[].difficulty 필드 존재 (DEM 기반)",
            all("difficulty" in t for t in r.get("trails", [])),
        )
        check(
            "get_oreum_detail trail_difficulties가 trails[].difficulty와 일치",
            sorted(d for d in r.get("trail_difficulties", []))
            == sorted(t.get("difficulty") for t in r.get("trails", []) if t.get("difficulty")),
        )

        oreum_id = r.get("id")
        r2 = await call(client, "get_oreum_detail", {"identifier": str(oreum_id)})
        check("get_oreum_detail(id) 이름 일치", r2.get("name") == "법정악")

        r = await call(client, "get_oreum_detail", {"identifier": "오름"})
        check("get_oreum_detail(모호한 이름) success=False", r.get("success") is False)
        check("get_oreum_detail(모호한 이름) candidates 비어있지 않음", len(r.get("candidates", [])) > 0)
        check(
            "get_oreum_detail candidates도 완전 레코드",
            all(is_full_record(c) for c in r.get("candidates", [])[:5]),
        )

        r = await call(client, "get_oreum_detail", {"identifier": "존재하지않는오름이름XYZ"})
        check("get_oreum_detail(없는 이름) success=False", r.get("success") is False)
        check("get_oreum_detail(없는 이름) candidates 없음", r.get("candidates") == [])

        # --- 등산로가 2개 이상 + 서로 다른 난이도인 오름: "하나라도 맞으면 포함" 필터 확인.
        # 괭이모루(등산로 쉬움+어려움 혼재)로 검증 — data/oreum.json은 배치 스크립트
        # (scripts/compute_trail_difficulty.py) 재실행 시 값이 바뀔 수 있으니, 먼저
        # get_oreum_detail로 실제 trail_difficulties를 확인한 뒤 그 값으로 검증한다.
        r = await call(client, "get_oreum_detail", {"identifier": "괭이모루"})
        check("get_oreum_detail(괭이모루) success", r.get("success") is True)
        gwaengi_diffs = set(r.get("trail_difficulties", []))
        check("get_oreum_detail(괭이모루) 등산로 난이도 2종 이상 혼재", len(gwaengi_diffs) >= 2)

        if len(gwaengi_diffs) >= 2:
            one_diff = sorted(gwaengi_diffs)[0]
            r = await call(client, "recommend_oreum", {"keyword": "괭이모루", "difficulty": one_diff, "limit": 5})
            check(
                f"recommend_oreum(difficulty={one_diff}) 괭이모루 포함 (등산로 하나라도 맞으면 포함)",
                any(x.get("name") == "괭이모루" for x in r.get("results", [])),
            )

        # --- recommend_linked_oreums ---

        r = await call(client, "recommend_linked_oreums", {"identifier": "법정악"})
        check("recommend_linked_oreums 응답 success", r.get("success") is True)
        check("recommend_linked_oreums base 이름 일치", (r.get("base") or {}).get("name") == "법정악")

        r = await call(client, "recommend_linked_oreums", {"identifier": "존재하지않는오름이름XYZ"})
        check("recommend_linked_oreums(없는 이름) success=False", r.get("success") is False)

        # 가메오름 -> 누운오름: 실제로 연계 데이터가 있는 케이스. map_url이 채워지고
        # linked[] 항목에 좌표(lat/lng/path 등)가 없는지 확인한다.
        r = await call(client, "recommend_linked_oreums", {"identifier": "가메오름"})
        check("recommend_linked_oreums(가메오름) success", r.get("success") is True)
        linked = r.get("linked") or []
        check("recommend_linked_oreums(가메오름) linked 비어있지 않음", len(linked) > 0)
        check("recommend_linked_oreums(가메오름) map_url 존재", bool(r.get("map_url")))

        def _has_no_coords(item: dict) -> bool:
            coords = (item.get("coordinates") or {})
            if "peak" in coords:
                return False
            for e in coords.get("entrances") or []:
                if "lat" in e or "lng" in e:
                    return False
            for p in coords.get("parking") or []:
                if "lat" in p or "lng" in p:
                    return False
            restroom = coords.get("restroom")
            if restroom and ("lat" in restroom or "lng" in restroom):
                return False
            for t in item.get("trails") or []:
                if "path" in t:
                    return False
            return True

        check(
            "recommend_linked_oreums(가메오름) linked[] 좌표 미포함",
            all(_has_no_coords(item) for item in linked if item.get("resolved")),
        )

        # identifier 생략: 연계 코스가 수집된 오름 중에서 브라우즈 추천
        r = await call(client, "recommend_linked_oreums", {})
        check("recommend_linked_oreums(identifier 생략) success", r.get("success") is True)
        results = r.get("results")
        check("recommend_linked_oreums(identifier 생략) results는 list", isinstance(results, list))
        check("recommend_linked_oreums(identifier 생략) results 비어있지 않음", len(results or []) > 0)
        check(
            "recommend_linked_oreums(identifier 생략) 각 결과에 base/linked/map_url",
            all(
                {"base", "linked", "map_url"} <= set(item.keys())
                for item in (results or [])
            ),
        )
        check(
            "recommend_linked_oreums(identifier 생략) 결과 좌표 미포함",
            all(
                _has_no_coords(linked_item)
                for item in (results or [])
                for linked_item in item.get("linked") or []
                if linked_item.get("resolved")
            ),
        )


def print_summary() -> bool:
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    for name, ok, detail in _results:
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {name}"
        if detail and not ok:
            line += f" ({detail})"
        print(line)
    print(f"\n총 {total}개 중 PASS {passed}, FAIL {total - passed}")
    return passed == total


if __name__ == "__main__":
    asyncio.run(run_tests())
    ok = print_summary()
    sys.exit(0 if ok else 1)
