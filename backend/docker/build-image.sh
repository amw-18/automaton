#!/bin/bash
# Build the Playwright test runner Docker image

set -e

echo "🔨 Building Playwright test runner Docker image..."

docker build \
  -f Dockerfile.playwright-runner \
  -t playwright-runner:latest \
  .

echo "✅ Docker image built successfully!"
echo "   Image: playwright-runner:latest"

# Show image info
docker images playwright-runner:latest
