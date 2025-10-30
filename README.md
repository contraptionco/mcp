# Contraption Company MCP

An MCP (Model Context Protocol) server for [Contraption Company](https://contraption.co) essay, built on [Chroma Cloud](https://trychroma.com).

## How to Install

Contraption Company MCP is available as a hosted MCP server with no authentication.

| Field      | Value                        |
| ---------- | ---------------------------- |
| Server URL | `https://mcp.contraption.co`  |

### How to configure in common clients

<details>
<summary><b>Cursor</b></summary>

Use the deep link to install directly in Cursor: [Install Contraption Company MCP](cursor://anysphere.cursor-deeplink/mcp/install?name=contraption-company&config=eyJ1cmwiOiJodHRwczovL21jcC5jb250cmFwdGlvbi5jbyJ9).

Or, create or edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "contraption-company": {
      "url": "https://mcp.contraption.co"
    }
  }
}
```

</details>

<details>
<summary><b>ChatGPT</b></summary>

1. Open **Settings → Connectors**.
2. Click **Create new connector**.
3. Set **MCP Server URL** to `https://mcp.contraption.co`.
4. Leave authentication blank and save.

</details>

<details>
<summary><b>VS Code (Copilot Chat MCP)</b></summary>

Create or edit `.vscode/mcp.json`:

```json
{
  "servers": {
    "contraption-company": {
      "type": "http",
      "url": "https://mcp.contraption.co"
    }
  }
}
```

</details>

<details>
<summary><b>Codex</b></summary>

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.contraption-company]
command = "npx"
args = ["mcp-remote", "--transport", "http", "https://mcp.contraption.co"]
```

</details>

<details>
<summary><b>Claude Code</b></summary>

Run in your terminal:

```bash
claude mcp add --transport http contraption-company https://mcp.contraption.co
```

</details>

<details>
<summary><b>OpenAI SDK (Python)</b></summary>

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5",
    input="List the newest Contraption Company blog posts.",
    tools=[
        {
            "type": "mcp",
            "server_label": "contraption-company",
            "server_url": "https://mcp.contraption.co",
            "require_approval": "never",
        }
    ],
)
print(response)
```

</details>

## Features

- Semantic Search: Uses Qwen3-Embedding-0.6B model for efficient semantic search
- Automatic Indexing: Syncs with the blog API on startup and via scheduled polling
- Full Content Access: Uses Ghost Admin API to index all published content including members-only posts
- Fast Performance: Powered by FastAPI and Chroma Cloud
- Background Updates: Polls Ghost every few minutes for new, updated, or deleted posts
- Docker Ready: Includes Dockerfile for easy deployment
- Well Tested: Comprehensive test suite with pytest

## Run Locally

1. Clone and install:

```bash
git clone <repository>
cd mcp
uv sync --all-extras
```

2. Configure environment:

```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Run the server:

```bash
./run.sh
# Or: uv run python -m src.main
```

### Docker

```bash
# Build
docker build -t contraption-mcp .

# Run
docker run -p 8000:8000 --env-file .env contraption-mcp

# Or use docker-compose
docker-compose up
```

## Configuration

Running locally requires credentials for external services:

- **Ghost Admin API Key**: From your Ghost Admin panel (Settings > Integrations)
- **Chroma Cloud Credentials**: Tenant ID, Database, and API key from Chroma Cloud
- **Ghost Blog URL**: Your Ghost blog's URL
- **Polling Interval (optional)**: Set `POLL_INTERVAL_SECONDS` to override the default 5 minute sync cadence

## MCP Tools

- `fetch(id=None, url=None, method="GET", headers=None, body=None)`: Fetch a single blog post via the MCP fetch contract using the canonical post URL as the identifier. Provide either the `id` returned by `list_posts`/`search` (which is the canonical URL) or a `url`; Ghost slugs and shorthand schemes are also accepted but responses always resolve to full URLs.
- `list_posts(sort_by, page, limit)`: List posts with pagination, returning canonical URLs as identifiers
- `search(query, limit)`: Semantic search across posts that emits canonical URLs for result IDs

## API Endpoints

- `GET /`: Server info (redirects to GitHub repo for non-MCP requests)
- `GET /health`: Health check
- `/mcp/*`: MCP protocol endpoints

### Background Sync

The server polls the Ghost Admin API every 5 minutes to detect new, updated, or deleted posts. Adjust the cadence by setting the `POLL_INTERVAL_SECONDS` environment variable.

## Development

```bash
# Install dev dependencies
make dev

# Run tests
make test

# Lint and format
make format lint

# Run all checks
make check
```

## License

MIT
