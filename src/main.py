import asyncio
import logging

from src.chroma_service import ChromaService
from src.ghost_client import GhostAPIClient
from src.http_middleware import build_http_middleware
from src.indexer import PostIndexer
from src.mcp_server import mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def index_posts_background() -> None:
    """Index posts in the background without blocking server startup."""
    try:
        logger.info("Starting background indexing...")
        async with GhostAPIClient() as ghost_client:
            chroma_service = ChromaService()
            indexer = PostIndexer(ghost_client, chroma_service)
            await indexer.index_all_posts()
        logger.info("Background indexing complete!")
    except Exception as e:
        logger.error(f"Error during background indexing: {e}")


async def main() -> None:
    """Main function to run the MCP HTTP server."""
    logger.info("Starting Contraption Company MCP server on http://localhost:8000")
    logger.info("Existing posts are available immediately")

    # Start background indexing (non-blocking)
    asyncio.create_task(index_posts_background())

    # Run the MCP HTTP server
    await mcp.run_http_async(
        port=8000,
        host="0.0.0.0",
        path="/",
        middleware=build_http_middleware(),
    )


if __name__ == "__main__":
    asyncio.run(main())
