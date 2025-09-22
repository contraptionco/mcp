from datetime import datetime
from unittest.mock import Mock

from src.indexer import PostIndexer
from src.models import GhostPost, PostChunk


class TestPostChunking:
    def setup_method(self):
        self.ghost_client = Mock()
        self.chroma_service = Mock()
        self.indexer = PostIndexer(self.ghost_client, self.chroma_service)

    def test_clean_html(self):
        html = """
        <html>
            <script>alert('test')</script>
            <style>body { color: red; }</style>
            <p>This is a test paragraph.</p>
            <p>Another paragraph here.</p>
        </html>
        """

        cleaned = self.indexer._clean_html(html)

        assert "alert" not in cleaned
        assert "color: red" not in cleaned
        assert "This is a test paragraph" in cleaned
        assert "Another paragraph here" in cleaned

    def test_chunk_by_paragraphs(self):
        text = """
        This is the first paragraph with some content.

        This is the second paragraph with more content.

        This is the third paragraph with even more content.
        """

        chunks = self.indexer._chunk_by_paragraphs(text)

        assert len(chunks) > 0
        assert all(chunk.strip() for chunk in chunks)

    def test_create_chunks_from_post(self):
        post = GhostPost(
            id="test-id",
            slug="test-post",
            title="Test Post",
            html="<p>First paragraph.</p><p>Second paragraph.</p>",
            plaintext="First paragraph. Second paragraph.",
            url="https://example.com/test-post",
            published_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[{"name": "test"}],
            authors=[{"name": "Author"}],
        )

        chunks = self.indexer._create_chunks(post)

        assert len(chunks) > 0
        assert all(isinstance(chunk, PostChunk) for chunk in chunks)
        assert chunks[0].post_slug == "test-post"
        assert chunks[0].post_title == "Test Post"
        assert chunks[0].tags == ["test"]
        assert chunks[0].authors == ["Author"]

    def test_create_chunks_handles_long_content(self):
        long_text = " ".join(["word"] * 2000)

        post = GhostPost(
            id="test-id",
            slug="test-post",
            title="Test Post",
            html=f"<p>{long_text}</p>",
            plaintext=long_text,
            url="https://example.com/test-post",
        )

        chunks = self.indexer._create_chunks(post)

        assert len(chunks) > 1
        for chunk in chunks:
            words = chunk.chunk_text.split()
            assert len(words) <= self.indexer.chunk_size + self.indexer.chunk_overlap
