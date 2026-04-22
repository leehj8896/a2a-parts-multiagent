# Parts Multi-Agent

Symmetric LAN A2A agents for querying parts inventory from local CSV files.
Each running process is both a local CSV inventory agent and a router that can
delegate to peer agents after reading their AgentCards.

## Run

Start one process per LAN device. Use one shared `.env` for common settings,
then provide `AGENT_NAME` when starting each process. The sample depends on
`a2a-sdk[http-server]` because it serves A2A over Starlette.

The agent reads CSV files from `./data/<lowercase AGENT_NAME>`. For example,
`AGENT_NAME=A` reads `./data/a/*.csv`.

When `AGENT_NAME` is provided, the agent also loads an agent-specific env file
named `.env.<lowercase AGENT_NAME>` if it exists. For example,
`AGENT_NAME=A` loads `.env.a`, and `AGENT_NAME=B` loads `.env.b`. Values passed
directly in the run command take precedence over values from these files.

Shared `.env`:

```bash
LLM_BASE_URL="http://joonyy-synology:26414/v1"
LLM_MODEL="github_copilot/gpt-4.1"
PEER_AGENT_URLS="http://localhost:10001,http://localhost:10002,http://localhost:10003"
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
```

Agent-specific `.env.b`:

```bash
BASE_URL="http://localhost"
PORT=10002
AGENT_DESCRIPTION="Warehouse B inventory agent."
```

Agent-specific `.env.c`:

```bash
BASE_URL="http://localhost"
PORT=10003
AGENT_DESCRIPTION="Warehouse C inventory agent."
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
  own local CSV inventory and all discovered peer agents in parallel, then
  returns one response section per agent.
- If some peer AgentCards or peer requests fail, available results are still
  returned with the failure details included in the response.

## Configuration

- `AGENT_NAME`: required runtime value. AgentCard name. Its lowercase value is
  used for the data folder and agent-specific env file.
- `AGENT_DESCRIPTION`: public AgentCard description.
- `LLM_BASE_URL`: OpenAI-compatible API base URL.
- `LLM_MODEL`: model name, default `github_copilot/gpt-4.1`.
- `PEER_AGENT_URLS`: comma-separated A2A base URLs for all agents, including
  this process. The current agent's own URL is removed before peer requests.
- `BASE_URL`: A2A agent base URL without a port, such as `http://localhost`.
  Combined with `PORT` for the public AgentCard URL.
- `PORT`: server port, default `10001`.

## CSV behavior

The agent reads only `*.csv` files directly under
`./data/<lowercase AGENT_NAME>`. It detects likely part name columns from names
such as `part`, `item`, `sku`, `품목`, `부품`, and likely quantity columns from
names such as `stock`, `qty`, `inventory`, `재고`, `수량`. Query results are
capped to 20 rows per file before the answer is summarized by the local LLM.
