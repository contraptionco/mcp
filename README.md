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

Create or edit `~/.cursor/mcp.json`:

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
- Automatic Indexing: Syncs with blog API on startup and via webhooks
- Full Content Access: Uses Ghost Admin API to index all published content including members-only posts
- Fast Performance: Powered by FastAPI and Chroma Cloud
- Real-time Updates: Webhook support for instant post updates
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

## MCP Tools

- `fetch(url, method="GET", headers=None, body=None)`: Fetch a single blog post via the MCP fetch contract
- `list_posts(sort_by, page, limit)`: List posts with pagination
- `search(query, limit)`: Semantic search across posts

## API Endpoints

- `GET /`: Server info (redirects to GitHub repo for non-MCP requests)
- `GET /health`: Health check
- `POST /webhook/ghost/{secret}`: Secure webhook endpoint for Ghost updates
- `/mcp/*`: MCP protocol endpoints

### Webhook Security

The webhook endpoint requires a secret token in the URL path for security. Configure it in Ghost Admin:

1. Go to Settings → Integrations → Webhooks
2. Set URL to: `https://your-domain.com/webhook/ghost/{your-webhook-secret}`
3. Replace `{your-webhook-secret}` with the value from your `.env` file
4. Select events: Post published, Post updated, Post deleted

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
