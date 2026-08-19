# 코드 리뷰 학습 노트 — `oreum_mcp/modules/routes.py`

- 시작일: 2026-08-19
- 진행 방식: `routes.py`를 1번 줄부터 섹션(임포트/클래스/함수) 단위로 나눠서 정독. 코딩 1년차 주니어 기준으로 설명.
- 진행 상황: **1~102줄 완료.** 다음은 105줄(`OreumIdentifierRequest`)부터 이어서.

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

## 다음에 이어서 볼 부분

- **105~110줄**: `OreumIdentifierRequest` 클래스 (아직 미검토)
- **112줄~**: `register_routes(app: FastAPI)` 함수 본문
  - `/recommend` (`recommend_oreum`, 113~210줄)
  - `/oreum` (`get_oreum_detail`, 212~273줄)
  - `/linked` (`recommend_linked_oreums`, 275~319줄)

## 학습 메모 (계속 헷갈리면 다시 볼 것)

- `Optional[X]` = `X` 또는 `None`. `Field(default=...)`는 값이 없을 때 채워지는 기본값이지 타입이 아님 — 둘은 별개 개념.
- Pydantic의 `Field(gt=..., ge=..., le=...)` 제약은 요청 자체를 자동으로 거부(422)시키는 "검증 규칙"이지, 비즈니스 로직(필터링)이 아님. 실제 "조건에 맞는 오름만 고르기"는 함수 본문에서 수동으로 함.
- `@model_validator(mode="before")`는 "원본 입력 다듬기" 단계, Pydantic 필드 검증(타입 체크, `gt`/`ge` 등)은 그 다음 단계. 순서를 헷갈리지 말 것.
