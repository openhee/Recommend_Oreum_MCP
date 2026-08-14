from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_base_app(
    title: str,
    description: str,
    version: str = "1.0.0",
    docs_url: str = "/docs",
    redoc_url: str = "/redoc",
) -> FastAPI:
    """기본 FastAPI 앱을 생성

    Args:
        title: 앱 제목
        description: 앱 설명
        version: API 버전
        docs_url: Swagger UI 경로 (None이면 비활성화)
        redoc_url: ReDoc 경로 (None이면 비활성화)

    Returns:
        설정이 완료된 FastAPI 앱 인스턴스
    """
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        docs_url=docs_url,
        redoc_url=redoc_url,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
