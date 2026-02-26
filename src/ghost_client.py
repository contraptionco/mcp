import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import GhostPost

logger = logging.getLogger(__name__)


class GhostAPIClient:
    def __init__(self) -> None:
        self.api_url = settings.ghost_api_url.rstrip("/")
        self.api_key = settings.ghost_admin_api_key
        self.client = httpx.AsyncClient(timeout=30.0)
        self._parse_admin_key()

    def _parse_admin_key(self) -> None:
        """Parse the Admin API key to extract key_id and secret."""
        try:
            key_id, secret = self.api_key.split(":")
            self.key_id = key_id
            self.secret = bytes.fromhex(secret)
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid Admin API key format: {e}")
            raise ValueError("Admin API key must be in format 'id:secret'") from e

    def _build_published_filter(self) -> str:
        return "status:published"

    def _generate_token(self) -> str:
        """Generate JWT token for Admin API authentication."""
        iat = datetime.now(UTC)
        exp = iat + timedelta(minutes=5)

        payload = {"iat": int(iat.timestamp()), "exp": int(exp.timestamp()), "aud": "/admin/"}

        token = jwt.encode(
            payload,
            self.secret,
            algorithm="HS256",
            headers={"alg": "HS256", "kid": self.key_id, "typ": "JWT"},
        )

        return str(token)

    async def __aenter__(self) -> "GhostAPIClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_posts(
        self,
        limit: int = 15,
        page: int = 1,
        include: str = "tags,authors",
        filter_str: str | None = None,
    ) -> tuple[list[GhostPost], dict[str, Any]]:
        headers = {"Authorization": f"Ghost {self._generate_token()}"}

        params = {
            "limit": str(limit),
            "page": str(page),
            "include": include,
            "formats": "html,plaintext",
        }

        if filter_str:
            params["filter"] = filter_str

        url = f"{self.api_url}/ghost/api/admin/posts/"

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            raw_posts = data.get("posts", [])
            logger.debug(f"Fetched {len(raw_posts)} posts from Ghost API")

            # Debug: Check what fields we're getting
            if raw_posts:
                sample_post = raw_posts[0]
                logger.debug(f"Sample post keys: {list(sample_post.keys())}")
                logger.debug(f"Sample post has html: {'html' in sample_post}")
                logger.debug(f"Sample post has plaintext: {'plaintext' in sample_post}")
                if "html" in sample_post:
                    logger.debug(
                        f"HTML content length: {len(sample_post['html']) if sample_post['html'] else 0}"
                    )

            posts = [GhostPost(**post) for post in raw_posts]
            meta = data.get("meta", {})

            return posts, meta
        except httpx.HTTPError as e:
            logger.error(f"Error fetching posts from Ghost: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_pages(
        self,
        limit: int = 15,
        page: int = 1,
        include: str = "tags,authors",
        filter_str: str | None = None,
    ) -> tuple[list[GhostPost], dict[str, Any]]:
        headers = {"Authorization": f"Ghost {self._generate_token()}"}

        params = {
            "limit": str(limit),
            "page": str(page),
            "include": include,
            "formats": "html,plaintext",
        }

        if filter_str:
            params["filter"] = filter_str

        url = f"{self.api_url}/ghost/api/admin/pages/"

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            raw_pages = data.get("pages", [])
            logger.debug(f"Fetched {len(raw_pages)} pages from Ghost API")

            pages = [GhostPost(**page) for page in raw_pages]
            meta = data.get("meta", {})

            return pages, meta
        except httpx.HTTPError as e:
            logger.error(f"Error fetching pages from Ghost: {e}")
            raise

    async def get_post_by_slug(self, slug: str) -> GhostPost | None:
        headers = {"Authorization": f"Ghost {self._generate_token()}"}

        params = {
            "include": "tags,authors",
            "formats": "html,plaintext",
        }

        url = f"{self.api_url}/ghost/api/admin/posts/slug/{slug}/"

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            posts = data.get("posts", [])
            if posts:
                return GhostPost(**posts[0])
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"Error fetching post by slug {slug}: {e}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"Error fetching post by slug {slug}: {e}")
            raise

    async def get_page_by_slug(self, slug: str) -> GhostPost | None:
        headers = {"Authorization": f"Ghost {self._generate_token()}"}

        params = {
            "include": "tags,authors",
            "formats": "html,plaintext",
        }

        url = f"{self.api_url}/ghost/api/admin/pages/slug/{slug}/"

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            pages = data.get("pages", [])
            if pages:
                return GhostPost(**pages[0])
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"Error fetching page by slug {slug}: {e}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"Error fetching page by slug {slug}: {e}")
            raise

    async def get_all_posts(self) -> list[GhostPost]:
        all_posts = []
        page = 1

        # Fetch all published posts (excluding drafts)
        filter_str = self._build_published_filter()
        while True:
            posts, meta = await self.get_posts(limit=50, page=page, filter_str=filter_str)
            all_posts.extend(posts)

            pagination = meta.get("pagination", {})
            if page >= pagination.get("pages", 1):
                break

            page += 1

        logger.info(f"Fetched {len(all_posts)} posts from Ghost")
        return all_posts

    async def get_all_pages(self) -> list[GhostPost]:
        all_pages = []
        page = 1

        filter_str = self._build_published_filter()
        while True:
            pages, meta = await self.get_pages(limit=50, page=page, filter_str=filter_str)
            all_pages.extend(pages)

            pagination = meta.get("pagination", {})
            if page >= pagination.get("pages", 1):
                break

            page += 1

        logger.info(f"Fetched {len(all_pages)} pages from Ghost")
        return all_pages
