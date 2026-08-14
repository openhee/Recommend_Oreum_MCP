"""oreum-mcp 도구 3개에 대한 테스트 케이스 (도구당 약 10개).

이 저장소엔 별도 테스트 프레임워크가 없어서(pytest 등 미설치), fastmcp.Client로
실행 중인 서버에 실제 MCP 호출을 날리고 결과를 단순 assert로 검증하는 스크립트
형태로 작성했다. 서버가 먼저 떠 있어야 한다:

    python app.py --host 127.0.0.1 --port 11010

실행:
    python test_tools.py [--url http://127.0.0.1:11010/]
"""
import argparse
import asyncio
import sys

from fastmcp import Client

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  {detail}")


async def test_recommend_oreum(client: Client) -> None:
    print("\n=== recommend_oreum ===")

    r = await client.call_tool("recommend_oreum", {})
    check("1. 필터/인자 전혀 없음 -> 기본 limit(10)만큼 반환", r.data["success"] and r.data["count"] == 10)

    r = await client.call_tool("recommend_oreum", {"region": "제주시", "limit": 50})
    check(
        "2. region 정확매치(제주시) -> 전부 제주시",
        all(x["region"] == "제주시" for x in r.data["results"]),
    )

    r = await client.call_tool("recommend_oreum", {"region": "한림", "limit": 50})
    check("3. region 세부지명(한림) 부분일치 -> 16건", r.data["count"] == 16, f"got {r.data['count']}")

    r = await client.call_tool("recommend_oreum", {"difficulty": "쉬움", "limit": 50})
    check(
        "4. difficulty 필터 -> 전부 쉬움",
        all(x["difficulty"] == "쉬움" for x in r.data["results"]),
    )

    r = await client.call_tool("recommend_oreum", {"max_distance_km": "1.5km", "limit": 50})
    check(
        "5. 단위 붙은 숫자('1.5km') 파싱 -> 전부 1.5km 이하",
        all((x["distance_km"] or 0) <= 1.5 for x in r.data["results"]),
    )

    r = await client.call_tool("recommend_oreum", {"max_climb_time_min": "30분", "limit": 50})
    check(
        "6. 단위 붙은 숫자('30분') 파싱 -> 전부 30분 이하",
        all((x["climb_time_min"] or 0) <= 30 for x in r.data["results"]),
    )

    r = await client.call_tool("recommend_oreum", {"season": "가을", "limit": 50})
    check(
        "7. season 키워드 -> 전부 '가을' 포함",
        all("가을" in (x["recommended_season"] or "") for x in r.data["results"]),
    )

    r = await client.call_tool(
        "recommend_oreum",
        {
            "region": "",
            "difficulty": "",
            "max_distance_km": "",
            "max_climb_time_min": "",
            "season": "",
            "keyword": "",
            "access_open_only": False,
            "limit": 50,
        },
    )
    check("8. 전체 필드 빈 문자열('') -> 422 없이 정상 처리", r.data["success"])

    r = await client.call_tool("recommend_oreum", {"access_open_only": True, "limit": 50})
    check(
        "9. access_open_only=True -> restricted/prohibited/reservation_required 없음",
        all(x["access_status"] in (None, "open") for x in r.data["results"]),
    )

    r = await client.call_tool("recommend_oreum", {"region": "존재하지않는지역이름", "limit": 10})
    check("10. 매칭 없는 조건 -> count 0", r.data["success"] and r.data["count"] == 0)


async def test_get_oreum_detail(client: Client) -> None:
    print("\n=== get_oreum_detail ===")

    r = await client.call_tool("get_oreum_detail", {"identifier": "가세오름"})
    check("1. 이름 정확조회", r.data["success"] and r.data["id"] == 7)

    r = await client.call_tool("get_oreum_detail", {"identifier": "7"})
    check("2. id로 조회('7')", r.data["success"] and r.data["name"] == "가세오름")

    r = await client.call_tool("get_oreum_detail", {"identifier": "존재하지않는오름이름XYZ"})
    check("3. 존재하지 않는 이름 -> success false, candidates 없음", not r.data["success"] and r.data["candidates"] == [])

    r = await client.call_tool("get_oreum_detail", {"identifier": "가"})
    check(
        "4. 모호한 이름('가') -> success false + candidates 여러 개",
        not r.data["success"] and len(r.data["candidates"]) > 1,
    )

    r = await client.call_tool("get_oreum_detail", {"identifier": "가세오름"})
    parking = r.data["parking_coords"]
    check(
        "5. 정식주차장 아님(official=False) 반영 (가세오름)",
        len(parking) == 1 and parking[0]["official"] is False,
    )

    r = await client.call_tool("get_oreum_detail", {"identifier": "가세오름"})
    check("6. restroom 없음 -> restroom_coord null", r.data["restroom_coord"] is None)

    r = await client.call_tool("get_oreum_detail", {"identifier": "노꼬메족은오름"})
    check(
        "7. 입구 여러 개 -> entrance_coords 길이 > 1",
        len(r.data["entrance_coords"]) > 1,
        f"got {len(r.data['entrance_coords'])}",
    )

    r = await client.call_tool("get_oreum_detail", {"identifier": "거슨세미"})
    check(
        "8. 등산로 여러 개 -> trails 길이 > 1",
        len(r.data["trails"]) > 1,
        f"got {len(r.data['trails'])}",
    )

    r = await client.call_tool("get_oreum_detail", {"identifier": "가시오름"})
    check("9. notes 구조화 데이터 존재", r.data["notes"] is not None)

    r = await client.call_tool("get_oreum_detail", {"identifier": "가메옥"})
    check("10. notes 없음(null)", r.data["notes"] is None)


async def test_recommend_linked_oreums(client: Client) -> None:
    print("\n=== recommend_linked_oreums ===")

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "궷물오름"})
    linked_names = {x.get("name") for x in r.data["linked"]}
    check(
        "1. 궷물오름 -> 노꼬메큰오름/노꼬메족은오름 둘 다 resolved",
        linked_names == {"노꼬메큰오름", "노꼬메족은오름"}
        and all(x["resolved"] for x in r.data["linked"]),
    )

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "가세오름"})
    check(
        "2. 연계정보 없는 오름 -> 빈 목록 + 안내 메시지",
        r.data["success"] and r.data["linked"] == [] and "message" in r.data,
    )

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "존재하지않는오름이름XYZ"})
    check("3. 존재하지 않는 이름 -> success false", not r.data["success"])

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "가"})
    check("4. 모호한 이름 -> candidates 반환", not r.data["success"] and len(r.data["candidates"]) > 1)

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "52"})
    check("5. id로 조회('52') -> 궷물오름 기준 연계 목록", r.data["base"]["name"] == "궷물오름")

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "대병악"})
    check("6. 대병악 -> 소병악", any(x.get("name") == "소병악" for x in r.data["linked"]))

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "밧돌오름"})
    check("7. 밧돌오름 -> 안돌오름", any(x.get("name") == "안돌오름" for x in r.data["linked"]))

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "소록산"})
    check("8. 소록산 -> 대록산", any(x.get("name") == "대록산" for x in r.data["linked"]))

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "소병악"})
    check("9. 역방향 참조(소병악 -> 대병악)도 존재", any(x.get("name") == "대병악" for x in r.data["linked"]))

    r = await client.call_tool("recommend_linked_oreums", {"identifier": "노꼬메족은오름"})
    check(
        "10. 상호참조(노꼬메족은오름 -> 노꼬메큰오름/궷물오름) 모두 resolved",
        all(x["resolved"] for x in r.data["linked"]) and len(r.data["linked"]) == 2,
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:11010/")
    args = parser.parse_args()

    async with Client(args.url) as client:
        await test_recommend_oreum(client)
        await test_get_oreum_detail(client)
        await test_recommend_linked_oreums(client)

    print(f"\n총 {PASS + FAIL}개 중 PASS {PASS}, FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
