# 2026-08-20 작업 정리 보고서

오늘은 두 부분으로 나뉩니다. **연계오름/고도 프로파일 기능**(코드 변경, 이 세션 초반에 커밋 완료)과, 그 이후 이 세션 대부분을 차지한 **Docker 기반 로컬 통합 테스트 환경 구축**(코드 변경 거의 없음, 인프라/설정 작업 + 디버깅)입니다. `git log`/`git status`와 이 세션의 대화 기록을 기준으로 작성했습니다.

---

## 1. 코드 변경 (커밋 완료)

| 커밋 | 내용 |
|---|---|
| `f4e7de3` (오늘, 이 세션 초반) | `docs/session-report-2026-08-19.md`에서 미커밋으로 남아있던 연계오름/고도 프로파일 작업 일체를 커밋. 추가로 `oreum_mcp/docker-compose.yml`에 `OREUM_MCP_PUBLIC_URL` 환경변수, `./static` 볼륨, `etri-jejuax-gateway-network`에 `external: true` 추가. `oreum_mcp/static/index.html`(추천 오름 지도 보기 페이지, 333줄 신규) 및 `/view`, `/view/data` 라우트 추가. `modules/data.py`에 `strip_coordinates()` 추가해 `recommend_oreum` 응답에서 좌표 필드 제외 |

이 커밋 자체는 `docs/session-report-2026-08-19.md`가 "다음 작업 우선순위"로 남긴 "미커밋 작업 커밋"을 이 세션 시작 시점에 처리한 것으로 보입니다(세션 앞부분은 컨텍스트 압축으로 요약만 남아 상세 대화는 확인 불가).

---

## 2. 이 세션에서 진행한 것 (Docker 통합 테스트 환경 구축)

### 2-1. `docker-compose.yml` 네트워크 설정 점검

`sample_MCP/docker-compose.yml`을 대조해, `etri-jejuax-gateway-network`에 `external: true`가 빠지면 이 compose를 먼저 올릴 때 동일 이름의 새 네트워크를 만들어버려 실제 gateway/hostllm 네트워크와 분리될 위험이 있음을 확인 → 이미 위 1절 커밋에 반영되어 있었음을 재확인.

### 2-2. 로컬 Ollama 컨테이너 구축 및 `docker-compose.test.yml` 분리

- host LLM 역할을 로컬에서 재현하기 위해 `ollama/ollama` 이미지로 `ollama-test` 컨테이너를 `etri-jejuax-gateway-network`에 올림 (처음엔 `docker run` ad-hoc 명령으로, 이후 사용자가 "별도 테스트 전용 `docker-compose.test.yml`로 분리"를 선택해 재구성).
- 컨테이너 이미지 pull이 회사망 특유의 간헐적 저속/정체 현상으로 여러 차례 지연됨(이전 세션의 ngrok DNS 차단 문제와 동일 계열) — `docker run` 백그라운드 실행과 `docker pull` 직접 실행을 병행해 진행 상황을 확인하며 완료.
- Compose로 전환하는 과정에서 **볼륨 이름 자동 접두사 문제** 발견: `docker-compose.test.yml`의 `ollama-test-data:` 볼륨에 `name:`을 명시하지 않으면 Compose가 `oreum_mcp_ollama-test-data`라는 새 볼륨을 만들어버려, 이미 받아둔 `qwen:4b` 모델이 안 보이는 문제 발생 → `name: ollama-test-data`를 명시해 기존 볼륨에 정상적으로 재연결, 모델 데이터 보존 확인.
- 최종 `oreum_mcp/docker-compose.test.yml` 신규 생성(미추적 상태) — `ollama-test` 서비스, 이름이 고정된 `ollama-test-data` 볼륨, `external: true`로 참조하는 `etri-jejuax-gateway-network`.

### 2-3. 컨테이너 간 통신 검증

- `ollama-test` 컨테이너에는 `curl`/`wget`이 없어(`ollama/ollama` 이미지가 최소 구성) 직접 테스트 불가 → `curlimages/curl` 임시 컨테이너를 같은 네트워크에 붙여 `http://oreum-mcp:11010/health`를 호출해 양방향 연결성 확인.
- `fastmcp.Client`로 `recommend_oreum` 툴을 직접 호출해 실제 오름 데이터가 정상 반환되고 `strip_coordinates()`가 적용되어 있음을 확인.
- Docker 개념 설명 다수 요청에 답변: 네트워크 이름과 실제 IP의 관계, 볼륨 vs 바인드 마운트(`oreum_mcp`의 `./modules:/app/modules` 마운트를 예시로 설명), `environment:` 블록의 역할, 로컬에서 `routes.py`를 수정하면 컨테이너에도 즉시 반영되지만(바인드 마운트) 실행 중인 프로세스는 `--reload` 없이는 재시작 전까지 옛 코드로 계속 동작한다는 점.

### 2-4. `ollmcp` + qwen 모델 툴콜 실패 디버깅

- `ollmcp -H http://localhost:11434 -m qwen:4b -u http://localhost:11010/`로 첫 테스트 시 "No Response from Model" 에러 발생 → `qwen:4b`가 툴콜 학습이 안 된 구세대 Qwen1 태그임을 확인(과거 세션 보고서에서 원래 의도한 모델은 `qwen3:4b`였음을 교차 확인), `qwen3:4b`를 추가로 pull.
- `qwen3:4b`로 재시도해도 동일하게 "No Response from Model" 재발 → 원인 후보를 좁히기 위해 `ollmcp --help`에서 타임아웃 설정 확인(없음), `oreum_mcp`의 실제 툴 스키마 크기 측정(3개 툴 합계 2,310자, `instructions` 936자 — qwen3:4b의 262,144토큰 컨텍스트에 비해 지나치게 작아 "스키마가 너무 복잡해서 실패" 가설은 기각), Windows 콘솔 mojibake로 인해 한글 페이로드가 깨져 보내진 문제를 UTF-8 파일 경유 방식으로 우회해 raw `/api/chat` 테스트는 정상적으로 툴콜에 성공함을 확인.
- 현재 결론(미확정): CPU 전용 추론 + qwen3 기본 thinking 모드의 장문 추론이 `ollmcp` 쪽 타임아웃을 넘겨 응답이 끊기는 것으로 추정. `pip show`/`uv`가 아닌 다른 경로로 설치된 것으로 보여 `mcp_client_for_ollama` 패키지 소스에서 타임아웃 값을 직접 확인하지는 못함. thinking mode 끄기 / 더 오래 기다리기 / 더 큰 모델(qwen2.5:7b 등) 시도 3가지 대안을 제시했으나 사용자가 아직 택하지 않음 — **미해결 상태로 다음 우선순위에 남음**.

### 2-5. MCP Inspector로 서버 단독 검증 시도

`ollmcp`(LLM 경유)와 서버 자체 문제를 분리하기 위해 `npx @modelcontextprotocol/inspector`로 `oreum_mcp`에 직접 붙는 방법을 안내(Streamable HTTP, `http://localhost:11010/`) → 실행은 됐으나 사용자가 "끄고 컨테이너 상태나 리뷰해줘"로 방향 전환, 백그라운드 프로세스는 `TaskStop`으로 종료. 실제 Inspector를 이용한 검증은 진행되지 않음.

### 2-6. 컨테이너 상태 점검

`docker ps -a`, `docker exec ollama-test ollama list`, `docker network inspect`로 최종 상태 확인:
- `oreum-mcp`: healthy, 약 1시간 가동
- `ollama-test`: 정상 가동 57분, `qwen:4b`/`qwen3:4b` 모두 보유
- 둘 다 `etri-jejuax-gateway-network`(172.18.0.0/16)에서 이름 기반 통신 가능한 상태 유지

### 2-7. 실제 플랫폼 연동을 위한 변경점 정리

`sample_MCP2/etri-jejuax-example-mcp/등록화면.png`(플랫폼의 "MCP 서버 관리" 등록 UI 스크린샷)를 근거로, 로컬 테스트 환경에서 실 배포로 넘어갈 때 필요한 변경을 정리:
- `.env`의 `OREUM_MCP_PUBLIC_URL`/`NGROK_AUTHTOKEN`을 실제 값으로 채워야 함(현재 비어있음 확인).
- `docker-compose.test.yml`(ollama-test)은 실 배포엔 불필요 — hostllm이 이미 별도 존재.
- 플랫폼 관리 화면에 서버 이름/공개 URL/`streamable_http` transport로 직접 등록해야 하며, 등록 시 플랫폼이 자동으로 `tools/list`를 호출해 검증함.
- `/view` 페이지의 Kakao Maps JS 키에 실제 공개 도메인을 Kakao 콘솔에서 별도 허용해야 함.
- `../data:/app/data:ro` 상대경로 볼륨 마운트는 레포 구조를 그대로 배포하면 자동으로 맞음.

---

## 3. 오늘 명령한 것들 (이 세션 기준)

| # | 요청 내용 (요약) | 실제 수행 작업 | 결과 |
|---|---|---|---|
| 1 | host Ollama(qwen:4b) + MCP서버 두 개를 같은 네트워크로 띄워 통신/실데이터 조회까지 테스트 | Docker Desktop 확인(이미 설치됨) → `ollama-test` 컨테이너 구축, 네트워크 연결, `recommend_oreum` 실호출 검증 | ✅ 완료 |
| 2 | (진행 중 질문) 컨테이너 두 개 생겼는지 | `docker ps` 확인 | ✅ 확인 |
| 3 | (스크린샷) 메모리 때문에 느린지 문의 | 메모리 사용량 확인(82MB/61GB, 문제 아님) → 회사망 저속 문제로 재설명 | ✅ 정보 제공 |
| 4 | 구조 이해를 위한 설명 요청 다수 (네트워크/볼륨/`ollmcp`/컨테이너 생성 코드 위치/네트워크-IP 관계/`environment` 블록) | 실제 시스템 조회 결과(`docker network inspect`, 파일 내용) 기반으로 순차 설명 | ✅ 정보 제공 |
| 5 | ad-hoc `docker run` 명령을 파일로 저장 | `docker-compose.test.yml`로 분리 생성(사용자가 옵션 선택) | ✅ 완료 |
| 6 | 기존 컨테이너를 compose 관리로 전환(모델 재다운로드 없이) | 볼륨 이름 접두사 문제 발견·수정 후 전환 | ✅ 완료 |
| 7 | ngrok 지금 되는지 재확인 | DNS 차단 재확인(`tunnel.us.ngrok.com` → 사내 DNS 응답, TLS 실패) | ⚠️ 여전히 차단, 우회 시도 안 함 |
| 8 | 직접 통신/응답 검증할 방법 문의 | `curlimages/curl` 임시 컨테이너 활용법, `fastmcp.Client` 스크립트 안내 | ✅ 정보 제공 |
| 9 | `ollmcp` + `qwen:4b` "No Response from Model" 에러 공유 | 구세대 모델(툴콜 미지원) 진단 → `qwen3:4b` pull 제안 | ✅ 원인 규명 |
| 10 | `qwen3:4b`로도 여전히 실패 | 스키마 크기/타임아웃/thinking mode 등 다각도 재진단 | ⚠️ 근본 원인 미확정, 대안 3가지 제시 |
| 11 | 로컬 IDE에서 파일 수정하면 컨테이너에도 반영되는지 | 바인드 마운트 vs 실행 중 프로세스 재로딩 차이 설명 | ✅ 정보 제공 |
| 12 | MCP Inspector로 디버깅하겠다 | `npx @modelcontextprotocol/inspector` 실행 및 접속 링크 안내 | ✅ 실행됨 (검증은 미진행) |
| 13 | Inspector 끄고 컨테이너 상태 리뷰 요청 | 백그라운드 프로세스 종료(`TaskStop`), `docker ps -a`/`ollama list`/`network inspect`로 상태 정리 | ✅ 완료 |
| 14 | 실제 플랫폼에 붙이려면 뭘 바꿔야 하는지 문의 | `sample_MCP2` 등록화면 스크린샷 근거로 설정값/제외 대상/외부 액션 구분 정리 | ✅ 정보 제공 |
| 15 | 08-19 양식으로 오늘자 보고서 작성 | `git log`/`git status` 확인 후 본 보고서 작성 | 진행 중(본 문서) |

---

## 4. 오늘 명령에서 발생한 특이사항

- `winget install`로 Docker Desktop을 설치하려던 시도는 사용자가 명시적으로 거부 — 이미 사용자가 직접 설치를 진행 중이었던 것으로 확인되어, 재시도 없이 대기 후 사용자의 설치 완료 확인을 받고서야 다음 단계로 진행.
- 이미지 pull이 회사망 문제로 여러 차례 느려지거나 멈춘 것처럼 보였는데, 매번 실제로는 백그라운드에서 계속 진행되고 있었음 — `run_in_background` + `ScheduleWakeup` 조합으로 폴링 없이 대기.
- `ollmcp` 툴콜 실패는 이 세션 안에서 완전히 해결되지 않은 채로 남음 — "스키마가 너무 복잡하다"는 초기 가설을 실측으로 직접 기각하고 "CPU 추론 속도 + thinking mode 타임아웃"으로 진단을 수정한 점이 특이사항(가설을 검증 데이터로 뒤집은 사례).

---

## 5. Git 커밋 현황

| 커밋 | 내용 |
|---|---|
| `f4e7de3` | 오늘 세션 초반에 커밋됨 — 연계오름/고도 프로파일 기능 + `docker-compose.yml` 네트워크·볼륨·환경변수 정비 + `/view` 지도 페이지 신규 |
| `23eddbd`, `6bea70d`, `71a155a`, `6e26d06` | 이전 세션 커밋 (변동 없음) |

오늘 세션 후반부(Docker 통합 테스트)는 인프라/로컬 검증 작업 위주라 **커밋 대상 코드 변경이 없습니다.** 유일한 미추적 파일은 `oreum_mcp/docker-compose.test.yml`(로컬 전용 Ollama 테스트 compose) — 실 배포에 포함되지 않는 파일이라 커밋 여부는 사용자 판단 필요(레포에 남겨 재사용할지, 로컬에만 둘지).

---

## 6. 전체 요약

**오늘 가장 중요한 성과**
- 이전 세션에서 미커밋으로 남아있던 연계오름/고도 프로파일 작업 + `docker-compose.yml` 정비(`external: true`, `OREUM_MCP_PUBLIC_URL`, `/view` 지도 페이지)를 커밋 완료했습니다.
- `oreum-mcp`와 `ollama-test`(qwen:4b, qwen3:4b) 두 컨테이너를 `etri-jejuax-gateway-network`라는 같은 Docker 네트워크에 올려, 실제 배포 아키텍처(gateway/hostllm 네트워크 공유)를 로컬에서 재현하고 상호 통신·실데이터 조회까지 검증했습니다.
- ad-hoc하게 만들었던 Ollama 테스트 컨테이너를 재사용 가능한 `docker-compose.test.yml`로 정리하면서, 볼륨 이름 자동 접두사로 모델 데이터가 분리되는 문제를 발견하고 수정했습니다.
- `sample_MCP2`의 실제 플랫폼 등록 화면 스크린샷을 근거로, 로컬 테스트 환경에서 실 배포로 넘어갈 때 바꿔야 할 설정값·제외할 파일·플랫폼에서 직접 해야 할 액션을 구체적으로 정리했습니다.

**현재 가장 큰 문제**
- `ollmcp`(로컬 LLM 경유 MCP 클라이언트)로 `qwen3:4b`에서 `oreum_mcp` 툴을 호출하면 여전히 "No Response from Model" 오류가 발생하며, 근본 원인이 확정되지 않았습니다(CPU 추론 속도 + thinking mode 타임아웃으로 추정만 된 상태).
- `.env`의 `OREUM_MCP_PUBLIC_URL`/`NGROK_AUTHTOKEN`이 비어있어, 실제 플랫폼 등록에 필요한 공개 URL이 아직 없습니다.

**다음 작업 우선순위**
- [높음] `ollmcp` 툴콜 실패 원인 확정 — thinking mode 끄기, 더 큰 모델(qwen2.5:7b 등)로 비교 테스트 중 하나를 선택해 실행
- [중간] 실 배포 환경에서 공개 URL 확보 방법 결정(ngrok 가능 여부 확인 또는 대체 수단) 후 `.env` 채우고 플랫폼 등록 화면에서 실제 등록 진행
- [중간] (8/19 보고서에서 이어짐) 고도/거리/노면 3요소 기반 난이도 계산식 설계·구현
- [낮음] `docker-compose.test.yml`을 레포에 커밋해 남길지, 로컬 전용으로 둘지 결정
- [낮음] (8/18 보고서에서 이어짐) Claude Desktop 연동 여부 결정, 좌표 시각화 방식 결정

**한 문단 요약**: 오늘은 이전 세션에서 미커밋으로 남아있던 연계오름/고도 프로파일 작업과 `docker-compose.yml` 네트워크 정비를 세션 초반에 커밋한 뒤, 세션 대부분의 시간을 들여 `oreum-mcp`와 로컬 Ollama(`ollama-test`, qwen:4b/qwen3:4b) 두 컨테이너를 실제 배포와 동일한 `etri-jejuax-gateway-network` 위에 올려 상호 통신과 실데이터 조회를 검증했습니다. 그 과정에서 ad-hoc 컨테이너를 재사용 가능한 `docker-compose.test.yml`로 정리하며 볼륨 이름 접두사 버그를 잡았고, `ollmcp` + qwen 모델의 툴콜 실패를 여러 각도로 디버깅했지만 근본 원인은 아직 확정하지 못했습니다. 마지막으로 `sample_MCP2`의 플랫폼 등록 화면을 근거로 실제 배포 전환 시 필요한 설정·액션을 정리해, 다음 단계로 넘어갈 준비를 마쳤습니다.
