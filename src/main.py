import asyncio
import logging

from src.chroma_service import ChromaService
from src.config import settings
from src.ghost_client import GhostAPIClient
from src.http_middleware import build_http_middleware
from src.indexer import PostIndexer
from src.mcp_server import mcp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def index_posts_background(poll_interval_seconds: int | None = None) -> None:
    """Continuously index posts and pages in the background at a fixed polling interval."""
    interval = poll_interval_seconds or settings.poll_interval_seconds
    chroma_service = ChromaService()

    try:
        while True:
            try:
                logger.info("Starting background indexing cycle...")
                async with GhostAPIClient() as ghost_client:
                    indexer = PostIndexer(ghost_client, chroma_service)
                    await indexer.index_all_posts()
                logger.info("Background indexing cycle complete; next poll in %s seconds", interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Error during background indexing cycle: %s", exc)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
    except asyncio.CancelledError:
        logger.info("Background indexing task cancelled")
        raise


async def main() -> None:
    """Main function to run the MCP HTTP server."""
    logger.info("Starting Contraption Company MCP server on http://localhost:8000")
    logger.info("Existing posts and pages are available immediately")

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
