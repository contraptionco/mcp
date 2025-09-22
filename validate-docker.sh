#!/bin/bash

# Script to validate Docker configuration

echo "🔍 Validating Docker files..."

# Check if required files exist
FILES_TO_CHECK=(
    "Dockerfile"
    "Dockerfile.dev"
    "docker-compose.yml"
    ".dockerignore"
    "pyproject.toml"
    "src/main.py"
)

for file in "${FILES_TO_CHECK[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file exists"
    else
        echo "❌ $file is missing"
        exit 1
    fi
done

# Validate Dockerfile syntax using hadolint if available
if command -v hadolint &> /dev/null; then
    echo "🔍 Linting Dockerfile with hadolint..."
    hadolint Dockerfile
    hadolint Dockerfile.dev
else
    echo "ℹ️  hadolint not installed, skipping Dockerfile linting"
    echo "   Install with: brew install hadolint"
fi

# Check docker-compose syntax
if command -v docker-compose &> /dev/null; then
    echo "🔍 Validating docker-compose.yml..."
    docker-compose config --quiet
    if [ $? -eq 0 ]; then
        echo "✅ docker-compose.yml is valid"
    else
        echo "❌ docker-compose.yml has errors"
        exit 1
    fi
else
    echo "ℹ️  docker-compose not available, skipping validation"
fi

# Check Python syntax
echo "🔍 Checking Python syntax..."
python3 -m py_compile src/*.py
if [ $? -eq 0 ]; then
    echo "✅ Python files are syntactically correct"
else
    echo "❌ Python syntax errors found"
    exit 1
fi

# Estimate Docker image size
echo ""
echo "📊 Estimated image sizes:"
echo "  Base python:3.12-slim: ~150MB"
echo "  With dependencies: ~500-800MB"
echo "  Multi-stage final: ~400-600MB"

echo ""
echo "✅ All validations passed!"
echo ""
echo "📋 Next steps:"
echo "1. Ensure Docker daemon is running"
echo "2. Run: docker build -t ghost-mcp-server ."
echo "3. Or use: docker-compose up"
echo "4. For development: docker-compose --profile dev up"