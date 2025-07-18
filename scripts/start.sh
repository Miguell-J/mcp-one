#!/bin/bash

# Script para iniciar o MCP Hub em desenvolvimento

set -e

echo "🚀 Iniciando MCP Hub..."

# Verificar se está em virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Recomendado usar virtual environment"
    echo "   python -m venv venv"
    echo "   source venv/bin/activate"
    echo ""
fi

# Verificar se config existe
if [[ ! -f "src/config.yaml" ]]; then
    echo "❌ Arquivo src/config.yaml não encontrado!"
    echo "   Criando arquivo de exemplo..."
    
    cat > src/config.yaml << 'EOF'
servers:
  - name: "mock"
    url: "http://localhost:3000"
    description: "Mock MCP Server for testing"
    enabled: true
    timeout: 30
    retry_attempts: 3

hub:
  host: "0.0.0.0"
  port: 8000
  debug: true
  log_level: "INFO"
  cors_enabled: true
  cors_origins:
    - "http://localhost:3000"
    - "http://localhost:8080"

cache:
  enabled: true
  ttl: 300
  max_size: 1000

rate_limit:
  enabled: false
  requests_per_minute: 100
  burst_size: 10
EOF

    echo "✅ Arquivo de configuração criado!"
fi

# Instalar dependências se necessário
if [[ ! -f ".installed" ]]; then
    echo "📦 Instalando dependências..."
    pip install -e ".[dev]"
    touch .installed
fi

# Executar testes rápidos
echo "🧪 Executando testes..."
python -m pytest tests/ -v --tb=short -x

# Iniciar servidor
echo "🌟 Iniciando servidor em http://localhost:8000"
echo "📖 Documentação em http://localhost:8000/docs"
echo "🔄 Pressione Ctrl+C para parar"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ===============================================
# ARQUIVO: scripts/test_integration.sh
# ===============================================
#!/bin/bash

# Script de teste de integração

set -e

echo "🧪 Executando testes de integração..."

# Iniciar mock MCP server
echo "🚀 Iniciando mock MCP server..."
python -c "
from fastapi import FastAPI
import uvicorn
from threading import Thread
import time

app = FastAPI()

@app.get('/health')
async def health():
    return {'status': 'healthy'}

@app.get('/tools')
async def tools():
    return {
        'tools': [
            {
                'name': 'echo',
                'description': 'Echo back the input',
                'parameters': {'message': 'string'}
            }
        ]
    }

@app.post('/call')
async def call_tool(request: dict):
    tool = request.get('tool')
    args = request.get('arguments', {})
    
    if tool == 'echo':
        return {'result': f'Echo: {args.get(\"message\", \"\")}'}
    else:
        return {'error': 'Tool not found'}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=3000)
" &

MOCK_PID=$!
sleep 2

# Iniciar MCP Hub
echo "🚀 Iniciando MCP Hub..."
python -m app.main &
HUB_PID=$!
sleep 3

# Função de cleanup
cleanup() {
    echo "🧹 Limpando processos..."
    kill $MOCK_PID 2>/dev/null || true
    kill $HUB_PID 2>/dev/null || true
    exit
}

trap cleanup EXIT

# Testes de integração
echo "📋 Testando endpoints..."

# Test 1: Health check
echo "1. Health check..."
curl -f http://localhost:8000/health || exit 1

# Test 2: Status
echo "2. Status..."
curl -f http://localhost:8000/status || exit 1

# Test 3: List tools
echo "3. List tools..."
curl -f http://localhost:8000/tools || exit 1

# Test 4: Call tool
echo "4. Call tool..."
curl -f -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "mock.echo", "arguments": {"message": "Hello World"}}' || exit 1

echo "✅ Todos os testes passaram!"