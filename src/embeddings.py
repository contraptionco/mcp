import logging
from collections.abc import Iterable
from typing import Any

import numpy as np
import torch
from chromadb.base_types import SparseVector
from scipy import sparse as sp
from sentence_transformers import SentenceTransformer
from sentence_transformers.sparse_encoder import SparseEncoder

from src.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self.model_name = settings.embedding_model
        self.model: SentenceTransformer | None = None
        self._device: str | None = None
        self.sparse_model_name = settings.sparse_embedding_model
        self.sparse_model: SparseEncoder | None = None
        self._sparse_device: str | None = None

    def _get_device(self) -> str:
        if self._device is None:
            if torch.cuda.is_available():
                self._device = "cuda"
            elif torch.backends.mps.is_available():
                self._device = "mps"
            else:
                self._device = "cpu"
            logger.info(f"Using device: {self._device}")
        return self._device

    def _load_model(self) -> None:
        if self.model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            device = self._get_device()
            self.model = SentenceTransformer(
                self.model_name,
                device=device,
                trust_remote_code=True,
            )
            logger.info("Embedding model loaded successfully")

    def _get_sparse_device(self) -> str:
        if self._sparse_device is None:
            if torch.cuda.is_available():
                self._sparse_device = "cuda"
            elif torch.backends.mps.is_available():
                self._sparse_device = "mps"
            else:
                self._sparse_device = "cpu"
            logger.info(f"Using sparse encoder device: {self._sparse_device}")
        return self._sparse_device

    def _load_sparse_model(self) -> None:
        if self.sparse_model is None:
            logger.info(f"Loading sparse embedding model: {self.sparse_model_name}")
            device = self._get_sparse_device()
            self.sparse_model = SparseEncoder(
                self.sparse_model_name,
                device=device,
                trust_remote_code=True,
            )
            logger.info("Sparse embedding model loaded successfully")

    @staticmethod
    def _sparse_row_to_vector(row: Any) -> SparseVector:
        if sp.issparse(row):
            csr_row = row.tocsr()
            indices = csr_row.indices.tolist()
            values = csr_row.data.astype(float).tolist()
            return {"indices": indices, "values": values}

        if isinstance(row, torch.Tensor):
            tensor = row.detach().cpu()
            if tensor.is_sparse:
                coalesced = tensor.coalesce()
                indices_tensor = coalesced.indices()
                # Sparse tensors store indices as 2 x nnz matrix for COO format.
                if indices_tensor.shape[0] == 1:
                    indices = indices_tensor[0].tolist()
                else:
                    indices = indices_tensor[1].tolist()
                values = coalesced.values().tolist()
                return {
                    "indices": [int(idx) for idx in indices],
                    "values": [float(val) for val in values],
                }
            arr = tensor.numpy().ravel()
        else:
            arr = np.asarray(row).ravel()

        if arr.size == 0:
            return {"indices": [], "values": []}

        non_zero_indices = np.nonzero(arr)[0].tolist()
        non_zero_values = [float(arr[idx]) for idx in non_zero_indices]
        return {"indices": non_zero_indices, "values": non_zero_values}

    @classmethod
    def _extract_sparse_vectors(cls, encoded: Any) -> list[SparseVector]:
        if encoded is None:
            return []

        if sp.issparse(encoded):
            rows: Iterable[Any] = (encoded.getrow(i) for i in range(encoded.shape[0]))
        elif isinstance(encoded, np.ndarray):
            rows = [encoded] if encoded.ndim == 1 else (encoded[i] for i in range(encoded.shape[0]))
        elif isinstance(encoded, list | tuple):
            rows = encoded
        else:
            rows = [encoded]

        vectors: list[SparseVector] = []
        for row in rows:
            vectors.append(cls._sparse_row_to_vector(row))
        return vectors

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        self._load_model()
        assert self.model is not None

        embeddings = self.model.encode(
            texts,
            batch_size=8,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

        return embeddings.tolist()  # type: ignore[no-any-return]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def sparse_embed_texts(self, texts: list[str]) -> list[SparseVector]:
        if not texts:
            return []

        self._load_sparse_model()
        assert self.sparse_model is not None

        encoded = self.sparse_model.encode(
            texts,
            batch_size=8,
            show_progress_bar=False,
            convert_to_sparse_tensor=False,
        )
        return self._extract_sparse_vectors(encoded)

    def sparse_embed_text(self, text: str) -> SparseVector:
        return self.sparse_embed_texts([text])[0]

    def sparse_embed_query(self, text: str) -> SparseVector:
        self._load_sparse_model()
        assert self.sparse_model is not None

        encoded = self.sparse_model.encode_query(
            [text],
            batch_size=8,
            show_progress_bar=False,
            convert_to_sparse_tensor=False,
        )
        vectors = self._extract_sparse_vectors(encoded)
        return vectors[0] if vectors else {"indices": [], "values": []}
