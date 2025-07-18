#!/bin/bash

# Script de deploy para produção

set -e

echo "🚀 Deploy do MCP Hub para produção..."

# Verificar se está na branch main
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" != "main" ]]; then
    echo "⚠️  Não está na branch main. Branch atual: $BRANCH"
    read -p "Continuar mesmo assim? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Executar testes
echo "🧪 Executando testes..."
make test

# Build da imagem Docker
echo "🐳 Building Docker image..."
docker build -t mcp-hub:latest .

# Tag para registry (se configurado)
if [[ -n "$DOCKER_REGISTRY" ]]; then
    echo "🏷️  Tagging for registry..."
    docker tag mcp-hub:latest $DOCKER_REGISTRY/mcp-hub:latest
    docker tag mcp-hub:latest $DOCKER_REGISTRY/mcp-hub:$(git rev-parse --short HEAD)
    
    echo "📤 Pushing to registry..."
    docker push $DOCKER_REGISTRY/mcp-hub:latest
    docker push $DOCKER_REGISTRY/mcp-hub:$(git rev-parse --short HEAD)
fi

# Deploy com docker-compose
echo "🚀 Deploying with docker-compose..."
docker-compose up -d

# Verificar se está rodando
sleep 5
echo "🔍 Verificando deploy..."
curl -f http://localhost:8000/health || exit 1

echo "✅ Deploy concluído com sucesso!"
echo "🌐 MCP Hub disponível em http://localhost:8000"