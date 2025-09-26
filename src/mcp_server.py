import json
import logging
from typing import Any
from urllib.parse import urljoin, urlparse

from fastmcp import FastMCP

from src.chroma_service import ChromaService
from src.config import settings
from src.models import PostSummary

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Contraption Company MCP",
    instructions=(
        "Contraption Company, shortened \"Contraption Co.\", is a blog about crafting digital "
        "tools by Philip I. Thomas. Use these tools to list, search, and pull essays by Philip I. "
        "Thomas from https://contraption.co."
    ),
)

_chroma_service: ChromaService | None = None


async def get_chroma_service() -> ChromaService:
    global _chroma_service
    if _chroma_service is None:
        _chroma_service = ChromaService()
    return _chroma_service


def _extract_slug_from_url(url: str) -> str | None:
    """Extract a post slug from user input.

    The MCP contract references HTTP-style requests, so we support a few shapes:

    - ``post://{slug}`` or ``ghost://{slug}`` custom schemes
    - Fully qualified Ghost URLs (``https://example.com/posts/{slug}``)
    - Bare slugs with no scheme
    """

    parsed = urlparse(url)

    if parsed.scheme in {"post", "ghost", ""}:
        if parsed.path and parsed.path.strip("/"):
            return parsed.path.strip("/")
        if parsed.netloc:
            return parsed.netloc
        return parsed.path or None

    if parsed.scheme in {"http", "https"}:
        path = parsed.path.strip("/")
        if not path:
            return None
        return path.split("/")[-1]

    return None


def _canonical_post_url(post_summary: PostSummary, fallback_url: str | None = None) -> str | None:
    """Resolve a canonical, HTTP(S) URL for a post."""

    if post_summary.url:
        return post_summary.url

    if fallback_url:
        parsed_fallback = urlparse(fallback_url)
        if parsed_fallback.scheme in {"http", "https"} and parsed_fallback.netloc:
            return fallback_url

    base_url = settings.ghost_api_url
    if base_url and post_summary.slug:
        parsed_base = urlparse(base_url)
        if parsed_base.scheme and parsed_base.netloc:
            origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
            return urljoin(origin.rstrip("/") + "/", post_summary.slug.strip("/"))

    return None


@mcp.tool(name="fetch")
async def fetch(
    id: str = "",
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """Fetch a blog post using the MCP HTTP-style contract.

    Accepts an ``id`` that can be a slug, canonical URL, or a ``post://`` style identifier.
    """

    del headers, body

    method = method.upper()
    if method != "GET":
        return {
            "status": {"code": 405, "text": "Method Not Allowed"},
            "headers": {"Allow": "GET"},
            "body": {"kind": "text", "text": ""},
        }

    identifier = id

    if not identifier:
        return {
            "status": {"code": 400, "text": "Bad Request"},
            "headers": {"Content-Type": "application/json"},
            "body": {
                "kind": "text",
                "text": json.dumps({"error": "An 'id' must be provided"}),
            },
        }

    slug = _extract_slug_from_url(identifier)
    if not slug:
        return {
            "status": {"code": 400, "text": "Bad Request"},
            "headers": {"Content-Type": "application/json"},
            "body": {
                "kind": "text",
                "text": json.dumps({"error": "Unable to determine post slug from identifier"}),
            },
        }

    chroma_service = await get_chroma_service()
    post_summary, markdown = await chroma_service.get_post_markdown(slug)

    if not post_summary or markdown is None:
        return {
            "status": {"code": 404, "text": "Not Found"},
            "headers": {"Content-Type": "application/json"},
            "body": {
                "kind": "text",
                "text": json.dumps({"error": "Post not found"}),
            },
        }

    resolved_url = _canonical_post_url(post_summary, identifier)
    if not resolved_url:
        logger.warning("Unable to resolve canonical URL for post %s", post_summary.id)
        return {
            "status": {"code": 502, "text": "Bad Gateway"},
            "headers": {"Content-Type": "application/json"},
            "body": {
                "kind": "text",
                "text": json.dumps({"error": "Unable to resolve canonical URL for post"}),
            },
        }

    response_body = {
        "id": resolved_url,
        "title": post_summary.title,
        "excerpt": post_summary.excerpt,
        "url": resolved_url,
        "published_at": post_summary.published_at.isoformat()
        if post_summary.published_at
        else None,
        "updated_at": post_summary.updated_at.isoformat() if post_summary.updated_at else None,
        "tags": post_summary.tags,
        "authors": post_summary.authors,
        "markdown": markdown,
    }

    return {
        "status": {"code": 200, "text": "OK"},
        "headers": {"Content-Type": "application/json", "x-resolved-url": resolved_url},
        "body": {"kind": "text", "text": json.dumps(response_body)},
    }


@mcp.tool()
async def list_posts(
    sort_by: str = "newest",
    page: int = 1,
    limit: int = 10,
) -> dict[str, Any]:
    """
    List blog posts with pagination.

    Args:
        sort_by: Sort order - 'newest' or 'oldest' (default: 'newest')
        page: Page number (default: 1)
        limit: Number of posts per page, max 10 (default: 10)

    Returns:
        List of post summaries with metadata
    """
    if limit > settings.max_posts_per_page:
        limit = settings.max_posts_per_page

    if page < 1:
        page = 1

    offset = (page - 1) * limit

    chroma_service = await get_chroma_service()
    posts = await chroma_service.list_posts(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
    )

    serialized_posts: list[dict[str, Any]] = []
    for post in posts:
        resolved_url = _canonical_post_url(post)
        if not resolved_url:
            logger.debug("Skipping post without canonical URL: %s", post.id)
            continue

        serialized_posts.append(
            {
                "id": resolved_url,
                "title": post.title,
                "excerpt": post.excerpt,
                "url": resolved_url,
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "updated_at": post.updated_at.isoformat() if post.updated_at else None,
                "tags": post.tags,
                "authors": post.authors,
            }
        )

    return {
        "posts": serialized_posts,
        "pagination": {
            "page": page,
            "limit": limit,
            "sort_by": sort_by,
        },
    }


@mcp.tool(name="search")
async def search(
    query: str,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Search blog posts using semantic search.

    Args:
        query: Search query text
        limit: Maximum number of results to return (default: 10)

    Returns:
        List of search results with relevance scores
    """
    if limit > settings.search_top_k:
        limit = settings.search_top_k

    chroma_service = await get_chroma_service()
    results = await chroma_service.search(query, limit)

    serialized_results: list[dict[str, Any]] = []
    for result in results:
        if not result.post_url:
            logger.debug("Skipping search result without canonical URL: %s", result.post_slug)
            continue

        serialized_results.append(
            {
                "id": result.post_url,
                "title": result.post_title,
                "url": result.post_url,
                "excerpt": result.excerpt,
                "relevance_score": result.relevance_score,
                "published_at": result.published_at.isoformat() if result.published_at else None,
                "tags": result.tags,
            }
        )

    return {
        "query": query,
        "results": serialized_results,
        "count": len(serialized_results),
    }
