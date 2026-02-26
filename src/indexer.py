import hashlib
import logging
from typing import Any

from bs4 import BeautifulSoup
from markdownify import markdownify

from src.chroma_service import ChromaService
from src.config import settings
from src.ghost_client import GhostAPIClient
from src.models import ContentType, GhostPost, PostChunk

logger = logging.getLogger(__name__)


class PostIndexer:
    def __init__(self, ghost_client: GhostAPIClient, chroma_service: ChromaService) -> None:
        self.ghost_client = ghost_client
        self.chroma_service = chroma_service

    def _clean_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for script in soup(["script", "style"]):
            script.decompose()

        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return str(text)

    def _extract_markdown(self, post: GhostPost) -> str | None:
        if post.html:
            markdown_text = str(markdownify(post.html))
            logger.debug("Converted HTML to markdown, length: %s", len(markdown_text))
            return markdown_text
        if post.plaintext:
            logger.debug("Using plaintext, length: %s", len(post.plaintext))
            return post.plaintext
        return None

    def _chunk_by_lines(self, text: str) -> list[str]:
        lines: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
        return lines

    def _build_chunks_and_hash(
        self, post: GhostPost, content_type: ContentType
    ) -> tuple[list[PostChunk], str | None]:
        logger.debug("Creating chunks for %s: %s", content_type, post.slug)
        logger.debug(
            "Content has html: %s, plaintext: %s",
            bool(post.html),
            bool(post.plaintext),
        )

        markdown_text = self._extract_markdown(post)
        if not markdown_text:
            logger.warning("%s %s has no content to index", content_type, post.slug)
            return [], None

        lines = self._chunk_by_lines(markdown_text)
        if not lines:
            logger.warning("%s %s has no content to index", content_type, post.slug)
            return [], None

        title_prefix = (post.title or "").strip()
        if post.published_at:
            date_str = post.published_at.strftime("%Y-%m-%d")
            title_prefix = f"{title_prefix} ({date_str})" if title_prefix else date_str

        content_hash = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

        chunks = []
        public_tags = self._filter_public_tags(post.tags)
        authors = [author.get("name", "") for author in post.authors if author.get("name")]

        for i, line_text in enumerate(lines):
            document_text = f"{title_prefix}\n{line_text}" if title_prefix else line_text

            chunk = PostChunk(
                post_id=post.id,
                post_slug=post.slug,
                post_title=post.title,
                post_url=post.url or f"{settings.ghost_api_url}/{post.slug}/",
                chunk_text=document_text,
                chunk_index=i,
                total_chunks=len(lines),
                content_type=content_type,
                content_hash=content_hash,
                published_at=post.published_at,
                updated_at=post.updated_at,
                tags=public_tags,
                authors=authors,
            )
            chunks.append(chunk)

        return chunks, content_hash

    @staticmethod
    def _filter_public_tags(tags: list[dict[str, Any]]) -> list[str]:
        public_tags: list[str] = []
        for tag in tags:
            name = str(tag.get("name", "")).strip()
            if not name:
                continue
            visibility = tag.get("visibility")
            if visibility is None:
                if name.startswith("#"):
                    continue
            else:
                if str(visibility).strip().lower() != "public":
                    continue
            if name.startswith("#"):
                continue
            public_tags.append(name)
        return public_tags

    def _create_chunks(self, post: GhostPost) -> list[PostChunk]:
        chunks, _ = self._build_chunks_and_hash(post, "post")
        return chunks

    async def index_post(
        self,
        post: GhostPost,
        *,
        content_type: ContentType = "post",
        chunks: list[PostChunk] | None = None,
    ) -> None:
        logger.info("Indexing %s: %s", content_type, post.slug)
        logger.debug(
            "Content details - Title: %s, Has HTML: %s, Has plaintext: %s",
            post.title,
            bool(post.html),
            bool(post.plaintext),
        )

        await self.chroma_service.delete_post(post.slug, content_type=content_type)

        if chunks is None:
            chunks, _ = self._build_chunks_and_hash(post, content_type)

        if chunks:
            await self.chroma_service.upsert_chunks(chunks)
            logger.info("Indexed %s chunks for %s: %s", len(chunks), content_type, post.slug)
        else:
            logger.warning("No chunks created for %s: %s", content_type, post.slug)

    async def index_all_posts(self) -> None:
        logger.info("Starting full content indexing")

        posts = await self.ghost_client.get_all_posts()
        pages = await self.ghost_client.get_all_pages()
        content_items: list[tuple[GhostPost, ContentType]] = [(post, "post") for post in posts] + [
            (page, "page") for page in pages
        ]

        indexed_content = await self.chroma_service.get_indexed_content_index()

        new_items: list[tuple[GhostPost, ContentType, list[PostChunk]]] = []
        updated_items: list[tuple[GhostPost, ContentType, list[PostChunk]]] = []
        current_keys: set[tuple[str, ContentType]] = set()

        for content, content_type in content_items:
            logger.debug(
                "Checking %s %s: has_html=%s, has_plaintext=%s",
                content_type,
                content.slug,
                bool(content.html),
                bool(content.plaintext),
            )
            key = (content.slug, content_type)
            current_keys.add(key)

            chunks, content_hash = self._build_chunks_and_hash(content, content_type)
            if not chunks:
                if key in indexed_content:
                    logger.info("Removing empty %s from index: %s", content_type, content.slug)
                    await self.chroma_service.delete_post(content.slug, content_type=content_type)
                continue

            existing = indexed_content.get(key)
            if not existing:
                new_items.append((content, content_type, chunks))
                continue

            hash_changed = content_hash != existing.get("content_hash")
            updated_at = content.updated_at
            existing_updated_at = existing.get("updated_at")
            updated = (
                updated_at is not None
                and existing_updated_at is not None
                and updated_at > existing_updated_at
            )

            if hash_changed or updated:
                updated_items.append((content, content_type, chunks))

        logger.info(
            "Found %s new items and %s updated items",
            len(new_items),
            len(updated_items),
        )

        for content, content_type, chunks in new_items + updated_items:
            await self.index_post(content, content_type=content_type, chunks=chunks)

        for slug, indexed_content_type in indexed_content:
            if (slug, indexed_content_type) not in current_keys:
                logger.info("Removing deleted %s from index: %s", indexed_content_type, slug)
                await self.chroma_service.delete_post(slug, content_type=indexed_content_type)

        logger.info("Full content indexing completed")
