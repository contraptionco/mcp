import logging
from typing import Any

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


@mcp.tool()
async def get_post(slug: str) -> dict[str, Any]:
    """
    Get a blog post by its slug.

    Args:
        slug: The slug of the post to retrieve

    Returns:
        The post content and metadata
    """
    chroma_service = await get_chroma_service()
    post_summary, markdown = await chroma_service.get_post_markdown(slug)

    if not post_summary or markdown is None:
        return {"error": f"Post with slug '{slug}' not found"}

    return {
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
