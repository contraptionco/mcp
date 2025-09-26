import json
import logging
from typing import Any
from urllib.parse import urlparse

from fastmcp import FastMCP

from src.chroma_service import ChromaService
from src.config import settings

logger = logging.getLogger(__name__)

mcp = FastMCP("Contraption Company MCP")

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


@mcp.tool(name="fetch")
async def fetch(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """Fetch a blog post using the MCP HTTP-style contract."""

    del headers, body

    method = method.upper()
    if method != "GET":
        return {
            "status_code": 405,
            "status_text": "Method Not Allowed",
            "headers": {"Allow": "GET"},
            "body": "",
            "url": url,
        }

    slug = _extract_slug_from_url(url)
    if not slug:
        return {
            "status_code": 400,
            "status_text": "Bad Request",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Unable to determine post slug from URL"}),
            "url": url,
        }

    chroma_service = await get_chroma_service()
    post_summary, markdown = await chroma_service.get_post_markdown(slug)

    if not post_summary or markdown is None:
        return {
            "status_code": 404,
            "status_text": "Not Found",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"Post with slug '{slug}' not found"}),
            "url": url,
        }

    response_body = {
        "id": post_summary.id,
        "slug": post_summary.slug,
        "title": post_summary.title,
        "excerpt": post_summary.excerpt,
        "url": post_summary.url,
        "published_at": post_summary.published_at.isoformat()
        if post_summary.published_at
        else None,
        "updated_at": post_summary.updated_at.isoformat() if post_summary.updated_at else None,
        "tags": post_summary.tags,
        "authors": post_summary.authors,
        "markdown": markdown,
    }

    return {
        "status_code": 200,
        "status_text": "OK",
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(response_body),
        "url": url,
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

    return {
        "posts": [
            {
                "id": post.id,
                "slug": post.slug,
                "title": post.title,
                "excerpt": post.excerpt,
                "url": post.url,
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "updated_at": post.updated_at.isoformat() if post.updated_at else None,
                "tags": post.tags,
                "authors": post.authors,
            }
            for post in posts
        ],
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

    return {
        "query": query,
        "results": [
            {
                "slug": result.post_slug,
                "title": result.post_title,
                "url": result.post_url,
                "excerpt": result.excerpt,
                "relevance_score": result.relevance_score,
                "published_at": result.published_at.isoformat() if result.published_at else None,
                "tags": result.tags,
            }
            for result in results
        ],
        "count": len(results),
    }
