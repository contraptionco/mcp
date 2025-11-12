import logging
import os
from collections.abc import Sequence

from chromadb.base_types import SparseVector
from chromadb.utils.embedding_functions import (
    ChromaCloudQwenEmbeddingFunction,
    ChromaCloudSpladeEmbeddingFunction,
)
from chromadb.utils.embedding_functions.chroma_cloud_qwen_embedding_function import (
    ChromaCloudQwenEmbeddingModel,
    ChromaCloudQwenEmbeddingTarget,
)
from chromadb.utils.embedding_functions.chroma_cloud_splade_embedding_function import (
    ChromaCloudSpladeEmbeddingModel,
)

from src.config import settings

logger = logging.getLogger(__name__)

# Domain-specific embedding instructions for Qwen
CHROMA_QWEN_INSTRUCTIONS: dict[str, dict[ChromaCloudQwenEmbeddingTarget, str]] = {
    "contraption_blog": {
        ChromaCloudQwenEmbeddingTarget.DOCUMENTS: "",
        ChromaCloudQwenEmbeddingTarget.QUERY: "",
    }
}


class EmbeddingService:
    """Thin wrapper around Chroma Cloud embedding endpoints for dense and sparse vectors."""

    def __init__(self) -> None:
        self._api_key_env_var = "CHROMA_API_KEY"
        self._ensure_api_key()
        self._dense_function = self._build_dense_function()
        self._sparse_function = self._build_sparse_function()

    def _ensure_api_key(self) -> None:
        """Ensure the Chroma Cloud API key is available for the embedding functions."""
        if os.getenv(self._api_key_env_var):
            return

        if not settings.chroma_api_key:
            raise ValueError("Chroma API key must be configured to initialize embeddings")

        os.environ[self._api_key_env_var] = settings.chroma_api_key
        logger.debug("Configured Chroma Cloud API key environment variable for embeddings")

    def _build_dense_function(self) -> ChromaCloudQwenEmbeddingFunction:
        try:
            return ChromaCloudQwenEmbeddingFunction(
                model=ChromaCloudQwenEmbeddingModel.QWEN3_EMBEDDING_0p6B,
                api_key_env_var=self._api_key_env_var,
                task="contraption_blog",
                instructions=CHROMA_QWEN_INSTRUCTIONS,
            )
        except Exception as exc:  # pragma: no cover - configuration issues
            logger.error("Failed to initialize dense embedding function: %s", exc)
            raise

    def _build_sparse_function(self) -> ChromaCloudSpladeEmbeddingFunction:
        try:
            return ChromaCloudSpladeEmbeddingFunction(
                api_key_env_var=self._api_key_env_var,
                model=ChromaCloudSpladeEmbeddingModel.SPLADE_PP_EN_V1,
            )
        except Exception as exc:  # pragma: no cover - configuration issues
            logger.error("Failed to initialize sparse embedding function: %s", exc)
            raise

    @property
    def dense_function(self) -> ChromaCloudQwenEmbeddingFunction:
        return self._dense_function

    @property
    def sparse_function(self) -> ChromaCloudSpladeEmbeddingFunction:
        return self._sparse_function

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self._dense_function(texts)
        return [self._ensure_sequence(embedding) for embedding in embeddings]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_queries(self, queries: list[str]) -> list[list[float]]:
        if not queries:
            return []

        embeddings = self._dense_function.embed_query(queries)
        return [self._ensure_sequence(embedding) for embedding in embeddings]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_queries([query])[0]

    def sparse_embed_texts(self, texts: list[str]) -> list[SparseVector]:
        if not texts:
            return []

        return list(self._sparse_function(texts))

    def sparse_embed_text(self, text: str) -> SparseVector:
        return self.sparse_embed_texts([text])[0]

    def sparse_embed_query(self, query: str) -> SparseVector:
        vectors = self._sparse_function([query])
        return vectors[0] if vectors else {"indices": [], "values": []}

    @staticmethod
    def _ensure_sequence(embedding: Sequence[float]) -> list[float]:
        return [float(value) for value in embedding]
