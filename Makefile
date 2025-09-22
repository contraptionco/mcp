.PHONY: help install dev test lint format clean run docker-build docker-run docker-test docker-dev

# Default target
help:
	@echo "Contraption Company MCP - Available commands:"
	@echo ""
	@echo "  make install      Install dependencies"
	@echo "  make dev          Install with dev dependencies"
	@echo "  make test         Run tests"
	@echo "  make lint         Run linting"
	@echo "  make format       Format code"
	@echo "  make clean        Clean up generated files"
	@echo "  make run          Run the server locally"
	@echo ""
	@echo "  Docker commands:"
	@echo "  make docker-build Build Docker image"
	@echo "  make docker-run   Run Docker container"
	@echo "  make docker-test  Test Docker build"
	@echo "  make docker-dev   Run development container"

# Install dependencies
install:
	@echo "Installing dependencies..."
	@uv sync

# Install with dev dependencies
dev:
	@echo "Installing dev dependencies..."
	@uv sync --all-extras
	@uv run pre-commit install

# Run tests
test:
	@echo "Running tests..."
	@uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Run linting
lint:
	@echo "Running linting..."
	@uv run ruff check src tests
	@uv run mypy src --ignore-missing-imports

# Format code
format:
	@echo "Formatting code..."
	@uv run ruff format src tests
	@uv run ruff check src tests --fix

# Clean up
clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	@rm -rf build dist *.egg-info

# Run server locally
run:
	@echo "Starting Contraption Company MCP..."
	@uv run python -m src.main

# Docker build
docker-build:
	@echo "Building Docker image..."
	@docker build -t ghost-mcp-server:latest .

# Docker run
docker-run:
	@echo "Running Docker container..."
	@docker run -d --name ghost-mcp \
		-p 8000:8000 \
		--env-file .env \
		--restart unless-stopped \
		ghost-mcp-server:latest

# Docker test
docker-test:
	@echo "Testing Docker build..."
	@./test-docker.sh

# Docker dev
docker-dev:
	@echo "Running development container..."
	@docker-compose --profile dev up

# Quick test without coverage
quick-test:
	@uv run pytest tests/ -x

# Check everything before commit
check: format lint test
	@echo "✅ All checks passed!"