# Parts Multi-Agent

Google Sheets에서 부품 재고를 조회하는 대칭형 LAN A2A 에이전트입니다. 실행
중인 각 프로세스는 Google Sheets 재고 에이전트이면서, AgentCard를 읽은 뒤
피어 에이전트에 위임할 수 있는 라우터이기도 합니다.

## Run

LAN 장치마다 프로세스 하나를 시작합니다. 공통 설정은 하나의 `.env`에 두고,
각 프로세스를 시작할 때 `AGENT_NAME`을 지정합니다. 이 샘플은 Starlette로 A2A를
서빙하므로 `a2a-sdk[http-server]`에 의존합니다.

각 에이전트는 설정된 Google Spreadsheet 하나를 읽습니다. 공통 설정은 `.env`에
두고, 각 에이전트의 spreadsheet ID는 `.env.<lowercase AGENT_NAME>`에 둡니다.
예를 들어 `AGENT_NAME=A`는 `.env.a`를 로드합니다.

스프레드시트 워크시트 기본값은 `inventory`입니다. 첫 번째 행에는 헤더가 있어야
합니다. 최소 시트는 다음 형태를 사용할 수 있습니다:

```csv
part_number,part_name,stock,location
BRK-001,Brake Pad,28,A-01
FLT-101,Oil Filter,7,A-02
```

에이전트를 시작하기 전에 각 스프레드시트를 서비스 계정 이메일에 Viewer 권한으로
공유하세요.

공통 `.env`:

```bash
LLM_BASE_URL="http://joonyy-synology:26414/v1"
LLM_MODEL="github_copilot/gpt-4.1"
PEER_AGENT_URLS="http://localhost:10001,http://localhost:10002,http://localhost:10003"
GOOGLE_SERVICE_ACCOUNT_FILE="/absolute/path/service-account.json"
GOOGLE_SHEET_WORKSHEET="inventory"
LOG_COLORS="A=cyan,B=yellow,C=magenta"
```

`PEER_AGENT_URLS`에는 현재 프로세스를 포함한 모든 에이전트 URL을 쉼표로 구분해
설정합니다. 각 에이전트는 피어를 검색하고 호출하기 전에 자신의 `BASE_URL` +
`PORT` URL을 제거합니다.

```bash
cd samples/python/agents/parts_multiagent

AGENT_NAME=A uv run python -m parts_multiagent
```

에이전트별 `.env.a`:

```bash
BASE_URL="http://localhost"
PORT=10001
AGENT_DESCRIPTION="창고 A 재고 에이전트입니다."
GOOGLE_SHEET_ID="<warehouse-a-spreadsheet-id>"
```

에이전트별 `.env.b`:

```bash
BASE_URL="http://localhost"
PORT=10002
AGENT_DESCRIPTION="창고 B 재고 에이전트입니다."
GOOGLE_SHEET_ID="<warehouse-b-spreadsheet-id>"
```

에이전트별 `.env.c`:

```bash
BASE_URL="http://localhost"
PORT=10003
AGENT_DESCRIPTION="창고 C 재고 에이전트입니다."
GOOGLE_SHEET_ID="<warehouse-c-spreadsheet-id>"
```

로컬 테스트에서는 서로 다른 포트를 사용합니다:

```bash
AGENT_NAME=A uv run python -m parts_multiagent

AGENT_NAME=B uv run python -m parts_multiagent

AGENT_NAME=C uv run python -m parts_multiagent
```

테스트 요청 보내기:

```bash
uv run python test_client.py --url http://localhost:10001 "FLT-101 재고 알려줘"
```

구조화 요청(DataPart)로 보내기:

```bash
uv run python test_client.py --url http://localhost:10001 --structured \
  '{"path": "/재고조회", "payload": {"query": "FLT-101 재고 알려줘"}}'
```

피어 agent들만 조회(구조화 요청):

```bash
uv run python test_client.py --url http://localhost:10001 --structured \
  '{"path": "/전국재고조회", "payload": {"query": "FLT-101 재고 알려줘"}}'
```

라우팅 동작:

- 참고: 기존 `/local`, `/peers` prefix는 제거되었습니다.
- 접두어 없는 요청은 수신 에이전트 자신의 Google Sheet를 조회한 뒤, 나를 제외한
  다른 피어 에이전트들을 조회하고 `내 agent 조회`와 `다른 agent 조회` 섹션으로
  분리해 반환합니다.
- 슬래시(prefix) 기반 텍스트 요청은 지원하지 않습니다. 명령은 구조화 요청(DataPart)의
  `path`/`payload`로 보내야 합니다.
- `path="/재고조회"` 구조화 요청은 수신 에이전트 자신의 Google Sheet만 조회합니다.
- `path="/전국재고조회"` 구조화 요청은 나를 제외한 다른 피어 에이전트들만 조회합니다.
- 피어 에이전트에 전달되는 요청은 `path="/재고조회"` 형태이므로 피어가
  다시 다른 에이전트로 재전파하지 않습니다.
- 일부 피어 AgentCard 또는 피어 요청이 실패해도 가능한 결과는 반환되며, 응답에
  실패 세부 정보가 포함됩니다.

## Configuration

- `AGENT_NAME`: 필수 런타임 값입니다. AgentCard 이름이며, 소문자 값은
  에이전트별 env 파일 이름에 사용됩니다.
- `AGENT_DESCRIPTION`: 공개 AgentCard 설명입니다.
- `GOOGLE_SERVICE_ACCOUNT_FILE`: 서비스 계정 JSON 파일의 필수 경로입니다.
- `GOOGLE_SHEET_ID`: 이 에이전트가 사용할 필수 spreadsheet ID입니다.
- `GOOGLE_SHEET_WORKSHEET`: 워크시트 이름이며, 기본값은 `inventory`입니다.
- `LLM_BASE_URL`: OpenAI 호환 API base URL입니다.
- `LLM_MODEL`: 모델 이름이며, 기본값은 `github_copilot/gpt-4.1`입니다.
- `PEER_AGENT_URLS`: 현재 프로세스를 포함한 모든 에이전트의 A2A base URL을
  쉼표로 구분한 값입니다. 현재 에이전트 자신의 URL은 피어 요청 전에 제거됩니다.
- `BASE_URL`: `http://localhost`처럼 포트를 제외한 A2A 에이전트 base URL입니다.
  공개 AgentCard URL을 만들 때 `PORT`와 결합됩니다.
- `PORT`: 서버 포트이며, 기본값은 `10001`입니다.
- `LOG_COLORS`: 에이전트별 로그 색상 매핑입니다. 공통 `.env`에
  `A=cyan,B=yellow,C=magenta`처럼 쉼표로 구분해 둡니다. 재고 응답 로그는
  `응답_에이전트`의 색상으로 출력됩니다. `red`, `green`, `yellow`, `blue`,
  `magenta`, `cyan`, `white`, `bright_*` 계열을 지원하며, 미지정 또는 미지원
  값은 무색으로 출력됩니다.

## Google Sheets Behavior

에이전트는 설정된 워크시트의 모든 값을 읽고 첫 번째 행을 헤더로 취급합니다.
`part`, `item`, `sku`, `품목`, `부품` 같은 이름에서 부품명 후보 열을 찾고,
`stock`, `qty`, `inventory`, `재고`, `수량` 같은 이름에서 수량 후보 열을
찾습니다. 조회 결과는 로컬 LLM이 답변을 요약하기 전에 최대 20행으로 제한됩니다.
