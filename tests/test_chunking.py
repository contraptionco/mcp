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

    def test_chunk_by_lines(self):
        text = "First line\n\nSecond line\n   \nThird line\n"

        lines = self.indexer._chunk_by_lines(text)

        assert lines == ["First line", "Second line", "Third line"]

    def test_chunk_by_lines_strips_whitespace(self):
        text = "  leading spaces\ntrailing spaces  \n  both  "

        lines = self.indexer._chunk_by_lines(text)

        assert lines == ["leading spaces", "trailing spaces", "both"]

    def test_chunk_by_lines_skips_empty(self):
        text = "\n\n\nonly line\n\n\n"

        lines = self.indexer._chunk_by_lines(text)

        assert lines == ["only line"]

    def test_create_chunks_from_post(self):
        published = datetime(2024, 1, 15, 12, 0, 0)
        post = GhostPost(
            id="test-id",
            slug="test-post",
            title="Test Post",
            html="<p>First paragraph.</p><p>Second paragraph.</p>",
            plaintext="First paragraph. Second paragraph.",
            url="https://example.com/test-post",
            published_at=published,
            updated_at=datetime.now(),
            tags=[{"name": "test"}],
            authors=[{"name": "Author"}],
        )

        chunks = self.indexer._create_chunks(post)

        assert len(chunks) > 0
        assert all(isinstance(chunk, PostChunk) for chunk in chunks)
        assert chunks[0].post_slug == "test-post"
        assert chunks[0].post_title == "Test Post"
        assert "Test Post" not in chunks[0].chunk_text  # title is metadata, not in document
        assert chunks[0].tags == ["test"]
        assert chunks[0].authors == ["Author"]

    def test_create_chunks_handles_long_content(self):
        lines = [f"Line number {i}" for i in range(100)]
        html = "".join(f"<p>{line}</p>" for line in lines)

        post = GhostPost(
            id="test-id",
            slug="test-post",
            title="Test Post",
            html=html,
            plaintext="\n".join(lines),
            url="https://example.com/test-post",
        )

        chunks = self.indexer._create_chunks(post)

        # Each non-empty line becomes a chunk
        assert len(chunks) >= 100
        for chunk in chunks:
            assert "Test Post" not in chunk.chunk_text
