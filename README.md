# 🚀 MCP Hub

**Central hub for managing multiple MCP (Model Context Protocol) servers**

[![Tests](https://github.com/miguel/mcp-hub/actions/workflows/test.yml/badge.svg)](https://github.com/miguel/mcp-hub/actions/workflows/test.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## 🎯 O que é o MCP Hub?

O MCP Hub é um servidor central que conecta múltiplos servidores MCP independentes e expõe uma **interface unificada** para clientes (LLMs ou aplicações).

Em vez de conectar um LLM a vários MCPs manualmente, você conecta apenas ao Hub, que:

- ✅ Descobre e registra servidores MCP disponíveis
- ✅ Indexa suas ferramentas automaticamente
- ✅ Faz proxy das chamadas de ferramentas para o servidor correto
- ✅ Monitora saúde dos servidores em tempo real
- ✅ Oferece interface REST simples e intuitiva

## 🏗 Arquitetura

```
[ MCP Server A ]---\
                    \
[ MCP Server B ]-----[ MCP Hub ]-----[ Cliente LLM ]
                    /
[ MCP Server C ]---/
```

## 🚀 Quick Start

### 1. Instalação

```bash
git clone https://github.com/miguel/mcp-hub.git
cd mcp-hub
pip install -e ".[dev]"
```

### 2. Configuração

Edite o arquivo `src/config.yaml`:

```yaml
servers:
  - name: "github"
    url: "http://localhost:3000"
    description: "GitHub MCP Server"
    enabled: true
    timeout: 30
    retry_attempts: 3
  
  - name: "jupyter"
    url: "http://localhost:3001"
    description: "Jupyter MCP Server"
    enabled: true
    timeout: 60
    retry_attempts: 2

hub:
  host: "0.0.0.0"
  port: 8000
  debug: true
  log_level: "INFO"
```

### 3. Executar

```bash
# Modo desenvolvimento
make dev

# Ou produção
make run
```

O Hub estará disponível em `http://localhost:8000`

## 📖 Uso

### Listar ferramentas disponíveis

```bash
curl http://localhost:8000/tools
```

```json
{
  "tools": [
    {
      "name": "create_issue",
      "description": "Create a GitHub issue",
      "parameters": {"title": "string", "body": "string"},
      "server_name": "github",
      "full_name": "github.create_issue"
    },
    {
      "name": "run_code",
      "description": "Execute Python code",
      "parameters": {"code": "string"},
      "server_name": "jupyter",
      "full_name": "jupyter.run_code"
    }
  ]
}
```

### Executar ferramenta

```bash
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "github.create_issue",
    "arguments": {
      "title": "Bug no sistema",
      "body": "Detalhes do bug encontrado"
    }
  }'
```

```json
{
  "success": true,
  "result": "Issue #123 criada com sucesso",
  "execution_time_ms": 245.3,
  "server_name": "github"
}
```

### Status do Hub

```bash
curl http://localhost:8000/status
```

```json
{
  "version": "0.1.0",
  "uptime_seconds": 1234.56,
  "servers_count": 2,
  "servers_online": 2,
  "tools_count": 8,
  "last_refresh": "2024-01-15T10:30:00Z"
}
```

## 🛠 Desenvolvimento

### Setup do ambiente

```bash
# Instalar dependências de desenvolvimento
make dev-install

# Executar testes
make test

# Executar em modo watch
make test-watch

# Linting e formatação
make lint
make format
make type-check

# Executar todos os checks
make pre-commit
```

### Estrutura do projeto

```
src/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app
│   ├── core/
│   │   ├── registry.py  # Gerenciamento de MCPs
│   │   └── router.py    # Execução de ferramentas
│   └── models/
│       └── schemas.py   # Modelos Pydantic
├── config.yaml          # Configuração
tests/
└── test_mcp_hub.py      # Testes
```

### Adicionando novos MCPs

1. Edite `src/config.yaml`
2. Adicione a configuração do novo servidor
3. Reinicie o Hub (ou use `/servers/refresh`)

## 🔧 Configuração Avançada

### Cache

```yaml
cache:
  enabled: true
  ttl: 300  # 5 minutos
  max_size: 1000
```

### Rate Limiting

```yaml
rate_limit:
  enabled: true
  requests_per_minute: 100
  burst_size: 10
```

### CORS

```yaml
hub:
  cors_enabled: true
  cors_origins:
    - "http://localhost:3000"
    - "https://myapp.com"
```

## 🐳 Docker

```bash
# Build
docker build -t mcp-hub .

# Run
docker run -p 8000:8000 -v $(pwd)/config.yaml:/app/config.yaml mcp-hub
```

## 🤝 Contribuindo

1. Fork o repositório
2. Crie uma branch (`git checkout -b feature/nova-feature`)
3. Faça commit das mudanças (`git commit -am 'Add nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🎯 Roadmap

- [ ] **v0.2.0** - Descoberta automática de MCPs (zeroconf)
- [ ] **v0.3.0** - Interface web para gerenciamento
- [ ] **v0.4.0** - Autenticação e autorização
- [ ] **v0.5.0** - Métricas e monitoramento (Prometheus)
- [ ] **v1.0.0** - Produção ready com clustering

## 🆘 Suporte

- 📖 [Documentação](https://mcp-hub.readthedocs.io)
- 🐛 [Issues](https://github.com/miguel/mcp-hub/issues)
- 💬 [Discussões](https://github.com/miguel/mcp-hub/discussions)

---

**Feito com ❤️ por Miguel**