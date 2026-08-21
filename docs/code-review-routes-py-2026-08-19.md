# 코드 리뷰 학습 노트 — `oreum_mcp/modules/routes.py`

- 시작일: 2026-08-19 / 이어서 진행: 2026-08-21
- 진행 방식: `routes.py`를 1번 줄부터 섹션(임포트/클래스/함수) 단위로 나눠서 정독. 코딩 1년차 주니어 기준으로 설명.
- 진행 상황: **1~194줄 완료** (`RecommendRequest` 전체 + `OreumIdentifierRequest` + `register_routes` 시작부 + `recommend_oreum`의 필터링 for-loop까지). 다음은 196줄(정렬 로직)부터 이어서.
- **주의**: 2026-08-19 이후 `routes.py`가 일부 수정됨(`strip_coordinates`/`resolve_linked_oreums` import 추가, `List` import 제거, `parking_coords[].official` 관련 등). 아래 08-21 섹션은 **수정된 최신 파일 기준 줄 번호**를 쓰므로, 위 08-19 섹션의 줄 번호(예: "105~110줄 `OreumIdentifierRequest`")와 몇 줄씩 어긋날 수 있음 — 최신 파일 기준이 맞는 번호임.

---

## 1줄: 파일 최상단 주석

```python
# FastAPI 라우트 1개는 MCP 도구 1개입니다.
```

이 프로젝트는 `FastMCP.from_fastapi()`로 일반 FastAPI 앱을 MCP 서버로 변환한다. `@app.post("/recommend")` 같은 FastAPI 라우트를 하나 만들면 그게 자동으로 `recommend_oreum`이라는 MCP 도구(tool)가 된다. 그래서 이 파일엔 별도의 "MCP 전용 코드"가 없고, FastAPI 라우트만 정의돼 있다.

## 3~4줄: 표준 라이브러리 import

```python
import re
from typing import Any, Dict, List, Optional
```

- `re`: 정규표현식 모듈. 20번 줄 숫자 추출용.
- `typing`: 타입 힌트 모듈.
  - `Optional[str]` = "`str`이거나 `None`" (`Union[str, None]`의 축약형)
  - `Dict[str, Any]` = 키는 문자열, 값은 뭐든 될 수 있는 딕셔너리
  - `List[str]` = 문자열들의 리스트
  - **중요:** 파이썬 타입 힌트는 기본적으로 "사람이 읽는 주석"에 가깝고 실행을 막지 않는다. 단, Pydantic의 `BaseModel` 필드에서는 Pydantic이 이 힌트를 실제로 읽어서 검증/변환에 사용하므로 "진짜로 작동하는 규칙"이 된다.

## 6~7줄: 외부 라이브러리 import

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator
```

- `FastAPI`: 웹 프레임워크의 앱 클래스(설계도). `app = FastAPI()`로 실제 서버 인스턴스(앱 객체)를 만든다. `register_routes(app: FastAPI)`(112줄)는 이 앱 객체를 받아서 라우트(`/recommend`, `/oreum`, `/linked`)를 등록해주는 조립 함수. 실제 `app = FastAPI()`는 `oreum_mcp/app.py`에서 만들어지고, 거기서 `register_routes(app)`을 호출하는 구조로 추정.
- **Pydantic이란?** "이 데이터는 이런 필드/타입을 가져야 한다"를 클래스로 선언하면 자동으로 JSON ↔ 파이썬 객체 검증·변환을 해주는 라이브러리. 예: `max_distance_km: Optional[float] = Field(gt=0)`이라고 선언해두면, 클라이언트가 0 이하 값을 보내면 개발자가 직접 `if` 체크 안 해도 자동으로 422 에러가 난다.
  - `BaseModel`: Pydantic 스키마 클래스의 베이스. 상속하면 자동 검증/변환 기능이 생김.
  - `Field`: 필드에 기본값·설명(description)·제약조건(`gt`, `ge`, `le` 등)을 붙일 때 사용.
  - `model_validator`: 모델이 파싱되기 전/후에 커스텀 검증·변환 로직을 끼워 넣는 데코레이터. `mode="before"`는 "필드 개별 검증 전에 입력 딕셔너리 전체를 먼저 손본다"는 뜻.

## 9~18줄: 로컬 모듈 import

```python
from .data import (
    completeness_score,
    entrance_coords,
    find_oreum,
    has_access_restriction_keyword,
    load_oreums,
    parking_coords,
    restroom_coord,
    to_summary,
)
```

- `.data`는 같은 패키지(`modules/`) 안의 `data.py`를 가리키는 상대 import. 점(`.`) 하나 = "현재 패키지".
- 이 함수들은 `data.py`에 정의되어 있고, `data/oreum.json`을 읽고 가공하는 로직을 담당. `routes.py`는 이 함수들을 조합해서 API 응답을 만드는 역할만 하고, 실제 데이터 접근/가공은 `data.py`에 위임.
- 각 함수는 실제 사용 지점에서 설명 예정 (`load_oreums()`→119줄, `find_oreum()`→219줄 등, 아직 상세 리뷰 전).

---

## 20줄: `_LEADING_NUMBER` 정규식

```python
_LEADING_NUMBER = re.compile(r"-?\d+(\.\d+)?")
```

- `re.compile(...)`로 정규식 패턴을 미리 컴파일해서 변수에 저장 (매번 새로 만들면 느리므로).
- 패턴 뜻: `-?`(마이너스 기호 있어도/없어도) `\d+`(숫자 1개 이상) `(\.\d+)?`(소수점+숫자, 있어도/없어도) → 문자열 맨 앞에서 `"30"`, `"-5"`, `"1.5"` 같은 숫자를 잡아낸다.
- **실제로 뽑는 숫자가 뭐냐면:** `max_distance_km`/`max_climb_time_min` 필드에 `"30분"`, `"1.5km"`처럼 단위가 붙은 문자열이 들어왔을 때, 그 앞부분 숫자만(`"30"`, `"1.5"`) 추출해서 Pydantic이 `int`/`float`로 변환할 수 있게 만든다. 39~41줄에서 실제 사용됨.

## 22~25줄: 주석 + `_NUMERIC_FIELDS`

```python
# 사람이나 LLM이 폼/자연어로 채우다 보면 숫자 필드에도 "30분", "1.5km"처럼
# 단위가 붙은 문자열이 들어올 수 있다. 순수 숫자를 요구하는 대신, 앞의 숫자만
# 뽑아 쓰는 게 422로 막는 것보다 실사용에 낫다고 판단.
_NUMERIC_FIELDS = {"max_distance_km", "max_climb_time_min"}
```

- 왜 이런 전처리가 필요한지에 대한 설계 근거 주석.
- `_NUMERIC_FIELDS`: 숫자 필드로 취급해서 단위 텍스트를 벗겨낼 대상 키 집합(`set`). `RecommendRequest`의 `max_distance_km`, `max_climb_time_min` 두 필드만 해당.

## 28~44줄: `_normalize_request_dict` 함수

```python
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
```

- 함수명 앞 `_`: 파이썬 관례상 "모듈 내부 전용" 표시(강제는 아님).
- `data: Any`, `-> Any`: 입출력 타입을 특정하지 않음 — 실제로 딕셔너리인지는 32줄에서 직접 확인.
- **32~33줄 방어 코드**: `isinstance(data, dict)`로 딕셔너리인지 확인. 아니면(`not`) 그대로 리턴하고 종료. `model_validator(mode="before")`는 아직 검증 전 원본 입력을 받으므로 항상 dict라는 보장이 없어 안전장치를 둠.
- **35줄**: 원본을 직접 수정하지 않고 새 딕셔너리 `result`에 변환값을 채우는 방식.
- **36줄**: `data.items()`로 (키, 값) 쌍을 순회. 예: `{"max_distance_km": "1.5km", "difficulty": ""}` → `("max_distance_km", "1.5km")`, `("difficulty", "")` 순서로 순회.
- **37~38줄**: 값이 빈 문자열이면 `None`으로 변환. `Optional[str]`은 `""`도 타입상 유효하지만, 숫자 필드에 `""`가 그대로 들어가면 `float`/`int` 변환이 안 돼 422가 나므로 미리 `None`으로 정리.
- **39~41줄**: `elif`이므로 위 조건에 안 걸렸을 때만 검사. 조건: 이 키가 `_NUMERIC_FIELDS`에 속하고(`k in _NUMERIC_FIELDS`) 값이 문자열(`isinstance(v, str)`)이면, `.strip()`으로 공백 제거 후 정규식 매치. `match.group() if match else v`는 삼항 표현식(한 줄 if-else) — 매치 성공 시 추출된 숫자 문자열, 실패 시 원본 값 그대로.
- **42~43줄**: 그 외 경우는 원본 값을 그대로 복사.
- **44줄**: 완성된 딕셔너리 리턴 → 이후 Pydantic이 이 값으로 각 필드를 검증/변환.

**한 줄 요약**: 클라이언트가 보낸 원본 딕셔너리를 돌면서, `""`는 `None`으로, `"30분"` 같은 값은 `"30"`으로 미리 손질해 Pydantic 검증 실패를 막는 전처리기.

---

## 47~102줄: `RecommendRequest` 클래스

`/recommend` API(MCP 도구 `recommend_oreum`)가 받는 요청 body 스키마. "이 API를 호출하려면 어떤 필드를 어떤 타입으로 보낼 수 있는지"를 선언.

### 47줄: 클래스 선언
```python
class RecommendRequest(BaseModel):
```
`BaseModel` 상속 → 자동 JSON ↔ 파이썬 객체 변환 + 검증 기능 획득.

### 48~51줄: 커스텀 검증 로직 연결
```python
@model_validator(mode="before")
@classmethod
def _normalize(cls, data: Any) -> Any:
    return _normalize_request_dict(data)
```
- `@model_validator(mode="before")`: Pydantic이 필드 개별 검증을 하기 **전에** 이 메서드를 먼저 실행.
- `@classmethod`: 아직 인스턴스가 없는 단계(검증 전)라 `self`가 아니라 `cls`를 받음.
- 실제 로직은 앞서 만든 `_normalize_request_dict(data)`를 그대로 호출 — "클래스 전용 검증기" 틀만 씌우고 로직은 재사용.

### 필드들 공통 패턴
`필드명: 타입 = Field(default=기본값, ..., description="...")` 형태 반복. `description`은 사람용 문서이자, MCP를 통해 LLM에게 "이 필드를 언제/어떻게 채워야 하는지" 전달하는 설명서 역할도 함(실제 도구 스펙에 노출됨).

| 필드 | 타입 | 기본값 | 제약 | 비고 / 실제 사용처 |
|---|---|---|---|---|
| `region` | `Optional[str]` | `None` | - | 주소 부분일치 필터. 148줄에서 `r.get("address")`에 부분 포함 여부 검사 |
| `difficulty` | `Optional[str]` | `None` | - | '쉬움'/'보통'/'어려움' 중 하나(코드로 강제 X, description으로만 안내). 150줄에서 정확히 일치(`==`) 비교 |
| `max_distance_km` | `Optional[float]` | `None` | `gt=0` | `_NUMERIC_FIELDS`에 포함되어 단위 텍스트(`"1.5km"`) 자동 정리 대상. `gt=0`은 0 이하 값 자동 422 |
| `max_climb_time_min` | `Optional[int]` | `None` | `gt=0` | 위와 동일 패턴, 정수(분 단위라 소수 불필요) |
| `season` | `Optional[str]` | `None` | - | 160줄에서 `recommended_season` 텍스트 부분 포함 검사 |
| `keyword` | `Optional[str]` | `None` | - | 자유 텍스트 검색. 180~189줄에서 이름/하이라이트/추천대상 텍스트 합쳐서 포함 여부 검사 |
| `access_open_only` | `bool` (Optional 아님!) | `False` | - | 명시적으로 제한 확인된 곳만 제외, 미분류는 포함시키는 안전-우선 정책. description이 유난히 긴 이유는 직관과 다른 동작(미확인=포함)을 LLM이 오해 없이 읽게 하려는 것 |
| `restroom_required` | `bool` | `False` | - | 화장실 좌표 수집 여부 하드 필터(177~179줄에서 안 맞으면 무조건 `continue`) |
| `limit` | `int` (Optional 아님) | `3` | `ge=1, le=50` | 반환 최대 개수. 범위 벗어나면 자동 422 |

- `Optional[...]`가 없는 필드(`access_open_only`, `restroom_required`, `limit`)는 `None`을 허용하지 않음 — 항상 값이 있어야 하고, 안 보내면 `default`로 채워짐.
- `gt`(greater than), `ge`(greater or equal), `le`(less or equal) 모두 Pydantic이 자동으로 검증해주는 제약 — 개발자가 직접 `if` 체크 코드를 안 써도 됨.

**핵심 정리**: `RecommendRequest` 자체는 필터링 로직을 전혀 담고 있지 않음. "입력값의 형태를 정의 + 검증"만 하고, 실제 필터링은 `recommend_oreum` 함수(118~210줄) 안에서 이 필드들을 하나씩 읽어서 수행한다.

---

---

## 2026-08-21 진행분 (최신 파일 기준 줄 번호)

## 108~112줄: `OreumIdentifierRequest` 클래스

```python
class OreumIdentifierRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="오름 이름(예: '가세오름') 또는 oreum.json의 id(숫자를 문자열로 전달, 예: '7').",
    )
```

- `RecommendRequest`와 별개의 작은 요청 모델. `get_oreum_detail`, `recommend_linked_oreums` 두 도구가 공유해서 씀.
- `identifier: str = Field(...)`에서 `...`(Ellipsis)는 "기본값 없음, 필수 필드"라는 뜻. `RecommendRequest`의 필드들은 전부 `default=None`/`default=False`였던 것과 대조적으로, 이건 반드시 값을 줘야 함.
- 이름이 `id`가 아니라 `identifier`인 이유는 타입이 `str` 하나로 이름과 id를 둘 다 받기 때문 — 실제로 이름/숫자 어느 쪽이 들어왔는지 구분하는 로직은 여기가 아니라 `find_oreum()`(`modules/data.py`)에 있음. 숫자 id도 "문자열로 전달"하라고 명시한 이유는, 이 모델 타입이 그냥 `str`이라 정수를 넣으면 타입이 안 맞기 때문(명확성을 위해 문자열로 받는 규약).

## 115번 줄: `register_routes` 함수 시작

```python
def register_routes(app: FastAPI) -> None:
```

- 이 함수가 실제로 3개의 라우트(`/recommend`, `/oreum`, `/linked`)를 `app`에 등록함. `oreum_mcp/app.py`에서 이 함수를 호출해서 FastAPI 앱을 완성한 뒤, `FastMCP.from_fastapi()`로 감싸서 MCP 서버로 변환.
- "FastAPI 라우트 1개 = MCP 도구 1개" 원칙이 여기서 실현됨.

## 116~121줄: `/recommend` 라우트 데코레이터 + 함수 시그니처

```python
@app.post(
    "/recommend",
    operation_id="recommend_oreum",
    summary="조건(지역/난이도/거리/소요시간/계절/키워드)에 맞는 오름을 추천한다",
)
def recommend_oreum(request: RecommendRequest = RecommendRequest()) -> Dict[str, Any]:
```

- `operation_id="recommend_oreum"` — MCP 도구로 변환될 때 실제 도구 이름이 됨(라우트 경로 `/recommend`가 아니라).
- `summary`는 도구 설명으로 노출되어 LLM이 "이 도구가 뭘 하는지" 판단하는 근거가 됨.
- `request: RecommendRequest = RecommendRequest()` — 파라미터에 **기본값으로 빈 인스턴스**를 줌. 이유: 본문 파라미터에 기본값이 없으면 요청 body를 아예 안 보냈을 때 FastAPI가 422를 냄. 인자 없이 호출해도(`recommend_oreum()`) 모든 필드가 기본값인 요청으로 동작하게 만든 것.

## 122번 줄: 데이터 로드

```python
records = load_oreums()
```

`modules/data.py`의 함수. 매 요청마다 `data/oreum.json`을 새로 읽음 — `oreum_mcp`는 read-only이고 캐싱 없이 매번 재로드해서, map_editor에서 수집한 데이터가 서버 재시작 없이 바로 반영되도록 설계된 부분.

## 124~138줄: `region_only` 판정

```python
region_only = (
    request.region is not None
    and request.difficulty is None
    and request.max_distance_km is None
    and request.max_climb_time_min is None
    and request.season is None
    and request.keyword is None
)
```

- "지역만 지정하고 다른 필터는 아무것도 안 준 경우"를 판별하는 플래그.
- `True`가 되려면: `region`은 반드시 값이 있어야 하고(`is not None`), 나머지 5개 필드(`difficulty`, `max_distance_km`, `max_climb_time_min`, `season`, `keyword`)는 전부 기본값(`None`)이어야 함.
- **주의**: `access_open_only`, `restroom_required`, `limit`은 이 판정에 포함되지 않음 — `access_open_only=True`를 켜도 `region_only` 여부에는 영향 없음(주석에 명시).
- 나중에(209번 줄) `picked = candidates[:3] if region_only else candidates[: request.limit]`에서 사용 — 지역만 준 "느슨한 질의"는 결과가 너무 많이 쏟아질 수 있으니 `limit` 값과 무관하게 무조건 3개로 캡하고, 그 외엔 사용자가 지정한 `limit`(기본 3, 최대 50)을 따름.
- 왜 이런 특별 취급을 하는가: 예전엔 8개 필드(난이도/거리/소요시간/계절 + 4개 좌표류)를 전부 요구하는 하드 필터였는데, 화장실 좌표 수집률이 낮아 지역별로 결과가 통째로 0건이 되는 문제가 있어 completeness_score 기반 랭킹으로 개편됨. "필터 조건이 거의 없는 경우엔 정보가 가장 많이 채워진 오름 상위 3개를 보여준다"는 동작을 지원하기 위한 플래그.

## 140~194줄: 후보 필터링 for-loop

### 140~143줄: 왜 레코드 단위로 필터링하는가

```python
candidates = []
for r in records:
```

필터링은 원본 레코드(`r`) 단위로 하고, 정렬까지 끝난 뒤 마지막에(214번 줄) `to_summary()`로 변환. 이유: `distance_km` 같은 필드는 정렬 키로만 쓰이고 최종 응답에는 안 담기는데, 필터링 단계에서 이미 요약본으로 바꿔버리면 정렬 시점에 그 값을 다시 뽑아올 수 없기 때문.

### 144~146줄: 루프 안 준비

```python
basic = r.get("basic_info") or {}
notes = r.get("notes") or {}
```

`basic_info`나 `notes`가 `None`일 수 있으므로(`notes`는 `null` 허용), `or {}`로 빈 dict를 fallback시켜 이후 `.get()` 호출이 `AttributeError`를 내지 않도록 방어.

### 148~152줄: `region` 필터

```python
if request.region and request.region not in (r.get("address") or ""):
    continue
```

`region`이 `None`/빈 문자열이면 건너뜀. 값이 있으면 `region` 필드가 아니라 **`address` 전체 문자열**에 대해 부분일치 검사 — "제주특별자치도 OO시 OO읍 OO리 ..."가 다 들어있어 "한림"/"구좌" 같은 읍면동 지명도 걸림.

### 153~154줄: `difficulty` 필터

```python
if request.difficulty and basic.get("difficulty") != request.difficulty:
    continue
```

정확히 일치(`!=`)해야 통과. 값 자체는 검증 안 하므로 CSV 값과 정확히 같은 문자열이 아니면 매치 실패.

### 155~158줄: `max_distance_km` 필터

```python
if request.max_distance_km is not None:
    dist = basic.get("distance_km")
    if dist is None or dist > request.max_distance_km:
        continue
```

`dist is None`(거리 데이터 자체가 없는 오름)도 걸러냄 — "상한 이하인지 알 수 없으니 안전하게 제외". `access_open_only`의 null 처리(통과시킴)와 반대 방향이라 헷갈리지 말 것.

### 159~162줄: `max_climb_time_min` 필터

거리 필터와 완전히 동일한 패턴. `climb_time_min`이 없거나 상한을 초과하면 제외.

### 163~164줄: `season` 필터

```python
if request.season and request.season not in (basic.get("recommended_season") or ""):
    continue
```

부분일치. `region` 필터와 같은 패턴.

### 165~178줄: `access_open_only` 필터 (2단 체크)

```python
if request.access_open_only:
    status = (notes.get("access") or {}).get("status")
    if status not in (None, "open"):
        continue
    if has_access_restriction_keyword(r):
        continue
```

- 1단계: `notes.access.status`가 `None`이나 `"open"`이면 통과, 그 외(`reservation_required`/`restricted`/`prohibited`)면 제외. "확실히 위험이 확인된 것만 걸러낸다"는 안전 우선 원칙과 "미분류(null)까지 걸러내면 결과가 거의 0건"이라는 데이터 현실의 절충안.
- 2단계: 1단계는 `notes.access.status`라는 구조화된 필드에만 의존하는데, `notes` 자체가 `null`인 레코드(살핀오름/성진이오름 등)는 다른 필드(`facilities.hours_fee` 등)에 "출입제한" 문구가 텍스트로만 남아있는 경우가 있었음. `has_access_restriction_keyword(r)`가 레코드 전체 JSON 텍스트에서 이 문구를 검색해서 필드 위치와 무관하게 걸러냄.
- 두 체크 모두 `request.access_open_only`가 `True`일 때만 실행(중첩 `if`).

### 179~182줄: `restroom_required` 필터

```python
if request.restroom_required:
    restroom = (r.get("coordinates") or {}).get("restroom") or {}
    if restroom.get("lat") is None or restroom.get("lng") is None:
        continue
```

`coordinates.restroom.lat`/`lng` 둘 다 값이 있어야 통과하는 하드 필터.

### 183~192줄: `keyword` 필터

```python
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
```

검색 대상(`haystack`)을 오름 이름 + `notes.highlights`(리스트를 공백 연결) + `notes.recommend_for` 세 군데에서 조합, 이 안에 `keyword`가 부분일치하면 통과.

### 194줄: 통과한 레코드 누적

```python
candidates.append(r)
```

모든 필터를 통과한 레코드만 원본 그대로 `candidates`에 쌓임. 이 리스트가 다음 단계(196번 줄 이후)에서 `completeness_score` 기준으로 정렬됨.

**패턴 요약**: 전형적인 "얼리 컨티뉴(early continue)" 필터 체인 — 각 조건은 독립적으로 검사되고, 하나라도 실패하면 즉시 다음 레코드로 넘어가 나머지 체크를 생략. `None`/`or {}` 방어 코드가 반복되는 이유는 `data/oreum.json`의 여러 필드가 구조적으로 `null`을 허용하기 때문.

---

## 다음에 이어서 볼 부분

- **196~235줄**: `completeness_score` 정렬 로직, `picked`/`results` 조립, `map_url` 생성, 최종 응답 dict (`recommend_oreum` 나머지)
- **237~298줄**: `/oreum` (`get_oreum_detail`)
- **300~347줄**: `/linked` (`recommend_linked_oreums`)

## 학습 메모 (계속 헷갈리면 다시 볼 것)

- `Optional[X]` = `X` 또는 `None`. `Field(default=...)`는 값이 없을 때 채워지는 기본값이지 타입이 아님 — 둘은 별개 개념.
- Pydantic의 `Field(gt=..., ge=..., le=...)` 제약은 요청 자체를 자동으로 거부(422)시키는 "검증 규칙"이지, 비즈니스 로직(필터링)이 아님. 실제 "조건에 맞는 오름만 고르기"는 함수 본문에서 수동으로 함.
- `@model_validator(mode="before")`는 "원본 입력 다듬기" 단계, Pydantic 필드 검증(타입 체크, `gt`/`ge` 등)은 그 다음 단계. 순서를 헷갈리지 말 것.
- 필터 루프의 `None` 처리 방향이 필드마다 다름: `max_distance_km`/`max_climb_time_min`은 값이 없으면(null) 제외하지만, `access_open_only`는 값이 없으면(status: null) 오히려 통과시킴. "null = 모른다"를 안전 쪽으로 해석할지 관대한 쪽으로 해석할지는 필드 성격(수치 데이터 vs 위험 확인 여부)에 따라 다르게 설계된 것 — 일괄 규칙이 아니라 각각 이유가 있음.
