# Contraption Company MCP

A production-ready MCP (Model Context Protocol) server for indexing and searching Contraption Company blog posts using Chroma Cloud and semantic search.

## Features

- Semantic Search: Uses Qwen3-Embedding-0.6B model for efficient semantic search
- Automatic Indexing: Syncs with blog API on startup and via webhooks
- Full Content Access: Uses Ghost Admin API to index all published content including members-only posts
- Fast Performance: Powered by FastAPI and Chroma Cloud
- Real-time Updates: Webhook support for instant post updates
- Docker Ready: Includes Dockerfile for easy deployment
- Well Tested: Comprehensive test suite with pytest

## Configuration

You'll need:
- **Ghost Admin API Key**: From your Ghost Admin panel (Settings > Integrations)
- **Chroma Cloud Credentials**: Tenant ID, Database, and API key from Chroma Cloud
- **Ghost Blog URL**: Your Ghost blog's URL

## Cursor Configuration

Add to your MCP config at `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "contraption-company-mcp": {
      "url": "http://localhost:8000/"
    }
  }
}
```

Then start the server:
```bash
uv run python -m src.main
```

The server will:
- Start immediately on http://localhost:8000
- Serve existing indexed posts right away
- Index new posts in the background
- Work with your Cursor configuration

## Quick Start

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

## Docker

```bash
# Build
docker build -t contraption-mcp .

# Run
docker run -p 8000:8000 --env-file .env contraption-mcp

# Or use docker-compose
docker-compose up
```

## MCP Tools

- `get_post(slug)`: Get a single blog post by slug
- `list_posts(sort_by, page, limit)`: List posts with pagination
- `search_posts(query, limit)`: Semantic search across posts

## API Endpoints

- `GET /`: Server info (redirects to GitHub repo for non-MCP requests)
- `GET /health`: Health check
- `POST /webhook/ghost/{secret}`: Secure webhook endpoint for Ghost updates
- `POST /reindex`: Manual reindexing
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