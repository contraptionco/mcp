"""Pytest configuration helpers."""

import os

# Ensure required environment variables exist before importing application settings.
DEFAULT_ENV_VARS = {
    "CHROMA_TENANT": "test-tenant",
    "CHROMA_DATABASE": "test-database",
    "CHROMA_API_KEY": "test-api-key",
    "CHROMA_COLLECTION": "test-collection",
    "CHROMA_QUERY_COLLECTION": "test-queries",
    "GHOST_ADMIN_API_KEY": "test-ghost-admin",
    "GHOST_API_URL": "https://example.com",
}

for var, value in DEFAULT_ENV_VARS.items():
    os.environ.setdefault(var, value)
