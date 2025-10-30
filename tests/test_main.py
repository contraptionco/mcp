import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.main import index_posts_background


@pytest.mark.asyncio
async def test_index_posts_background_runs_single_cycle() -> None:
    mock_sleep = AsyncMock(side_effect=asyncio.CancelledError())

    with (
        patch("src.main.asyncio.sleep", mock_sleep),
        patch("src.main.ChromaService") as mock_chroma_service_cls,
        patch("src.main.GhostAPIClient") as mock_ghost_client_cls,
        patch("src.main.PostIndexer") as mock_post_indexer_cls,
    ):
        mock_chroma_service = mock_chroma_service_cls.return_value

        mock_ghost_client = mock_ghost_client_cls.return_value
        mock_ghost_client.__aenter__.return_value = mock_ghost_client
        mock_ghost_client.__aexit__.return_value = None

        mock_indexer = mock_post_indexer_cls.return_value
        mock_indexer.index_all_posts = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            await index_posts_background(poll_interval_seconds=42)

        mock_chroma_service_cls.assert_called_once_with()
        mock_ghost_client_cls.assert_called_once_with()
        mock_post_indexer_cls.assert_called_once_with(mock_ghost_client, mock_chroma_service)
        mock_indexer.index_all_posts.assert_awaited_once_with()
        mock_sleep.assert_awaited_once_with(42)
