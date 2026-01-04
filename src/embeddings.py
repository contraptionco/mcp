import logging
import os
from collections.abc import Sequence
from typing import Any, cast

import voyageai
from chromadb.base_types import SparseVector
from chromadb.utils.embedding_functions import (
    ChromaCloudQwenEmbeddingFunction,
    ChromaCloudSpladeEmbeddingFunction,
)
from chromadb.utils.embedding_functions.chroma_cloud_qwen_embedding_function import (
    ChromaCloudQwenEmbeddingModel,
)
from chromadb.utils.embedding_functions.chroma_cloud_splade_embedding_function import (
    ChromaCloudSpladeEmbeddingModel,
)

from src.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Wrapper around Voyage dense embeddings and Chroma sparse embeddings."""

    def __init__(self) -> None:
        self._voyage_env_var = "VOYAGE_API_KEY"
        self._chroma_env_var = "CHROMA_API_KEY"
        self._ensure_voyage_api_key()
        self._ensure_chroma_api_key()
        self._client = cast(Any, voyageai).Client(api_key=os.getenv(self._voyage_env_var))
        self._model = "voyage-context-3"
        self._output_dimension = 2048
        self._sparse_function = self._build_sparse_function()

    def _ensure_voyage_api_key(self) -> None:
        if os.getenv(self._voyage_env_var):
            return

        if settings.voyage_api_key:
            os.environ[self._voyage_env_var] = settings.voyage_api_key
            logger.debug("Configured Voyage API key environment variable for embeddings")
            return

        raise ValueError("Voyage API key must be configured to initialize embeddings")

    def _ensure_chroma_api_key(self) -> None:
        if os.getenv(self._chroma_env_var):
            return

        if settings.chroma_api_key:
            os.environ[self._chroma_env_var] = settings.chroma_api_key
            logger.debug("Configured Chroma API key environment variable for embeddings")
            return

        raise ValueError("Chroma API key must be configured to initialize embeddings")

    def _build_sparse_function(self) -> ChromaCloudSpladeEmbeddingFunction:
        try:
            return ChromaCloudSpladeEmbeddingFunction(
                api_key_env_var=self._chroma_env_var,
                model=ChromaCloudSpladeEmbeddingModel.SPLADE_PP_EN_V1,
            )
        except Exception as exc:  # pragma: no cover - configuration issues
            logger.error("Failed to initialize sparse embedding function: %s", exc)
            raise

    @property
    def sparse_function(self) -> ChromaCloudSpladeEmbeddingFunction:
        return self._sparse_function

    def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        """Embed related chunks with contextualized embeddings."""
        if not chunks:
            return []

        response = self._client.contextualized_embed(
            inputs=[chunks],
            model=self._model,
            input_type="document",
            output_dimension=self._output_dimension,
            output_dtype="float",
        )

        if not response.results:
            raise ValueError("Voyage contextualized embedding response contained no embeddings")

        embeddings = response.results[0].embeddings
        if len(embeddings) != len(chunks):
            raise ValueError(
                "Contextualized embedding count does not match chunk count "
                f"({len(embeddings)} != {len(chunks)})"
            )

        return [self._ensure_sequence(embedding) for embedding in embeddings]

    def embed_query(self, query: str) -> list[float]:
        response = self._client.contextualized_embed(
            inputs=[[query]],
            model=self._model,
            input_type="query",
            output_dimension=self._output_dimension,
            output_dtype="float",
        )
        if not response.results:
            raise ValueError("Voyage query embedding response contained no embeddings")

        embeddings = response.results[0].embeddings
        if not embeddings:
            raise ValueError("Voyage query embedding response contained no embeddings")

        return self._ensure_sequence(embeddings[0])

    def sparse_embed_texts(self, texts: list[str]) -> list[SparseVector]:
        if not texts:
            return []

        batch_size = 16
        embeddings: list[SparseVector] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings.extend(list(self._sparse_function(batch)))
        return embeddings

    def sparse_embed_query(self, query: str) -> SparseVector:
        vectors = self._sparse_function([query])
        if not vectors:
            return SparseVector(indices=[], values=[])

        vector = vectors[0]
        if isinstance(vector, SparseVector):
            return vector

        return SparseVector(
            indices=vector.get("indices", []),
            values=vector.get("values", []),
            labels=vector.get("labels"),
        )

    @staticmethod
    def _ensure_sequence(embedding: Sequence[float]) -> list[float]:
        return [float(value) for value in embedding]


class QueryEmbeddingService:
    """Embeds query strings using Chroma Cloud Qwen embeddings."""

    def __init__(self) -> None:
        self._chroma_env_var = "CHROMA_API_KEY"
        self._ensure_chroma_api_key()
        self._dense_function = self._build_dense_function()

    def _ensure_chroma_api_key(self) -> None:
        if os.getenv(self._chroma_env_var):
            return

        if settings.chroma_api_key:
            os.environ[self._chroma_env_var] = settings.chroma_api_key
            logger.debug("Configured Chroma API key environment variable for embeddings")
            return

        raise ValueError("Chroma API key must be configured to initialize embeddings")

    def _build_dense_function(self) -> ChromaCloudQwenEmbeddingFunction:
        try:
            return ChromaCloudQwenEmbeddingFunction(
                model=ChromaCloudQwenEmbeddingModel.QWEN3_EMBEDDING_0p6B,
                task=cast(Any, ""),
                api_key_env_var=self._chroma_env_var,
            )
        except Exception as exc:  # pragma: no cover - configuration issues
            logger.error("Failed to initialize query embedding function: %s", exc)
            raise

    @property
    def dense_function(self) -> ChromaCloudQwenEmbeddingFunction:
        return self._dense_function

    def embed_query(self, query: str) -> list[float]:
        embeddings = self._dense_function.embed_query([query])
        if not embeddings:
            raise ValueError("Chroma query embedding response contained no embeddings")
        return [float(value) for value in embeddings[0]]

    def close(self) -> None:
        session = getattr(self._dense_function, "_session", None)
        if session:
            session.close()
