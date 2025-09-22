# Repository Guidelines

## Project Structure & Module Organization
The application code lives in `src/`, with `main.py` bootstrapping the MCP server, `mcp_server.py` defining FastAPI routes, and services such as `chroma_service.py`, `ghost_client.py`, and `indexer.py` handling storage, API access, and synchronization. Shared models and settings sit in `models.py` and `config.py`. Tests reside in `tests/` and mirror the runtime modules (`test_api.py`, `test_mcp_tools.py`, etc.). Supporting tooling includes the project-wide `pyproject.toml`, `Makefile`, container specs (`Dockerfile`, `Dockerfile.dev`, `docker-compose.yml`), and helper scripts like `run.sh` and `validate-docker.sh`. Coverage artifacts land in `htmlcov/`; clear it before committing.

## Build, Test, and Development Commands
Install dependencies with `uv sync --all-extras`. Use `uv run python -m src.main` or `./run.sh` to start the server locally. `make dev` installs development tooling, `make format` and `make lint` apply Ruff formatting and linting, `make test` runs the pytest suite with coverage, and `make check` executes the full formatting/lint/test pipeline. When debugging a single target, run `uv run pytest tests/test_api.py -vv`.

## Coding Style & Naming Conventions
Target Python 3.12, four-space indentation, and the Ruff defaults configured in `pyproject.toml` (line length 100, double-quoted strings). Keep modules and functions snake_case, classes PascalCase, and constants upper snake_case. Add type hints everywhere—mypy runs in strict mode—plus concise docstrings for public entry points such as new MCP tools.

## Testing Guidelines
Write unit tests alongside new functionality under `tests/` using the `test_*.py` pattern. Prefer pytest fixtures for external dependencies and async tests (pytest-asyncio is already configured). Maintain coverage by running `make test` or `uv run pytest --cov=src --cov-report=term-missing`; regenerate local HTML reports via `pytest --cov --cov-report=html` and inspect `htmlcov/index.html` before cleanup.

## Commit & Pull Request Guidelines
Use short, present-tense commit subjects (e.g., `Add webhook secret validation`) and additional context in the body when needed. Reference related issues or tickets in either the body or PR description. Open PRs only after `make check` passes, include a brief testing summary, and attach API output or screenshots when altering HTTP behavior. Flag configuration changes, especially updates to `.env` expectations, so reviewers can adjust deployment secrets.

## Security & Configuration Tips
Store Ghost Admin and Chroma credentials in `.env` only; never commit secrets. Keep webhook secrets aligned between Ghost and `config.py`. Use `validate-docker.sh` before publishing container images to ensure the runtime environment honors required environment variables.
