# Parts Multi-Agent

Symmetric LAN A2A agents for querying parts inventory from Google Sheets. Each
running process is both a Google Sheets inventory agent and a router that can
delegate to peer agents after reading their AgentCards.

## Run

Start one process per LAN device. Use one shared `.env` for common settings,
then provide `AGENT_NAME` when starting each process. The sample depends on
`a2a-sdk[http-server]` because it serves A2A over Starlette.

Each agent reads one configured Google Spreadsheet. Put shared settings in
`.env`, then put each agent's own spreadsheet ID in `.env.<lowercase
AGENT_NAME>`. For example, `AGENT_NAME=A` loads `.env.a`.

The spreadsheet worksheet defaults to `inventory`. The first row must contain
headers. A minimal sheet can use this shape:

```csv
part_number,part_name,stock,location
BRK-001,Brake Pad,28,A-01
FLT-101,Oil Filter,7,A-02
```

Share each spreadsheet with the service account email as a Viewer before
starting the agents.

Shared `.env`:

```bash
LLM_BASE_URL="http://joonyy-synology:26414/v1"
LLM_MODEL="github_copilot/gpt-4.1"
PEER_AGENT_URLS="http://localhost:10001,http://localhost:10002,http://localhost:10003"
GOOGLE_SERVICE_ACCOUNT_FILE="/absolute/path/service-account.json"
GOOGLE_SHEET_WORKSHEET="inventory"
```

Set `PEER_AGENT_URLS` to the comma-separated URLs of all agents, including this
process. Each agent removes its own `BASE_URL` + `PORT` URL before discovering
and calling peers.

```bash
cd samples/python/agents/parts_multiagent

AGENT_NAME=A uv run python -m parts_multiagent
```

Agent-specific `.env.a`:

```bash
BASE_URL="http://localhost"
PORT=10001
AGENT_DESCRIPTION="Warehouse A inventory agent."
GOOGLE_SHEET_ID="<warehouse-a-spreadsheet-id>"
```

Agent-specific `.env.b`:

```bash
BASE_URL="http://localhost"
PORT=10002
AGENT_DESCRIPTION="Warehouse B inventory agent."
GOOGLE_SHEET_ID="<warehouse-b-spreadsheet-id>"
```

Agent-specific `.env.c`:

```bash
BASE_URL="http://localhost"
PORT=10003
AGENT_DESCRIPTION="Warehouse C inventory agent."
GOOGLE_SHEET_ID="<warehouse-c-spreadsheet-id>"
```

For local testing, use different ports:

```bash
AGENT_NAME=A uv run python -m parts_multiagent

AGENT_NAME=B uv run python -m parts_multiagent

AGENT_NAME=C uv run python -m parts_multiagent
```

Send a test request:

```bash
uv run python test_client.py --url http://localhost:10001 "FLT-101 재고 알려줘"
```

Routing behavior:

- If the request names a specific peer agent or warehouse, the receiving agent
  delegates only to that target agent.
- If the request does not name a target agent, the receiving agent queries its
  own configured Google Sheet and all discovered peer agents in parallel, then
  returns one response section per agent.
- If some peer AgentCards or peer requests fail, available results are still
  returned with the failure details included in the response.

## Configuration

- `AGENT_NAME`: required runtime value. AgentCard name. Its lowercase value is
  used for the agent-specific env file.
- `AGENT_DESCRIPTION`: public AgentCard description.
- `GOOGLE_SERVICE_ACCOUNT_FILE`: required path to a service account JSON file.
- `GOOGLE_SHEET_ID`: required spreadsheet ID for this agent.
- `GOOGLE_SHEET_WORKSHEET`: worksheet name, default `inventory`.
- `LLM_BASE_URL`: OpenAI-compatible API base URL.
- `LLM_MODEL`: model name, default `github_copilot/gpt-4.1`.
- `PEER_AGENT_URLS`: comma-separated A2A base URLs for all agents, including
  this process. The current agent's own URL is removed before peer requests.
- `BASE_URL`: A2A agent base URL without a port, such as `http://localhost`.
  Combined with `PORT` for the public AgentCard URL.
- `PORT`: server port, default `10001`.

## Google Sheets Behavior

The agent reads all values from the configured worksheet and treats the first
row as headers. It detects likely part name columns from names such as `part`,
`item`, `sku`, `품목`, `부품`, and likely quantity columns from names such as
`stock`, `qty`, `inventory`, `재고`, `수량`. Query results are capped to 20 rows
before the answer is summarized by the local LLM.
