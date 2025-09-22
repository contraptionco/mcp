from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.mcp_server import mcp
from src.models import PostSummary, SearchResult


class TestMCPTools:
    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_get_post_found(self, mock_get_service):
        mock_service = AsyncMock()
        mock_get_service.return_value = mock_service

        test_summary = PostSummary(
            id="test-id",
            slug="test-post",
            title="Test Post",
            excerpt="Excerpt",
            url="https://example.com/test-post",
            published_at=datetime.now(),
            updated_at=datetime.now(),
            tags=["test"],
            authors=["Author"],
        )

        mock_service.get_post_markdown.return_value = (test_summary, "# Markdown content")

        tools = await mcp.get_tools()
        get_post_func = tools["get_post"].fn
        result = await get_post_func(slug="test-post")

        assert result["slug"] == "test-post"
        assert result["title"] == "Test Post"
        assert result["markdown"] == "# Markdown content"
        assert "error" not in result
        mock_service.get_post_markdown.assert_awaited_once_with("test-post")

    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_get_post_not_found(self, mock_get_service):
        mock_service = AsyncMock()
        mock_get_service.return_value = mock_service
        mock_service.get_post_markdown.return_value = (None, None)

        tools = await mcp.get_tools()
        get_post_func = tools["get_post"].fn
        result = await get_post_func(slug="nonexistent")

        assert "error" in result
        assert "not found" in result["error"]
        mock_service.get_post_markdown.assert_awaited_once_with("nonexistent")

    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_list_posts(self, mock_get_service):
        mock_service = AsyncMock()
        mock_get_service.return_value = mock_service

        test_posts = [
            PostSummary(
                id="1",
                slug="post-1",
                title="Post 1",
                excerpt="Excerpt 1",
                url="https://example.com/post-1",
                published_at=datetime.now(),
                updated_at=datetime.now(),
                tags=["tag1"],
                authors=["Author 1"],
            ),
            PostSummary(
                id="2",
                slug="post-2",
                title="Post 2",
                excerpt="Excerpt 2",
                url="https://example.com/post-2",
                published_at=datetime.now(),
                updated_at=datetime.now(),
                tags=["tag2"],
                authors=["Author 2"],
            ),
        ]

        mock_service.list_posts.return_value = test_posts

        tools = await mcp.get_tools()
        list_posts_func = tools["list_posts"].fn
        result = await list_posts_func(sort_by="newest", page=1, limit=10)

        assert "posts" in result
        assert len(result["posts"]) == 2
        assert result["posts"][0]["slug"] == "post-1"
        assert result["pagination"]["page"] == 1
        mock_service.list_posts.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_search_posts(self, mock_get_service):
        mock_service = AsyncMock()
        mock_get_service.return_value = mock_service

        test_results = [
            SearchResult(
                post_slug="post-1",
                post_title="Post 1",
                post_url="https://example.com/post-1",
                excerpt="Matching excerpt",
                relevance_score=0.95,
                published_at=datetime.now(),
                tags=["tag1"],
            ),
        ]

        mock_service.search.return_value = test_results

        tools = await mcp.get_tools()
        search_posts_func = tools["search_posts"].fn
        result = await search_posts_func(query="test query", limit=5)

        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["slug"] == "post-1"
        assert result["results"][0]["relevance_score"] == 0.95
        assert result["query"] == "test query"
        mock_service.search.assert_called_once_with("test query", 5)
