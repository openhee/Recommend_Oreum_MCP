-- 오름 추천 MCP 서버 - 오름 데이터 스키마
-- 원본: data/오름_dataset.csv (328행, CP949)

CREATE TABLE IF NOT EXISTS oreum (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_seq          INTEGER UNIQUE,        -- 연번 (원본 일련번호, 추적용)
    name                TEXT NOT NULL,          -- 오름명 (중복 존재, UNIQUE 아님)
    region              TEXT NOT NULL CHECK (region IN ('제주시','서귀포시')),  -- 행정시
    address             TEXT,                   -- 소재지
    relative_height_m   REAL,                   -- 비고(比高) - 기저 대비 상대높이
    elevation_m         REAL,                   -- 표고 - 해발고도
    area_sqm            REAL,                   -- 면적(㎡)
    shape_type          TEXT,                   -- 형태 기본형 (원추형/원형/복합형/말굽형 등)
    shape_direction     TEXT,                   -- 형태 방향 (북향/남서향 등, nullable)
    peak_lng            REAL,                   -- 정상_경도 (좌표스왑 정제됨)
    peak_lat            REAL,                   -- 정상_위도
    entrance_lng        REAL,                   -- 입구_경도 (map_editor에서 클릭으로 수집)
    entrance_lat        REAL,                   -- 입구_위도
    restroom_lng        REAL,                   -- 화장실 좌표_경도 (map_editor에서 클릭으로 수집)
    restroom_lat         REAL,                  -- 화장실 좌표_위도
    parking_lng           REAL,                 -- 주차장 좌표_경도 (map_editor에서 클릭으로 수집)
    parking_lat            REAL,                -- 주차장 좌표_위도
    kakao_map_url       TEXT,                   -- 카카오맵_url
    difficulty          TEXT CHECK (difficulty IN ('쉬움','보통','어려움') OR difficulty IS NULL),  -- 난이도
    distance_km         REAL,                   -- 거리_km (등산로 총 거리)
    climb_time_min      INTEGER,                -- 상행시간(분). 원본이 범위표기("30분~50분")면 평균값으로 환산
    surface             TEXT,                   -- 노면
    parking             TEXT,                   -- 주차
    restroom            TEXT,                   -- 화장실
    trail_info          TEXT,                   -- 등산로 정보
    recommended_season  TEXT,                   -- 추천시기 (콤마구분 원본 텍스트, 예: "봄, 가을")
    notes                TEXT,                  -- 참고글
    hours_fee            TEXT,                  -- 운영시간 및 입장료
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_oreum_region ON oreum(region);
CREATE INDEX IF NOT EXISTS idx_oreum_difficulty ON oreum(difficulty);
CREATE INDEX IF NOT EXISTS idx_oreum_shape_type ON oreum(shape_type);
CREATE INDEX IF NOT EXISTS idx_oreum_name ON oreum(name);
CREATE INDEX IF NOT EXISTS idx_oreum_peak_coords ON oreum(peak_lat, peak_lng);
