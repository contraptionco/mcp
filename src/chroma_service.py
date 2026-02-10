import asyncio
import logging
import time
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

import chromadb
import chromadb.execution.expression as chroma_expr
from chromadb.api.types import (
    IntInvertedIndexConfig,
    Schema,
    SparseVectorIndexConfig,
    StringInvertedIndexConfig,
    VectorIndexConfig,
)
from chromadb.api.types import (
    SearchResult as ChromaSearchResponse,
)
from chromadb.base_types import SparseVector
from chromadb.types import Metadata

from src.config import settings
from src.embeddings import EmbeddingService, QueryEmbeddingService
from src.models import ContentType, PostChunk, PostSummary
from src.models import SearchResult as PostSearchResult

logger = logging.getLogger(__name__)


class ChromaService:
    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.query_embedding_service = QueryEmbeddingService()
        self.client = chromadb.CloudClient(
            tenant=settings.chroma_tenant,
            database=settings.chroma_database,
            api_key=settings.chroma_api_key,
        )
        self.collection_name = settings.chroma_collection
        self.query_collection_name = settings.chroma_query_collection
        self._ensure_collection()
        self._ensure_query_collection()

    def _build_schema(self) -> Schema:
        schema = Schema()

        vector_index = VectorIndexConfig(
            embedding_function=None,
            source_key="#document",
            space="cosine",
        )
        schema.create_index(config=vector_index)

        sparse_index = SparseVectorIndexConfig(
            embedding_function=self.embedding_service.sparse_function,
        )
        schema.create_index(config=sparse_index, key="sparse_vector")

        for metadata_key in (
            "post_id",
            "post_slug",
            "post_title",
            "post_url",
            "content_type",
            "tags",
            "authors",
        ):
            schema.create_index(config=StringInvertedIndexConfig(), key=metadata_key)

        for metadata_key in ("chunk_index", "total_chunks"):
            schema.create_index(config=IntInvertedIndexConfig(), key=metadata_key)

        return schema

    def _build_query_schema(self) -> Schema:
        schema = Schema()

        vector_index = VectorIndexConfig(
            embedding_function=self.query_embedding_service.dense_function,
            source_key="#document",
            space="cosine",
        )
        schema.create_index(config=vector_index)

        for metadata_key in ("top_match_id", "top_match_url"):
            schema.create_index(config=StringInvertedIndexConfig(), key=metadata_key)

        schema.create_index(config=IntInvertedIndexConfig(), key="query_ts")

        return schema

    def _ensure_collection(self) -> None:
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                schema=self._build_schema(),
            )
            logger.info(f"Connected to collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error creating/getting collection: {e}")
            raise

    def _ensure_query_collection(self) -> None:
        try:
            self.query_collection = self.client.get_or_create_collection(
                name=self.query_collection_name,
                schema=self._build_query_schema(),
            )
            logger.info(f"Connected to query collection: {self.query_collection_name}")
        except Exception as e:
            logger.error(f"Error creating/getting query collection: {e}")
            raise

    def _build_where(self, filters: dict[str, Any]) -> dict[str, Any]:
        items = [(key, value) for key, value in filters.items() if value is not None]
        if not items:
            raise ValueError("At least one filter is required to build a where clause")
        if len(items) == 1:
            key, value = items[0]
            return {key: value}
        return {"$and": [{key: value} for key, value in items]}

    async def upsert_chunks(self, chunks: list[PostChunk]) -> None:
        if not chunks:
            return

        ids: list[str] = []
        texts: list[str] = []
        metadata_records: list[dict[str, str | int | float | bool | None | SparseVector]] = []

        for chunk in chunks:
            chunk_id = f"{chunk.content_type}_{chunk.post_id}_{chunk.chunk_index}"
            ids.append(chunk_id)
            texts.append(chunk.chunk_text)

            metadata_dict: dict[str, str | int | float | bool | None | SparseVector] = {
                "post_id": chunk.post_id,
                "post_slug": chunk.post_slug,
                "post_title": chunk.post_title,
                "post_url": chunk.post_url,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "content_type": chunk.content_type,
                "tags": ",".join(chunk.tags) if chunk.tags else "",
                "authors": ",".join(chunk.authors) if chunk.authors else "",
            }

            if chunk.published_at:
                metadata_dict["published_at"] = chunk.published_at.isoformat()
            if chunk.updated_at:
                metadata_dict["updated_at"] = chunk.updated_at.isoformat()
            if chunk.content_hash:
                metadata_dict["content_hash"] = chunk.content_hash

            metadata_records.append(metadata_dict)

        embeddings: list[list[float]] = self.embedding_service.embed_chunks(texts)
        embeddings_seq = cast(list[Sequence[float] | Sequence[int]], embeddings)
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
                sparse_vector = SparseVector(indices=[], values=[])
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

    async def get_post_markdown(
        self,
        slug: str,
        *,
        content_url: str | None = None,
        content_type: str | None = None,
    ) -> tuple[PostSummary | None, str | None]:
        results = None
        if content_url:
            where = self._build_where({"post_url": content_url, "content_type": content_type})
            results = self.collection.get(where=where, limit=300)

        if not results or not results.get("ids"):
            where = self._build_where({"post_slug": slug, "content_type": content_type})
            results = self.collection.get(where=where, limit=300)

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
        post_title = str(primary_metadata.get("post_title", "")).strip()
        excerpt_source = next(
            (
                chunk_text
                for _, chunk_text, _ in chunks
                if chunk_text and chunk_text.strip() and chunk_text.strip() != post_title
            ),
            chunks[0][1],
        )

        summary = PostSummary(
            id=str(primary_metadata.get("post_id", "")),
            slug=slug,
            title=str(primary_metadata.get("post_title", "")),
            excerpt=excerpt_source[:200] if excerpt_source else None,
            url=str(primary_metadata.get("post_url", "")),
            published_at=self._parse_datetime(primary_metadata.get("published_at")),
            updated_at=self._parse_datetime(primary_metadata.get("updated_at")),
            content_type=self._normalize_content_type(primary_metadata.get("content_type")),
            tags=self._filter_public_tag_names(
                self._split_comma_separated(primary_metadata.get("tags"))
            ),
            authors=self._split_comma_separated(primary_metadata.get("authors")),
        )

        return summary, markdown

    async def get_post_markdown_by_id(self, post_id: str) -> tuple[PostSummary | None, str | None]:
        results = self.collection.get(
            where={"post_id": post_id},
            limit=1,
        )

        metadatas = cast(list[dict[str, Any] | None], results.get("metadatas", []))
        if not metadatas or metadatas[0] is None:
            return None, None

        slug = str(metadatas[0].get("post_slug", "")).strip()
        if not slug:
            return None, None

        content_type = str(metadatas[0].get("content_type", "")).strip() or None
        return await self.get_post_markdown(slug, content_type=content_type)

    async def list_posts(
        self,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "newest",
    ) -> list[PostSummary]:
        # Chroma Cloud has a limit of 300 items per request
        all_results = self.collection.get(limit=300, where={"content_type": "post"})

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
                    "content_type": self._normalize_content_type(metadata.get("content_type")),
                    "tags": self._filter_public_tag_names(
                        str(metadata.get("tags", "")).split(",") if metadata.get("tags") else []
                    ),
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
                content_type=self._normalize_content_type(p.get("content_type")),
                tags=p["tags"],
                authors=p["authors"],
            )
            for p in paginated_posts
        ]

    async def search(
        self,
        query: str,
        limit: int = 10,
        *,
        distinct_results: bool = False,
    ) -> list[PostSearchResult]:
        dense_embedding: list[float] | None = None
        try:
            dense_embedding = self.embedding_service.embed_query(query)
        except Exception as exc:
            logger.warning("Dense query embedding failed; falling back to sparse-only: %s", exc)

        sparse_embedding = self.embedding_service.sparse_embed_query(query)

        results, top_match = self._hybrid_rrf_search(
            dense_embedding=dense_embedding,
            sparse_embedding=sparse_embedding,
            limit=limit,
            distinct_results=distinct_results,
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

        asyncio.create_task(self.log_query(query, top_match))

        return results

    def _hybrid_rrf_search(
        self,
        *,
        dense_embedding: list[float] | None,
        sparse_embedding: SparseVector | None,
        limit: int,
        distinct_results: bool,
    ) -> tuple[list[PostSearchResult], dict[str, str | None]]:
        dense_weight = settings.dense_query_weight if dense_embedding else 0.0
        sparse_weight = settings.sparse_query_weight if sparse_embedding else 0.0

        if dense_weight == 0.0 and sparse_weight == 0.0:
            raise NotImplementedError("No embeddings available for search")

        rrf_k = settings.hybrid_rrf_k
        rank_limit = max(limit * 5, limit, 128)

        rank_expression: Any | None = None
        if dense_embedding and dense_weight > 0:
            dense_knn = chroma_expr.Knn(
                query=dense_embedding,
                key="#embedding",
                limit=rank_limit,
                return_rank=True,
            )
            rank_expression = chroma_expr.Val(-dense_weight) / (chroma_expr.Val(rrf_k) + dense_knn)

        if sparse_embedding and sparse_weight > 0:
            sparse_knn = chroma_expr.Knn(
                query=sparse_embedding,
                key="sparse_vector",
                limit=rank_limit,
                return_rank=True,
            )
            sparse_rrf = chroma_expr.Val(-sparse_weight) / (chroma_expr.Val(rrf_k) + sparse_knn)
            rank_expression = (
                sparse_rrf if rank_expression is None else rank_expression + sparse_rrf
            )

        if rank_expression is None:
            raise NotImplementedError("Rank expression could not be constructed")

        search_payload = (
            cast(Any, chroma_expr.Search())
            .rank(rank_expression)
            .limit(max(limit * 3, limit))
            .select("#document", "#score", "#metadata", "post_title")
        )
        if distinct_results:
            group_by = getattr(chroma_expr, "GroupBy", None)
            min_k = getattr(chroma_expr, "MinK", None)
            if group_by is None or min_k is None:
                raise RuntimeError("Chroma GroupBy support is unavailable; upgrade chromadb.")
            search_payload = search_payload.group_by(
                group_by(keys="post_url", aggregate=min_k(keys="#score", k=1))
            )

        response = self.collection.search([search_payload])
        return self._parse_search_response(response, limit, distinct_results=distinct_results)

    def _parse_search_response(
        self,
        response: ChromaSearchResponse,
        limit: int,
        *,
        distinct_results: bool,
    ) -> tuple[list[PostSearchResult], dict[str, str | None]]:
        if not response.get("ids"):
            return [], {}

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

        seen_urls: set[str] = set()
        top_match: dict[str, str | None] = {}
        if payload_ids:
            top_match_id = payload_ids[0]
            metadata = metadatas_payload[0] if metadatas_payload else {}
            top_match = {
                "post_id": str(metadata.get("post_id", "")) if metadata else None,
                "post_url": str(metadata.get("post_url", "")) if metadata else None,
                "post_slug": str(metadata.get("post_slug", "")) if metadata else None,
                "chunk_id": str(top_match_id),
            }

        search_results: list[PostSearchResult] = []

        for index, _doc_id in enumerate(payload_ids):
            metadata = metadatas_payload[index] if index < len(metadatas_payload) else {}
            if not metadata:
                continue

            url = str(metadata.get("post_url", ""))
            if distinct_results:
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

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

        return search_results, top_match

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
            content_type=ChromaService._normalize_content_type(metadata.get("content_type")),
            tags=ChromaService._filter_public_tag_names(
                ChromaService._split_comma_separated(metadata.get("tags"))
            ),
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
    def _normalize_content_type(value: Any) -> ContentType:
        if str(value or "").strip().lower() == "page":
            return "page"
        return "post"

    @staticmethod
    def _split_comma_separated(value: Any) -> list[str]:
        if not value:
            return []

        if isinstance(value, list):
            return [str(item) for item in value if item]

        return [part.strip() for part in str(value).split(",") if part.strip()]

    @staticmethod
    def _filter_public_tag_names(tags: list[str]) -> list[str]:
        return [tag for tag in tags if tag and not tag.startswith("#")]

    async def log_query(self, query: str, top_match: dict[str, str | None]) -> None:
        if not query:
            return

        timestamp = int(time.time())
        try:
            await asyncio.to_thread(self._log_query_sync, query, timestamp, top_match)
        except Exception as exc:  # pragma: no cover - non-blocking logging
            logger.error("Failed to log query asynchronously: %s", exc, exc_info=True)

    def _log_query_sync(
        self,
        query: str,
        timestamp: int,
        top_match: dict[str, str | None],
    ) -> None:
        query_embedding_service = QueryEmbeddingService()
        try:
            embedding = query_embedding_service.embed_query(query)
            query_embeddings = cast(list[Sequence[float] | Sequence[int]], [embedding])
            query_id = f"query_{timestamp}_{uuid.uuid4().hex}"

            metadata: dict[str, str | int] = {"query_ts": timestamp}

            top_match_id = top_match.get("post_id") or top_match.get("chunk_id")
            if top_match_id:
                metadata["top_match_id"] = top_match_id

            top_match_url = top_match.get("post_url")
            if top_match_url:
                metadata["top_match_url"] = top_match_url

            self.query_collection.upsert(
                ids=[query_id],
                embeddings=query_embeddings,
                documents=[query],
                metadatas=[metadata],
            )
        except Exception as exc:  # pragma: no cover - best-effort logging
            logger.error("Failed to log query '%s' to Chroma: %s", query[:50], exc, exc_info=True)
        finally:
            query_embedding_service.close()

    async def delete_post(self, slug: str, content_type: str | None = None) -> None:
        where = self._build_where({"post_slug": slug, "content_type": content_type})
        results = self.collection.get(where=where, limit=300)

        if results["ids"]:
            self.collection.delete(ids=results["ids"])
            logger.info(f"Deleted {len(results['ids'])} chunks for post: {slug}")

    async def get_indexed_content_index(
        self,
    ) -> dict[tuple[str, ContentType], dict[str, Any]]:
        # Paginate through all results respecting Chroma Cloud's limit
        content_index: dict[tuple[str, ContentType], dict[str, Any]] = {}
        offset = 0
        batch_size = 300  # Chroma Cloud limit

        while True:
            try:
                results = self.collection.get(limit=batch_size, offset=offset)

                if not results["ids"]:
                    break

                for metadata in results["metadatas"] or []:
                    if not metadata:
                        continue
                    slug = str(metadata.get("post_slug", "")).strip()
                    if not slug:
                        continue
                    content_type = self._normalize_content_type(metadata.get("content_type"))
                    key = (slug, content_type)
                    if key not in content_index:
                        content_index[key] = {
                            "updated_at": self._parse_datetime(metadata.get("updated_at")),
                            "content_hash": (
                                str(metadata.get("content_hash", "")).strip()
                                if metadata.get("content_hash")
                                else None
                            ),
                        }

                # If we got fewer results than requested, we've reached the end
                if len(results["ids"]) < batch_size:
                    break

                offset += batch_size
            except Exception as e:
                logger.error(f"Error fetching indexed content at offset {offset}: {e}")
                break

        return content_index
