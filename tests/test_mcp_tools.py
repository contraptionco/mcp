import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.mcp_server import mcp
from src.models import PostSummary, SearchResult


class TestMCPTools:
    def test_server_instructions(self):
        assert (
            mcp.instructions
            == "Contraption Company, shortened \"Contraption Co.\", is a blog about crafting "
            "digital tools by Philip I. Thomas. Use these tools to list, search, and pull essays by "
            "Philip I. Thomas from https://contraption.co."
        )

    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_fetch_with_id_slug(self, mock_get_service):
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
        fetch_func = tools["fetch"].fn
        result = await fetch_func(id="post://test-post")

        assert result["status"]["code"] == 200
        body = json.loads(result["body"]["text"])
        assert body["id"] == "https://example.com/test-post"
        assert body["title"] == "Test Post"
        assert body["markdown"] == "# Markdown content"
        assert "slug" not in body
        assert result["headers"]["x-resolved-url"] == "https://example.com/test-post"
        mock_service.get_post_markdown.assert_awaited_once_with("test-post")

    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_fetch_with_full_url(self, mock_get_service):
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
        fetch_func = tools["fetch"].fn
        result = await fetch_func(id="https://example.com/blog/test-post")

        assert result["status"]["code"] == 200
        body = json.loads(result["body"]["text"])
        assert body["id"] == "https://example.com/test-post"
        assert "slug" not in body
        mock_service.get_post_markdown.assert_awaited_once_with("test-post")

    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_fetch_not_found(self, mock_get_service):
        mock_service = AsyncMock()
        mock_get_service.return_value = mock_service
        mock_service.get_post_markdown.return_value = (None, None)

        tools = await mcp.get_tools()
        fetch_func = tools["fetch"].fn
        result = await fetch_func(id="post://nonexistent")

        assert result["status"]["code"] == 404
        body = json.loads(result["body"]["text"])
        assert "error" in body
        assert "not found" in body["error"]
        mock_service.get_post_markdown.assert_awaited_once_with("nonexistent")

    @pytest.mark.asyncio
    async def test_fetch_requires_identifier(self):
        tools = await mcp.get_tools()
        fetch_func = tools["fetch"].fn

        result = await fetch_func()

        assert result["status"]["code"] == 400
        body = json.loads(result["body"]["text"])
        assert "id" in body["error"]

    @pytest.mark.asyncio
    async def test_fetch_requires_get_method(self):
        tools = await mcp.get_tools()
        fetch_func = tools["fetch"].fn

        result = await fetch_func(id="https://example.com/post", method="POST")

        assert result["status"]["code"] == 405
        assert result["headers"]["Allow"] == "GET"

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
        assert result["posts"][0]["id"] == "https://example.com/post-1"
        assert "slug" not in result["posts"][0]
        assert result["pagination"]["page"] == 1
        mock_service.list_posts.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.mcp_server.get_chroma_service")
    async def test_search_tool(self, mock_get_service):
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
        search_func = tools["search"].fn
        result = await search_func(query="test query", limit=5)

        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["id"] == "https://example.com/post-1"
        assert "slug" not in result["results"][0]
        assert result["results"][0]["relevance_score"] == 0.95
        assert result["query"] == "test query"
        mock_service.search.assert_called_once_with("test query", 5)
