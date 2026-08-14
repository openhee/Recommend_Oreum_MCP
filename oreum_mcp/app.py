"""제주 오름 추천 MCP 서버.

data/oreum.json을 읽어 조건 기반 추천 / 오름 상세 조회 / 연계 코스 추천
도구를 제공한다. 데이터를 쓰지 않는 읽기 전용 서버 — 수집은 map_editor에서
계속 진행된다.
"""
from pathlib import Path

import sys
import argparse
from fastmcp import FastMCP
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent))

from modules.routes import register_routes
from modules.shared import create_base_app


# 1. REST API 앱 생성
api_app = create_base_app(
    title="Oreum API Server",
    description="제주 오름 추천을 위한 REST API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

register_routes(api_app)

# 2. FastAPI 앱을 MCP 서버로 변환
mcp = FastMCP.from_fastapi(
    api_app,
    name="Oreum Recommendation MCP Server",
    instructions="""제주 오름(기생화산체) 데이터를 기반으로 추천/조회를 제공하는 MCP 서버입니다.

주요 기능:
1. 조건 기반 추천 (recommend_oreum)
   - 지역/난이도/거리/소요시간/계절/키워드로 필터링해 오름 목록 추천
   - 예: "서귀포시에 있고 30분 이내로 오를 수 있는 쉬운 오름 추천해줘"
2. 오름 상세 조회 (get_oreum_detail)
   - 이름 또는 id로 특정 오름의 기본정보/시설/등산로/노트 조회
   - 이름이 여러 오름과 부분일치하면 candidates 목록을 반환하니, 사용자에게
     정확한 오름을 재확인하세요.
3. 연계 코스 추천 (recommend_linked_oreums)
   - 특정 오름과 함께 방문하기 좋은 다른 오름 목록 (notes.linked_oreums 기반)
   - 아직 연계 정보가 수집되지 않은 오름은 빈 목록 + 안내 메시지를 반환합니다.

주의:
- 난이도(difficulty)는 CSV 원본 값(쉬움/보통/어려움)이며, 일부 오름은 아직
  값이 없을 수 있습니다(null) — 필터에서 제외되니 참고하세요.
- access_status가 'reservation_required'/'restricted'/'prohibited'인 오름은
  방문 전 예약/통제 여부를 반드시 안내하세요.
- get_oreum_detail의 parking_coords[].official이 false면 CSV 원본상 "정식 주차장
  없음"으로 기재된 오름입니다 — 좌표가 있어도 갓길/공터 등 비공식 주차 공간일
  수 있으니 "정식 주차장"이라 단정하지 말고 그 점을 사용자에게 알려주세요.""",
)

# 3. MCP HTTP 앱 (streamable-http 트랜스포트)
# stateless_http=True: 이 서버의 도구는 전부 매 요청마다 data/oreum.json을 새로
# 읽는 순수 조회라 세션 상태가 필요 없다. 세션을 유지하지 않으면 개발 중 서버를
# 재시작해도 클라이언트(Inspector 등)가 들고 있던 세션 ID가 무효화되는 문제
# ("Session not found")가 아예 발생하지 않는다.
mcp_app = mcp.http_app(
    path="/",
    transport="streamable-http",
    json_response=False,
    host_origin_protection=False,
    stateless_http=True,
)

# 4. lifespan 연동을 위한 래퍼 앱
app = FastAPI(
    title="Oreum Recommendation MCP Server",
    description="MCP server providing Jeju oreum recommendation tools",
    version="1.0.0",
    lifespan=mcp_app.lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "oreum-mcp"}


# 5. MCP 앱 마운트
app.mount("/", mcp_app)


if __name__ == "__main__":
    import os
    import uvicorn

    parser = argparse.ArgumentParser(description="Oreum Recommendation MCP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OREUM_MCP_PORT", "11010")),
        help="Port to bind (default: 11010)",
    )
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
