import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

import chromadb
from chromadb.api.types import SearchResult as ChromaSearchResponse
from chromadb.base_types import SparseVector
from chromadb.execution.expression import Key, Knn, Rank, Search, Val
from chromadb.types import Metadata

from src.config import settings
from src.embeddings import EmbeddingService
from src.models import PostChunk, PostSummary
from src.models import SearchResult as PostSearchResult

logger = logging.getLogger(__name__)


class ChromaService:
    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.client = chromadb.CloudClient(
            tenant=settings.chroma_tenant,
            database=settings.chroma_database,
            api_key=settings.chroma_api_key,
        )
        self.collection_name = settings.chroma_collection
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
            )
            logger.info(f"Connected to collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error creating/getting collection: {e}")
            raise

    async def upsert_chunks(self, chunks: list[PostChunk]) -> None:
        if not chunks:
            return

        ids: list[str] = []
        texts: list[str] = []
        metadata_records: list[dict[str, str | int | float | bool | None | SparseVector]] = []

        for chunk in chunks:
            chunk_id = f"{chunk.post_slug}_{chunk.chunk_index}"
            ids.append(chunk_id)
            texts.append(chunk.chunk_text)

            metadata_dict: dict[str, str | int | float | bool | None | SparseVector] = {
                "post_id": chunk.post_id,
                "post_slug": chunk.post_slug,
                "post_title": chunk.post_title,
                "post_url": chunk.post_url,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "tags": ",".join(chunk.tags) if chunk.tags else "",
                "authors": ",".join(chunk.authors) if chunk.authors else "",
            }

            if chunk.published_at:
                metadata_dict["published_at"] = chunk.published_at.isoformat()
            if chunk.updated_at:
                metadata_dict["updated_at"] = chunk.updated_at.isoformat()

            metadata_records.append(metadata_dict)

        embeddings: list[list[float]] = self.embedding_service.embed_texts(texts)
        embeddings_seq = cast(list[Sequence[float]], embeddings)
        sparse_embeddings = self.embedding_service.sparse_embed_texts(texts)

        if sparse_embeddings and len(sparse_embeddings) != len(metadata_records):
            logger.warning(
                "Sparse embedding count (%s) does not match metadata count (%s)",
                len(sparse_embeddings),
                len(metadata_records),
            )

        for index, metadata in enumerate(metadata_records):
            sparse_vector: SparseVector
            if index < len(sparse_embeddings):
                sparse_vector = sparse_embeddings[index]
            else:
                sparse_vector = {"indices": [], "values": []}
            metadata["sparse_vector"] = sparse_vector

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings_seq,
            documents=texts,
            metadatas=cast(list[Metadata], metadata_records),
        )

        logger.info(f"Upserted {len(chunks)} chunks to Chroma")

    async def get_post_by_slug(self, slug: str) -> PostSummary | None:
        summary, _ = await self.get_post_markdown(slug)
        return summary

    async def get_post_markdown(self, slug: str) -> tuple[PostSummary | None, str | None]:
        results = self.collection.get(
            where={"post_slug": slug},
            limit=300,
        )

        if not results["ids"]:
            return None, None

        documents = cast(list[str | None], results.get("documents", []))
        metadatas = cast(list[dict[str, Any] | None], results.get("metadatas", []))

        chunks: list[tuple[int, str, dict[str, Any]]] = []
        for document, metadata in zip(documents, metadatas):
            if metadata is None:
                continue
            index_raw = metadata.get("chunk_index", 0)
            chunk_index = int(index_raw) if index_raw is not None else 0
            chunk_text = document or ""
            chunks.append((chunk_index, chunk_text, metadata))

        if not chunks:
            return None, None

        chunks.sort(key=lambda item: item[0])

        markdown = "\n\n".join(chunk_text.strip() for _, chunk_text, _ in chunks if chunk_text)
        primary_metadata = chunks[0][2]
        excerpt_source = chunks[0][1]

        summary = PostSummary(
            id=str(primary_metadata.get("post_id", "")),
            slug=slug,
            title=str(primary_metadata.get("post_title", "")),
            excerpt=excerpt_source[:200] if excerpt_source else None,
            url=str(primary_metadata.get("post_url", "")),
            published_at=self._parse_datetime(primary_metadata.get("published_at")),
            updated_at=self._parse_datetime(primary_metadata.get("updated_at")),
            tags=self._split_comma_separated(primary_metadata.get("tags")),
            authors=self._split_comma_separated(primary_metadata.get("authors")),
        )

        return summary, markdown

    async def list_posts(
        self,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "newest",
    ) -> list[PostSummary]:
        # Chroma Cloud has a limit of 300 items per request
        all_results = self.collection.get(limit=300)

        if not all_results["ids"]:
            return []

        posts_map: dict[str, dict[str, Any]] = {}

        for i, metadata in enumerate(all_results["metadatas"] or []):
            slug = str(metadata.get("post_slug", ""))
            if slug and slug not in posts_map:
                posts_map[slug] = {
                    "id": metadata.get("post_id", ""),
                    "slug": slug,
                    "title": metadata.get("post_title", ""),
                    "url": metadata.get("post_url", ""),
                    "excerpt": (
                        all_results["documents"][i][:200] if all_results["documents"] else None
                    ),
                    "published_at": metadata.get("published_at"),
                    "updated_at": metadata.get("updated_at"),
                    "tags": str(metadata.get("tags", "")).split(",")
                    if metadata.get("tags")
                    else [],
                    "authors": str(metadata.get("authors", "")).split(",")
                    if metadata.get("authors")
                    else [],
                }

        posts = list(posts_map.values())

        if sort_by == "newest":
            posts.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        elif sort_by == "oldest":
            posts.sort(key=lambda x: x.get("published_at", ""))

        paginated_posts = posts[offset : offset + limit]

        return [
            PostSummary(
                id=p["id"],
                slug=p["slug"],
                title=p["title"],
                excerpt=p["excerpt"],
                url=p["url"],
                published_at=datetime.fromisoformat(p["published_at"])
                if p.get("published_at")
                else None,
                updated_at=datetime.fromisoformat(p["updated_at"]) if p.get("updated_at") else None,
                tags=p["tags"],
                authors=p["authors"],
            )
            for p in paginated_posts
        ]

    async def search(self, query: str, limit: int = 10) -> list[PostSearchResult]:
        dense_embedding = self.embedding_service.embed_text(query)
        sparse_embedding = self.embedding_service.sparse_embed_query(query)

        results = self._hybrid_rrf_search(
            dense_embedding=dense_embedding,
            sparse_embedding=sparse_embedding,
            limit=limit,
        )

        # Console-friendly printout for quick debugging/inspection
        try:
            print(f"\n📊 Hybrid Search Results (RRF Combined) — Query: {query!r}")
            if results:
                for i, result in enumerate(results):
                    title = result.post_title or "Unknown"
                    score = result.relevance_score or 0.0
                    excerpt = (result.excerpt or "").strip()
                    print(f"   {i + 1}. [{title}] Score: {score:.4f}")
                    if excerpt:
                        print(f"      Text: {excerpt[:100]}...")
            else:
                print("   No results")
        except Exception:  # Best-effort printing; never block search on logging issues
            pass

        return results

    def _hybrid_rrf_search(
        self,
        *,
        dense_embedding: list[float] | None,
        sparse_embedding: SparseVector | None,
        limit: int,
    ) -> list[PostSearchResult]:
        dense_weight = settings.dense_query_weight if dense_embedding else 0.0
        sparse_weight = settings.sparse_query_weight if sparse_embedding else 0.0

        if dense_weight == 0.0 and sparse_weight == 0.0:
            raise NotImplementedError("No embeddings available for hybrid search")

        rrf_k = settings.hybrid_rrf_k
        rank_limit = max(limit * 5, limit, 128)

        rank_expression: Rank | None = None
        if dense_embedding and dense_weight > 0:
            dense_knn = Knn(
                query=dense_embedding,
                key="$chroma_embedding",
                limit=rank_limit,
                ordinal=True,
                return_rank=True,
            )
            dense_rrf = Val(dense_weight) / (Val(rrf_k) + dense_knn)
            rank_expression = dense_rrf

        if sparse_embedding and sparse_weight > 0:
            sparse_knn = Knn(
                query=sparse_embedding,
                key="sparse_vector",
                limit=rank_limit,
                ordinal=True,
                return_rank=True,
            )
            sparse_rrf = Val(sparse_weight) / (Val(rrf_k) + sparse_knn)
            rank_expression = (
                sparse_rrf if rank_expression is None else rank_expression + sparse_rrf
            )

        if rank_expression is None:
            raise NotImplementedError("Hybrid rank expression could not be constructed")

        search_payload = (
            Search()
            .rank(rank_expression)
            .limit(max(limit * 3, limit))
            .select(Key.DOCUMENT, Key.SCORE, Key.METADATA, "post_title")
        )

        response = self.collection.search([search_payload])
        return self._parse_search_response(response, limit)

    def _parse_search_response(
        self, response: ChromaSearchResponse, limit: int
    ) -> list[PostSearchResult]:
        if not response.get("ids"):
            return []

        payload_ids = response["ids"][0]

        documents_payload_raw = response.get("documents")
        documents_payload: list[str] = []
        if documents_payload_raw and documents_payload_raw[0]:
            documents_source = cast(Sequence[str | None], documents_payload_raw[0])
            documents_payload = [doc or "" for doc in documents_source]

        metadatas_payload_raw = response.get("metadatas")
        metadatas_payload: list[dict[str, Any]] = []
        if metadatas_payload_raw and metadatas_payload_raw[0]:
            metadatas_source = cast(Sequence[dict[str, Any] | None], metadatas_payload_raw[0])
            metadatas_payload = [dict(metadata or {}) for metadata in metadatas_source]

        scores_payload_raw = response.get("scores")
        scores_payload: list[float | None] = []
        if scores_payload_raw and scores_payload_raw[0]:
            scores_source = cast(Sequence[float | None], scores_payload_raw[0])
            scores_payload = [
                float(score) if score is not None else None for score in scores_source
            ]

        seen_slugs: set[str] = set()
        search_results: list[PostSearchResult] = []

        for index, _doc_id in enumerate(payload_ids):
            metadata = metadatas_payload[index] if index < len(metadatas_payload) else {}
            if not metadata:
                continue

            slug = str(metadata.get("post_slug", ""))
            if not slug or slug in seen_slugs:
                continue

            seen_slugs.add(slug)

            excerpt_source = documents_payload[index] if index < len(documents_payload) else ""
            excerpt = excerpt_source[:300] if excerpt_source else ""

            score_raw = scores_payload[index] if index < len(scores_payload) else None
            score_val = float(score_raw) if score_raw is not None else 0.0

            search_results.append(
                self._build_search_result_from_metadata(
                    metadata=metadata,
                    excerpt=excerpt,
                    score=score_val,
                )
            )

            if len(search_results) >= limit:
                break

        return search_results

    @staticmethod
    def _build_search_result_from_metadata(
        *, metadata: dict[str, Any], excerpt: str, score: float
    ) -> PostSearchResult:
        return PostSearchResult(
            post_slug=str(metadata.get("post_slug", "")),
            post_title=str(metadata.get("post_title", "")),
            post_url=str(metadata.get("post_url", "")),
            excerpt=excerpt,
            relevance_score=score,
            published_at=ChromaService._parse_datetime(metadata.get("published_at")),
            tags=ChromaService._split_comma_separated(metadata.get("tags")),
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            logger.debug("Invalid datetime value encountered: %s", value)
            return None

    @staticmethod
    def _split_comma_separated(value: Any) -> list[str]:
        if not value:
            return []

        if isinstance(value, list):
            return [str(item) for item in value if item]

        return [part.strip() for part in str(value).split(",") if part.strip()]

    async def delete_post(self, slug: str) -> None:
        results = self.collection.get(where={"post_slug": slug}, limit=300)

        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(f"Deleted {len(results['ids'])} chunks for post: {slug}")

    async def get_indexed_post_slugs(self) -> set[str]:
        # Paginate through all results respecting Chroma Cloud's limit
        slugs = set()
        offset = 0
        batch_size = 300  # Chroma Cloud limit

        while True:
            try:
                results = self.collection.get(limit=batch_size, offset=offset)

                if not results["ids"]:
                    break

                for metadata in results["metadatas"] or []:
                    if slug := metadata.get("post_slug"):
                        slugs.add(str(slug))

                # If we got fewer results than requested, we've reached the end
                if len(results["ids"]) < batch_size:
                    break

                offset += batch_size
            except Exception as e:
                logger.error(f"Error fetching indexed slugs at offset {offset}: {e}")
                break

        return slugs
