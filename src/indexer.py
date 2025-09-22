import logging
import re
from typing import Any

from bs4 import BeautifulSoup
from markdownify import markdownify

from src.chroma_service import ChromaService
from src.config import settings
from src.ghost_client import GhostAPIClient
from src.models import GhostPost, PostChunk

logger = logging.getLogger(__name__)


class PostIndexer:
    def __init__(self, ghost_client: GhostAPIClient, chroma_service: ChromaService) -> None:
        self.ghost_client = ghost_client
        self.chroma_service = chroma_service
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap

    def _clean_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for script in soup(["script", "style"]):
            script.decompose()

        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return str(text)

    def _chunk_by_paragraphs(self, text: str) -> list[str]:
        paragraphs = re.split(r"\n\n+", text.strip())
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks = []
        current_chunk: list[str] = []
        current_word_count = 0

        for paragraph in paragraphs:
            paragraph_words = paragraph.split()
            paragraph_word_count = len(paragraph_words)

            if paragraph_word_count > self.chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_word_count = 0

                words = paragraph.split()
                for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
                    chunk_words = words[i : i + self.chunk_size]
                    chunks.append(" ".join(chunk_words))
            elif current_word_count + paragraph_word_count > self.chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = [paragraph]
                current_word_count = paragraph_word_count
            else:
                current_chunk.append(paragraph)
                current_word_count += paragraph_word_count

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _create_chunks(self, post: GhostPost) -> list[PostChunk]:
        logger.debug(f"Creating chunks for post: {post.slug}")
        logger.debug(
            f"Post has html: {bool(post.html)}, length: {len(post.html) if post.html else 0}"
        )
        logger.debug(
            f"Post has plaintext: {bool(post.plaintext)}, length: {len(post.plaintext) if post.plaintext else 0}"
        )

        # Convert HTML to markdown for better formatting
        if post.html:
            markdown_text = markdownify(post.html)
            logger.debug(f"Converted HTML to markdown, length: {len(markdown_text)}")
        elif post.plaintext:
            markdown_text = post.plaintext
            logger.debug(f"Using plaintext, length: {len(post.plaintext)}")
        else:
            logger.warning(f"Post {post.slug} has no content to index")
            return []

        text_chunks = self._chunk_by_paragraphs(markdown_text)

        if not text_chunks:
            text_chunks = [markdown_text[: self.chunk_size * 5]]

        chunks = []
        for i, chunk_text in enumerate(text_chunks):
            if not chunk_text.strip():
                continue

            chunk = PostChunk(
                post_id=post.id,
                post_slug=post.slug,
                post_title=post.title,
                post_url=post.url or f"{settings.ghost_api_url}/{post.slug}/",
                chunk_text=chunk_text,
                chunk_index=i,
                total_chunks=len(text_chunks),
                published_at=post.published_at,
                updated_at=post.updated_at,
                tags=[tag.get("name", "") for tag in post.tags if tag.get("name")],
                authors=[author.get("name", "") for author in post.authors if author.get("name")],
            )
            chunks.append(chunk)

        return chunks

    async def index_post(self, post: GhostPost) -> None:
        logger.info(f"Indexing post: {post.slug}")
        logger.debug(
            f"Post details - Title: {post.title}, Has HTML: {bool(post.html)}, Has plaintext: {bool(post.plaintext)}"
        )

        await self.chroma_service.delete_post(post.slug)

        chunks = self._create_chunks(post)
        if chunks:
            await self.chroma_service.upsert_chunks(chunks)
            logger.info(f"Indexed {len(chunks)} chunks for post: {post.slug}")
        else:
            logger.warning(f"No chunks created for post: {post.slug}")

    async def index_all_posts(self) -> None:
        logger.info("Starting full post indexing")

        posts = await self.ghost_client.get_all_posts()
        indexed_slugs = await self.chroma_service.get_indexed_post_slugs()

        new_posts = []
        updated_posts = []

        for post in posts:
            logger.debug(
                f"Checking post {post.slug}: has_html={bool(post.html)}, has_plaintext={bool(post.plaintext)}"
            )
            if post.slug not in indexed_slugs:
                new_posts.append(post)
            else:
                existing_post = await self.chroma_service.get_post_by_slug(post.slug)
                if (
                    existing_post
                    and post.updated_at
                    and existing_post.updated_at
                    and post.updated_at > existing_post.updated_at
                ):
                    updated_posts.append(post)

        logger.info(f"Found {len(new_posts)} new posts and {len(updated_posts)} updated posts")

        for post in new_posts + updated_posts:
            await self.index_post(post)

        for slug in indexed_slugs:
            if slug not in {p.slug for p in posts}:
                logger.info(f"Removing deleted post from index: {slug}")
                await self.chroma_service.delete_post(slug)

        logger.info("Full post indexing completed")

    async def index_post_from_webhook(self, post_data: dict[str, Any]) -> None:
        post = GhostPost(**post_data)
        await self.index_post(post)
