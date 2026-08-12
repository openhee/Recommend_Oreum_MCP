# 세션 리포트 — 2026-08-12

**작성 기준**: `git status`/`git diff`/`git log`, 현재 작업트리의 `data/oreum.json`(329건)과 마지막 커밋 `f221fc8`(2026-08-11 17:41:48 +0900) 시점의 `data/oreum.json`(328건)을 직접 비교, `map_editor/app.py`·`map_editor/static/index.html`·`scripts/migrate_entrances_and_drop_trail_start.py`의 실제 diff. 세션 종료 시점(이 리포트 작성 시점)까지도 아직 커밋되지 않은 상태(`git status` = working tree, not staged/committed) — 아래 수치는 전부 "지금 디스크에 있는 파일" 기준이며, 다음 커밋에 정확히 무엇이 들어갈지는 사용자가 커밋하는 시점의 상태에 따라 달라질 수 있음.

---

## 1. 오늘 Map Editor에서 수정한 내용

### `map_editor/app.py` (+11/-3, 백엔드)

**목적**: `facilities.trail_info == "있음"`인데 아직 `trails[]`가 비어 있는 오름(수집 우선순위가 높은 대상)을 UI에서 바로 식별할 수 있게 함.

- **추가**: `needs_trail(row: dict) -> bool` 헬퍼 — `facilities.trail_info == "있음" and not row.get("trails")`를 반환하는 파생 플래그(별도 저장 필드 아님, 매 요청마다 재계산).
- **변경**: `GET /api/oreum` (`search_oreum`)
  - 변경 전: `search_oreum(q: str = "")` — 검색어로만 필터링, 응답에 `needs_trail` 없음.
  - 변경 후: `search_oreum(q: str = "", needs_trail_only: bool = False)` — `needs_trail_only=1`이면 서버 사이드에서 해당 오름만 필터링. 응답 각 항목에 `"needs_trail": needs_trail(r)` 필드 추가.

### `map_editor/static/index.html` (+20/-2, 프론트엔드)

- **CSS 추가**: `.badge-needs-trail`(빨간 배지), `#needs-trail-filter`(체크박스 줄 스타일).
- **HTML 추가**: 검색창 아래 `<label id="needs-trail-filter">` 체크박스 — "등산로 정보 '있음'인데 미수집인 오름만 보기".
- **JS 변경**:
  - `searchOreum(q)`: 체크박스 상태를 읽어 `needs_trail_only=1` 쿼리 파라미터를 붙여서 요청하도록 변경.
  - `renderResults(items)`: `item.needs_trail`이 true면 목록 각 행에 빨간 "등산로 필요" 배지 렌더링 (기존 "화장실없음"/"주차없음" 배지와 같은 자리에 추가).
  - `#needs-trail-checkbox`에 `change` 리스너 추가 — 체크 시 현재 검색어로 목록 재조회.

**변경 전 → 변경 후 요약**: 검색 결과 목록에는 화장실/주차 유무 배지만 있었고, "등산로 정보는 있는데 아직 못 채운 오름"을 구분할 방법이 없었음 → 이제 빨간 배지 + 전용 필터 체크박스로 바로 걸러볼 수 있음. 이 플래그는 요청마다 서버에서 실시간 재계산되므로, 등산로를 하나라도 저장해 `trails[]`가 채워지면 다음 목록 갱신(`refreshProgress()`가 저장 성공 시 항상 호출됨) 때 배지가 자동으로 사라짐 — 별도 처리 불필요.

**검증**: 8010 포트가 사용자의 기존 서버(PID 9756)로 점유되어 있어 종료 후 검증용 서버를 띄우고, `GET /api/oreum?needs_trail_only=1` → 135건, 전체 목록 중 `needs_trail=true` 개수도 135건으로 일치하는 것을 실제 HTTP 응답으로 확인 후 종료(포트 사용자에게 반환). **단, 실제 브라우저에서 체크박스 클릭 시 렌더링까지 스크린샷으로 확인하지는 않음** — API 레벨 검증만 완료된 상태.

### `scripts/migrate_entrances_and_drop_trail_start.py` (+11/-9, 데이터 파이프라인 스크립트)

map_editor 자체 파일은 아니지만 오늘 함께 수정됨.

- **문제 발견**: `coords.pop("entrance", None)`가 이미 마이그레이션된 데이터(구형 `entrance` 단수 키 없음)에서는 항상 `None`을 반환 → `else` 분기로 빠져 `coords["entrances"] = []`를 **무조건** 덮어씀. 재실행 시 map_editor로 수집한 모든 입구 데이터가 삭제되는 실제 데이터 파괴 버그였음(현재 데이터에는 `entrance` 단수 키가 이미 없음을 확인 — 재실행하면 100% 발동).
- **수정**: `"entrance" in coords`일 때만 처리하도록 가드 추가 — 키가 없으면 `entrances`를 건드리지 않음.
- **검증**: 현재 `data/oreum.json`에 대해 수정된 `migrate_record()`를 메모리상에서만 재실행하는 드라이런으로 "재실행 전/후 데이터 완전히 동일(`unchanged: True`)"을 확인. 파일에는 쓰지 않음.
- **미해결**: 없음 — 이 스크립트는 이제 안전하게 재실행 가능하지만, 애초에 재실행할 필요가 없는 1회성 스크립트라는 점은 그대로.

---

## 2. 오늘 확보한 데이터

### (1) 서걸세 오름 신규 레코드 — `data/oreum.json`, `id: 329`

| 항목 | 내용 |
|---|---|
| 출처 | 사용자가 대화 중 직접 제공(난이도/해발고도/거리/상행시간/주차/화장실/등산로정보/추천시기) + 후속 질문으로 확인한 region(서귀포시)·address |
| 건수 | 1건 (전체 328 → 329) |
| 채워진 필드 | `name`, `region`, `address`, `basic_info.{difficulty, elevation_m, distance_km, climb_time_min, recommended_season}`, `facilities.{parking, restroom, trail_info}` |
| 비어있는 필드 | `basic_info.{relative_height_m, area_sqm, shape_type, shape_direction}`, `coordinates.{peak, entrances, parking, restroom}`(전부 null/빈배열), `trails: []`, `facilities.{surface, hours_fee}`, `kakao_map_url`, `notes` |
| 사용 가능 상태 | 부분적. 텍스트 기반 필드(난이도·거리·소요시간·주차/화장실 여부)는 바로 사용 가능하나, 좌표가 전혀 없어 지도 표시·거리 계산·map_editor 진행률(0/4)에는 아직 반영 안 됨 |
| 이상치 | 없음 (id 충돌 없음, 필드 타입 기존 레코드와 동일) |

### (2) 사용자가 오늘 map_editor로 직접 수집한 좌표/등산로 데이터

**중요**: 이건 Claude가 조작한 게 아니라, 오늘 대화 중 사용자가 본인 서버(포트 8010, PID 9756)로 병행 작업한 결과를 마지막 커밋(`f221fc8`, 328건) 대비 현재 파일과 비교해서 역산한 수치.

| 항목 | 어제(f221fc8) | 오늘(현재) | 증감 |
|---|---:|---:|---:|
| entrances 있는 오름 | 101 | 147 | +46 |
| entrance 포인트 총합 | 108 | 154 | +46 |
| parking 있는 오름 | 86 | 119 | +33 |
| parking 포인트 총합 | 89 | 124 | +35 |
| restroom 좌표 있는 오름 | 18 | 30 | +12 |
| trails 있는 오름 | 104 | 150 | +46 |
| trail 포인트(구간) 총합 | 117 | 165 | +48 |
| `needs_trail`(등산로정보 있음+미수집) | 135 | 89 | **-46 (해결됨)** |

| 필드 | 출처 | 저장 위치 | 사용 가능 상태 | 비고 |
|---|---|---|---|---|
| 좌표(입구/주차/화장실) | 카카오맵 클릭 + 역지오코딩 | `data/oreum.json` (커밋 안 됨) | 즉시 사용 가능 (lat/lng 유효) | address는 카카오 역지오코딩 자동 채움 |
| 등산로 경로 | 카카오맵 수동 클릭 or OSM Overpass 후보 가져오기 후 검수 | 동일 | 경로(`path`)는 사용 가능, `surface_type`은 165건 중 162건(98.2%) 여전히 미기재 | `length_m`은 서버 자동계산이라 162/165(98.2%) 채워짐 |

**추가로 확보해야 하는 데이터** (오늘 기준 잔여):
- `coordinates.peak` 없는 오름 16건
- `coordinates.entrances` 없는 오름 182건
- `coordinates.parking` 없는 오름 210건
- `coordinates.restroom` 없는 오름 299건 (90.9% — 가장 심각)
- `trails` 없는 오름 179건 (그중 89건은 `trail_info == "있음"`이라 우선순위 높음, 오늘 새로 추가한 UI 배지로 식별 가능)
- `trails[].surface_type` 미기재 162건(98.2%)

**중복/이상치**: 오름명 중복 15건(11개 이름, 2~4개씩 — 어제와 동일, 오늘 변동 없음, id는 전부 고유). CSV 원본 자체의 특성으로 추정되며 오늘 작업으로 생기거나 해소되지 않음.

---

## 3. 앞으로 데이터를 정리할 때 발생할 문제점

| # | 문제 | 발생 원인 | 현재 영향 | 해결 방법 | 우선순위 |
|---|---|---|---|---|---|
| 1 | `coordinates.peak` 결측 건수가 계속 변동(8/10 21건 → 8/11 17건 → 오늘 16건)하는데 경위가 코드/커밋 이력으로 추적 안 됨 | `map_editor`에는 peak 편집 UI가 아예 없음(코드로 확인) — 그런데 값이 바뀜. CSV/DB 레벨 직접 수정 또는 파일 수동 편집으로 추정되나 근거 없음 | peak 없는 16개 오름은 `trail-candidates` API가 entrance로 폴백하지만, entrance도 없으면 등산로 후보 조회 자체가 불가 (`400: 정상/입구 좌표가 없어 검색 기준점을 정할 수 없습니다`) | 데이터를 코드 밖에서 직접 편집할 경우 커밋 메시지나 별도 로그에 "무엇을 왜 고쳤는지" 남기는 절차 도입 | 중간 |
| 2 | `facilities.restroom` 등 CSV 자유서술 텍스트 필드가 map_editor 경로 밖에서 바뀐 정황(`facilities.restroom == "없음"` 건수가 221→217로 감소) | `app.py`의 어떤 엔드포인트도 `facilities.*` 텍스트를 쓰지 않음(코드로 확인) — 즉 파일을 직접 편집했을 가능성 | 변경 경로가 코드로 추적 안 됨. `scripts/build_oreum_json.py`를 다시 돌리면 이런 수동 보정이 전부 CSV 원본값으로 되돌아감(그 스크립트는 CSV만 보고 완전히 새로 만드는 구조) | CLAUDE.md에 "facilities 텍스트 필드는 CSV 원본 그대로 유지, 수정 시 이유를 남길 것" 명문화 | 중간 |
| 3 | `trails[].surface_type` 98.2% 결측(165건 중 162건) | 등산로 저장 시 노면상태 선택이 선택사항이라 강제되지 않음 + 난이도 자동계산 공식(경사도 0.286/거리 0.196/암릉암반 0.193/노면상태 0.169/소요시간 0.154)이 아직 코드에 미구현 | 난이도 자동계산 기능을 아직 만들 수 없음 | 등산로 저장 시 노면상태 입력을 필수로 바꾸거나 최소한 미입력 경고 표시 | 중간 (난이도 계산 기능 착수 시 높음으로 격상) |
| 4 | 오름 신규 추가 절차가 스크립트화되어 있지 않음(오늘 서걸세는 `python -c`로 직접 append) | `id` 발급이 `build_oreum_json.py`(CSV 행 순서)와 수동 `max(id)+1` 두 체계로 혼재 | 현재는 수동 관리로 충돌 없음(`dup_ids: 0` 확인) | 오름 추가 전용 스크립트/API를 만들어 id 발급 로직을 한 곳에 모으기 | 중간 (신규 오름 추가가 반복될수록 우선순위 상승) |
| 5 | 오름명 중복 15건(11개 이름) — 검색 UI가 이름만으로 검색 | CSV 원본 자체에 동명이 존재(지역이 다른 별개 오름으로 추정, 확인 불가) | id로는 구분 가능하나 검색 결과에서 region 배지만으로 구분해야 해 혼동 가능 | 검색 결과에 address 일부를 함께 표시 | 낮음 |
| 6 | OSM Overpass 등산로 후보를 사람이 검수 없이 그대로 저장할 위험 | `importTrailCandidate`가 후보를 그대로 `draftTrails`에 편입하지만, 저장 전 검수를 강제하는 코드 레벨 장치는 없음(문서로만 안내) | 현재까지 사고 없음(확인 가능한 범위 내) | 저장 시 "OSM 원본 그대로인가?" 같은 경고 UI 추가 검토 | 낮음 |
| 7 | `data/oreum.json` 전체를 매 요청마다 통째로 읽고 쓰는 구조(`load_records`/`save_records`) | 동시 편집자가 여러 명이 되면 파일 락 없는 전체 재작성 방식이라 경쟁 조건(거의 동시 저장 시 한쪽 유실) 위험 | 현재는 사용자 1인 편집이라 발생 안 함 | 협업 확장 시 SQLite 또는 파일 락 도입 검토 | 낮음 |
| 8 | 서버 프로세스 충돌(8010 포트, Claude 검증용 vs 사용자 서버) — 여러 날 반복됐던 이슈 | 두 프로세스가 같은 포트를 바인딩 시도 | 오늘은 세션 시작 시 저장해둔 루틴(항상 netstat 확인 → 필요시 종료 → 검증 → 재종료)으로 사고 없이 처리됨 | 계속 이 루틴 유지, 필요하면 검증용 포트를 별도로 분리하는 것도 검토 가능 | 낮음 (운영 습관으로 완화됨) |

---

## 4. 오늘 내가 Claude Code에게 명령한 것들

| # | 요청 내용 | 실제 수행 작업 | 결과 | 관련 파일 |
|---|---|---|---|---|
| A | (세션 시작) 검증 서버를 띄울 때 항상 netstat로 8010 확인 후 종료/재기동/재종료하라는 고정 루틴 지시 | 메모리에 feedback 항목으로 저장, 이후 모든 서버 기동 전 실제로 netstat 체크 수행 | 성공 — 이후 두 차례(오늘) 실제로 이 루틴을 따름 | `~/.claude/.../memory/feedback_port_8010_check.md` |
| B | 어제 리포트 5절 내용(서버 충돌 재발)을 이해하고 있는지 확인 | 내용 확인 응답만 함(추가 조치 없음, 이미 A에서 루틴화됨) | 성공 | - |
| C | `facilities.trail_info == "있음"`인데 `trails[]` 비어있는 오름 개수 질문 | 스크립트로 실제 계산 → 135건 + 전체 이름 목록 제시 | 성공 | `data/oreum.json` (읽기 전용) |
| D | 두 마이그레이션 스크립트(`migrate_parking_to_array_and_add_notes.py`, `migrate_entrances_and_drop_trail_start.py`)의 재실행 안전성(멱등성) 코드 리뷰 및 삭제/가드 여부 판단 요청 | parking 스크립트는 이미 멱등임을 코드로 확인, entrances 스크립트에서 재실행 시 데이터 파괴 버그 발견 → 가드 추가 → 드라이런으로 재검증 | 성공 (버그 발견 + 수정 + 검증까지 완료) | `scripts/migrate_entrances_and_drop_trail_start.py` |
| E | 두 스크립트가 map_editor 수정 시 자동으로 실행되는지 질문 | 코드베이스 전체 grep으로 두 스크립트가 어디서도 import/호출되지 않음을 확인 후 답변 | 성공 | 전체 코드베이스 (읽기 전용) |
| F | (C의 결과인) 135개 오름을 map_editor UI에 표시해달라는 요청 | 백엔드에 `needs_trail` 플래그/필터 파라미터 추가, 프론트엔드에 배지+체크박스 필터 추가, 실제 서버 기동해 API 응답으로 검증 후 서버 종료 | 성공 | `map_editor/app.py`, `map_editor/static/index.html` |
| G | (F 작업 중 끼어든 요청) 등산로를 채우면 표시가 사라지게 해달라는 요청 | 이미 F의 설계(서버에서 매 요청마다 실시간 재계산)가 이 요구사항을 충족함을 코드 근거로 설명, 추가 구현 불필요 | 성공 (추가 구현 없이 요구사항 충족 확인) | `map_editor/app.py` (변경 없음, 기존 구현 설명) |
| H | "서걸세" 오름을 동일 양식으로 신규 생성 (난이도/해발고도/거리/상행시간/주차/화장실/등산로정보/추천시기 제공) | 기존 레코드 스키마 확인 → region/address 누락분 질문(AskUserQuestion + 후속 텍스트 질문) → 답변 받은 뒤 `id: 329`로 append, 결과 재확인 | 성공 | `data/oreum.json` |
| I | 오늘 작업 전체를 실제 기록 기반으로 7개 항목에 걸쳐 상세 정리 요청 (현재 작업) | `git status`/`git diff`/`git log`, 커밋 시점 대비 데이터 비교 스크립트 실행, 결측률 전수 계산 후 본 리포트 작성 | 진행 중(본 문서) | `docs/session-report-2026-08-12.md` |

---

## 5. Claude Code에게 명령할 때 발생한 문제점

1. **필드 경로 표현의 모호함** — C 요청에서 "`facilities.trail_info = "있음"`인데 `facilities.trails[]`이 비어있는"이라고 쓰셨는데, 실제 스키마상 `trails`는 `facilities` 하위가 아니라 최상위 필드입니다(`CLAUDE.md`의 레코드 구조 문서에도 최상위로 명시). 최상위 `trails[]` 기준으로 해석해서 답변했고 이후 대화에서 정정이 없었던 걸로 봐서 의도와 맞았던 것 같지만, 답변 시작 부분에서 "말씀하신 필드는 최상위 `trails[]`로 이해했습니다"처럼 먼저 확인 문구를 넣었으면 더 안전했을 것. → **다음에는**: 스키마상 존재하지 않는 경로가 요청에 등장하면, 가장 가까운 실제 필드로 조용히 대체하지 말고 어떤 필드로 해석했는지 한 줄로 밝히고 진행.

2. **한글 콘솔 출력 깨짐 반복** — Bash 도구(Git Bash, cp949 콘솔)로 파이썬 스크립트의 한글 결과를 바로 `print`하면 매번 깨져서, 파일에 UTF-8로 써서 Read 도구로 다시 읽는 우회를 여러 차례 반복해야 했음(오늘만 3~4회). → **다음에는**: 한글이 포함된 결과를 다룰 걸 예상하면 처음부터 "스크립트 결과를 파일에 쓰고 Read로 확인" 패턴을 기본으로 사용해 시행착오를 줄임.

3. **신규 오름 추가 요청 시 필수 정보 일부 누락** — H 요청에 `region`/`address`가 빠져 있어 질문을 두 번(AskUserQuestion으로 region 선택 → 이어서 텍스트로 address)에 나눠 진행해야 했음. → **다음에는**: 요청에 스키마상 필수급 필드가 빠져 있으면 한 번에 모아서 질문(또는 AskUserQuestion 하나에 여러 항목)하는 편이 왕복을 줄임 — 이번에는 Claude 쪽에서 개선할 부분.

4. 그 외 지시들(C, D, E, F, G)은 의도가 비교적 명확했고, 재지시 없이 첫 시도에 의도한 결과가 나와 성공적으로 마무리됨.

---

## 6. 현재 데이터 결측률

**전체 기준 (`data/oreum.json`, 329건, map_editor가 유일하게 읽고 쓰는 데이터)**

| 데이터셋 | 전체 건수 | 컬럼 | 결측 건수 | 결측률 | 중요도 | 비고 |
|---|---:|---|---:|---:|---|---|
| oreum.json | 329 | basic_info.elevation_m | 0 | 0.0% | 높음 | CSV 원본, 거의 완비 |
| oreum.json | 329 | basic_info.relative_height_m | 1 | 0.3% | 중간 | 신규 서걸세 1건만 결측 |
| oreum.json | 329 | basic_info.area_sqm | 1 | 0.3% | 중간 | 〃 |
| oreum.json | 329 | basic_info.shape_type | 1 | 0.3% | 낮음 | 〃 |
| oreum.json | 329 | basic_info.climb_time_min | 72 | 21.9% | 중간 | CSV 원본 자체 결측 |
| oreum.json | 329 | basic_info.distance_km | 129 | 39.2% | 중간 | 〃 |
| oreum.json | 329 | basic_info.difficulty | 137 | 41.6% | 높음 | 〃 |
| oreum.json | 329 | basic_info.shape_direction | 157 | 47.7% | 낮음 | 〃 |
| oreum.json | 329 | basic_info.recommended_season | 187 | 56.8% | 낮음 | 〃 |
| oreum.json | 329 | notes | 145 | 44.1% | 낮음 | CSV 원본, 참고용 |
| oreum.json | 329 | kakao_map_url | 20 | 6.1% | 낮음 | CSV 원본 |
| oreum.json | 329 | facilities.surface | 262 | 79.6% | 낮음 | CSV 자유서술 |
| oreum.json | 329 | facilities.parking | 40 | 12.2% | 낮음 | 〃 |
| oreum.json | 329 | facilities.restroom | 43 | 13.1% | 낮음 | 〃 |
| oreum.json | 329 | facilities.trail_info | 49 | 14.9% | 낮음 | 〃 |
| oreum.json | 329 | facilities.hours_fee | 314 | 95.4% | 낮음 | 〃 |
| **oreum.json (map_editor 4대 핵심 필드)** | 329 | **coordinates.peak** | 16 | **4.9%** | 높음 | CSV 원본 좌표, map_editor는 편집 불가 |
| **oreum.json (map_editor)** | 329 | **coordinates.entrances (오름 단위)** | 182 | **55.3%** | **높음** | 어제 55.5%(182/328)에서 미세 개선(오름 수 +1 반영) |
| **oreum.json (map_editor)** | 329 | **coordinates.parking (오름 단위)** | 210 | **63.8%** | **높음** | 어제 73.8%(242/328 존재 기준 환산)에서 개선 |
| **oreum.json (map_editor)** | 329 | **coordinates.restroom** | 299 | **90.9%** | **매우 높음** | 여전히 가장 심각한 결측 필드 |
| **oreum.json (map_editor)** | 329 | **trails (오름 단위)** | 179 | **54.4%** | **높음** | 어제 68.3%(224/328)에서 크게 개선 |
| oreum.json (trail 단위, n=165) | 165 | trails[].surface_type | 162 | 98.2% | 중간 | 난이도 자동계산 공식 미구현 상태라 당장 영향 적음 |
| oreum.json (trail 단위, n=165) | 165 | trails[].length_m | 3 | 1.8% | 낮음 | 서버 자동계산이라 사실상 정상 |

**map_editor 4대 핵심 필드(입구/주차장/화장실/등산로, 오름 단위) 평균 결측률**: (55.3 + 63.8 + 90.9 + 54.4) / 4 = **66.1%** (참고: 8/11 리포트의 76.5%에서 계산식 기준으로 개선됨 — 단, 오름 모수가 328→329로 바뀌어 완전히 동일한 산식은 아님)

**계산 불가/제외한 데이터**:
- `data/oreum.db` (SQLite): 파일 존재(마지막 수정 2026-08-07 11:27, 오늘 변경 없음)하지만 `CLAUDE.md`에 명시된 대로 map_editor가 전혀 읽거나 쓰지 않는 레거시 경로라 현재 수집 상태를 반영하지 않음 — 결측률을 계산해도 의미가 없어 제외. 최신화하려면 `sync_json_to_db.py`를 실행해야 하나 오늘은 실행하지 않음.
- `data/no_oreum.json`: `CLAUDE.md`에 "미사용, 데이터 소스로 취급 금지"로 명시되어 제외(마지막 수정 2026-08-07, 오늘 변경 없음).
- `db/schema.sql`: 스키마 정의 파일이라 결측률 개념 자체가 해당 없음.

---

## 7. 전체 요약

### 오늘 가장 중요한 성과

1. Map Editor 검색 UI에 "등산로 정보 있음인데 미수집" 오름을 빨간 배지 + 전용 필터로 표시하는 기능을 추가하고, 실제 서버 응답으로 검증(135건 정확히 일치) — 사용자가 이어서 실제로 이 표시를 활용해 오늘 하루에만 46개 오름의 등산로를 채움(`needs_trail` 135→89).
2. `scripts/migrate_entrances_and_drop_trail_start.py`에서 재실행 시 모든 입구 데이터를 삭제할 수 있는 실제 데이터 파괴 버그를 발견하고 가드를 추가해 영구적으로 안전하게 만듦(드라이런으로 검증 완료).
3. "서걸세" 오름을 사용자 제공 정보 기준으로 신규 추가(`id: 329`) — 누락된 region/address는 질문으로 확인 후 반영.

### 현재 가장 큰 문제

1. `coordinates.restroom` 결측률 90.9%(299/329) — map_editor 4대 핵심 필드 중 가장 심각.
2. `coordinates.peak` 결측 건수가 며칠째 원인 불명으로 계속 변동(8/10 21건 → 8/11 17건 → 오늘 16건) — map_editor에는 peak 편집 기능이 없는데도 수치가 바뀌는 경위가 코드/커밋 이력으로 추적 안 됨.
3. `trails[].surface_type` 98.2% 결측 — 관리자 등급표 기반 난이도 자동계산 공식이 아직 코드에 구현되지 않은 상태라 이 결측이 당장의 기능 결손으로는 이어지지 않지만, 난이도 계산 기능을 만들려면 반드시 선행되어야 함.

### 데이터 상태

- 전체 데이터 규모: 329건 (어제 328건 + 서걸세 1건)
- 주요 데이터: 기본정보(CSV 원본, 대부분 완비) + 좌표/등산로(map_editor 수집, 오늘 크게 개선)
- 평균/전체 결측률: map_editor 핵심 4항목(입구/주차장/화장실/등산로) 평균 **66.1% 결측**
- 가장 결측률이 높은 데이터: `coordinates.restroom` (90.9%)
- 데이터 품질상 가장 큰 문제: 화장실 좌표 수집이 다른 3개 항목(입구/주차/등산로)에 비해 압도적으로 뒤처져 있음 + `peak` 결측 변동의 원인 불명

### 다음 작업 우선순위

1. [높음] `coordinates.restroom` 좌표 수집 (299건 잔여, 4대 항목 중 최우선)
2. [높음] `trails` 없는 오름 179건 중, 오늘 추가한 "등산로 필요" 필터로 걸러지는 89건(등산로정보 "있음")부터 우선 수집
3. [중간] `coordinates.peak` 결측 16건의 변동 원인 규명 (수동 편집이라면 절차 문서화)
4. [중간] `facilities.*` 텍스트 필드가 map_editor 밖에서 수정된 정황(오늘 `restroom` 필드 221→217) 원인 확인 및 편집 규칙 명문화
5. [낮음] `trails[].surface_type` 입력을 등산로 저장 시 필수 또는 경고로 유도(난이도 자동계산 착수 전 선행 작업)

### 내일 Claude Code에게 먼저 시킬 작업

```
1. data/oreum.json에서 coordinates.restroom.lat/lng이 없는 오름 목록을 뽑아줘.
   그중 facilities.restroom이 "없음"이 아닌 것만 걸러서(=실제로 화장실이 있는데
   좌표만 못 찍은 곳) 몇 개인지 알려줘.

2. map_editor UI에 "화장실 있는데 좌표 미수집"인 오름만 보는 필터도
   등산로 필터(needs-trail-checkbox)와 같은 방식으로 하나 더 추가해줘.

3. coordinates.peak가 없는 16개 오름 목록을 뽑고, 각 오름의 data/오름_dataset.csv
   원본 행과 현재 data/oreum.json 값을 비교해서 CSV 자체 결측인지
   아니면 CSV엔 있는데 변환 과정에서 빠진 건지 확인해줘.

4. scripts/migrate_parking_to_array_and_add_notes.py 외에 저장소에 있는
   다른 1회성 스크립트들(scripts/ 디렉토리 전체)도 오늘처럼 재실행 안전성을
   코드 리뷰해줘.

5. 오늘 변경사항(data/oreum.json, map_editor/app.py, map_editor/static/index.html,
   scripts/migrate_entrances_and_drop_trail_start.py)을 커밋해줘. 커밋 메시지는
   "등산로 미수집 오름 표시 기능 추가 + 마이그레이션 스크립트 멱등성 버그 수정"
   같은 식으로 오늘 세션 리포트(docs/session-report-2026-08-12.md) 내용을 참고해서 작성해줘.
```

### 한 문단 요약

오늘은 지난 세션에서 놓쳤던 등산로 미수집 오름(135건)을 사용자가 직접 채워나갈 수 있도록 Map Editor에 실시간 필터/배지 기능을 추가했고, 그 결과 사용자가 세션 중에 실제로 46개 오름의 등산로를 채워 잔여 89건까지 줄였다. 동시에 코드 리뷰 요청을 통해 재실행 시 입구 데이터를 통째로 삭제할 수 있었던 마이그레이션 스크립트의 숨은 버그를 찾아 영구적으로 고쳤고, 사용자가 제공한 정보로 신규 오름("서걸세", id 329)을 추가했다. 다만 화장실 좌표(90.9% 결측)와 peak 좌표 결측 건수가 며칠째 원인 불명으로 계속 바뀌는 문제, 그리고 map_editor가 건드리지 않는 `facilities.*` 텍스트 필드가 알 수 없는 경로로 바뀐 정황은 여전히 미해결로 남아 있어, 내일은 이 두 가지의 원인 규명과 화장실 좌표 수집 가속화가 최우선 과제다.
