from datetime import datetime

from scipy.sparse import csr_matrix

from src.chroma_service import ChromaService
from src.embeddings import EmbeddingService


def test_extract_sparse_vectors_from_csr_matrix() -> None:
    matrix = csr_matrix([[0.0, 1.5, 0.0, 0.25], [0.0, 0.0, 0.0, 0.0]])

    vectors = EmbeddingService._extract_sparse_vectors(matrix)

    assert vectors[0] == {"indices": [1, 3], "values": [1.5, 0.25]}
    assert vectors[1] == {"indices": [], "values": []}


def test_build_search_result_ignores_sparse_vector_metadata() -> None:
    published = datetime.now().isoformat()
    metadata = {
        "post_slug": "hybrid-search",
        "post_title": "Hybrid Search",
        "post_url": "https://example.com/hybrid",
        "tags": "search,hybrid",
        "published_at": published,
        "sparse_vector": {"indices": [10], "values": [0.42]},
    }

    result = ChromaService._build_search_result_from_metadata(
        metadata=metadata,
        excerpt="Example excerpt",
        score=0.8,
    )

    assert result.post_slug == "hybrid-search"
    assert result.tags == ["search", "hybrid"]
    assert result.relevance_score == 0.8
