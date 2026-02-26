from datetime import datetime

from src.chroma_service import ChromaService


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


def test_build_search_result_filters_internal_tags() -> None:
    published = datetime.now().isoformat()
    metadata = {
        "post_slug": "public-tags",
        "post_title": "Public Tags",
        "post_url": "https://example.com/public-tags",
        "tags": "alpha,#internal,beta",
        "published_at": published,
    }

    result = ChromaService._build_search_result_from_metadata(
        metadata=metadata,
        excerpt="Example excerpt",
        score=0.7,
    )

    assert result.tags == ["alpha", "beta"]


def test_build_query_metadata_includes_params() -> None:
    metadata = ChromaService._build_query_metadata(
        query="hello world",
        timestamp=1700000000,
        top_match={"post_id": "post-1", "post_url": "https://example.com/post-1"},
        params={"limit": 5, "distinct_results": True},
    )

    assert "query" not in metadata  # query is stored as the document, not metadata
    assert metadata["query_ts"] == 1700000000
    assert metadata["query_time"] == "2023-11-14T22:13:20+00:00"
    assert metadata["limit"] == 5
    assert metadata["distinct_results"] is True
    assert "top_match_id" not in metadata
    assert metadata["top_match_url"] == "https://example.com/post-1"
