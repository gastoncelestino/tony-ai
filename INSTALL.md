# Tony-AI - Instalación

## 0. Requisitos obligatorios

Tony-AI requiere todos estos componentes para una instalación completa:

- **Python 3.10+** — servidores MCP y tooling Python.
- **Bun** — scripts TypeScript y plugins.
- **OpenCode CLI** — orquestador SDD.
- **Ollama** — ejecución de los modelos locales.
- **Docker + Docker Compose** — servicios de soporte, especialmente Qdrant.
- **GGA (Gentleman Guardian Angel)** — code review obligatorio antes de commit.
- **tree-sitter + tree-sitter-languages** — chunking estructural obligatorio del Code Indexer.

No hay dependencias opcionales en el bootstrap oficial. `setup.sh` falla si cualquiera de estos requisitos no está disponible.

Qdrant es obligatorio porque Code Indexer y Judgment Memory lo utilizan.

## 1. Clonar

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
git checkout dev
```

## 2. Bootstrap automático

```bash
./scripts/setup.sh
```

El bootstrap:

1. valida Python 3.10+, Bun, OpenCode CLI, Docker, Ollama y GGA;
2. valida e instala las dependencias Python de desarrollo, incluyendo tree-sitter;
3. comprueba Ollama y Qdrant;
4. usa Docker para levantar únicamente los servicios que falten;
5. descarga `qwen3-coder:30b`, `carstenuhlig/omnicoder-2-9b:q4_k_m`, `deepseek-r1:14b`, `ornith:9b`, `bge-m3` y `nomic-embed-text`;
6. configura `.env.example` con `TONY_INDEX_CHUNKER=tree-sitter`;
7. regenera `opencode.json` con rutas portables y el chunker obligatorio.

Podés ejecutar el bootstrap varias veces; `ollama pull` y la configuración son idempotentes.

## 3. Configuración manual

```bash
cp .env.example .env
```

Ajustá `TONY_REPO_ROOT` a la ruta absoluta del clone:

```env
TONY_REPO_ROOT=/home/tu-usuario/proyectos/tony-ai
TONY_OLLAMA_URL=http://localhost:11434
TONY_QDRANT_URL=http://localhost:6333
JUDGMENT_EMBED_MODEL=nomic-embed-text
CODE_EMBED_MODEL=bge-m3
TONY_IMPLEMENTATION_MODEL=carstenuhlig/omnicoder-2-9b:q4_k_m
TONY_INDEX_CHUNKER=tree-sitter
```

## 4. Servicios

Ollama puede estar instalado de forma nativa o ejecutarse mediante Docker, pero debe responder en `TONY_OLLAMA_URL`. Qdrant se ejecuta normalmente mediante Docker.

Si Ollama ya corre de forma nativa, no levantes otro Ollama sobre el puerto 11434:

```bash
cd docker
docker compose up -d qdrant
```

Si ninguno está corriendo:

```bash
cd docker
docker compose up -d ollama qdrant
```

Verificación:

```bash
curl http://localhost:11434/api/tags
curl http://localhost:6333/readyz
docker compose ps
```

## 5. GGA

GGA es obligatorio. Debe existir como `gga` en `PATH` antes de considerar terminado el bootstrap.

Una instalación típica desde el repositorio de GGA deja el ejecutable en `~/.local/bin/gga` y sus librerías en `~/.local/share/gga/lib`. Asegurate de que `~/.local/bin` esté en `PATH` y verificá:

```bash
gga --version
```

## 6. tree-sitter

Tree-sitter es obligatorio porque Code Indexer usa chunking estructural en lugar del chunker regex. Las dependencias están en `requirements-dev.txt`:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -c 'import tree_sitter, tree_sitter_languages; print("tree-sitter OK")'
```

No configures `TONY_INDEX_CHUNKER=regex` en una instalación soportada de Tony-AI.

## 7. Verificación

```bash
make health
make test
make validate-config
```

También podés ejecutar la suite Python directamente:

```bash
pytest tests
python3 tools/run-python-tests.py tests
```

## 8. Modelos de Ollama

El bootstrap instala estos modelos:

```text
qwen3-coder:30b
carstenuhlig/omnicoder-2-9b:q4_k_m
deepseek-r1:14b
ornith:9b
bge-m3
nomic-embed-text
```

El modelo de implementación canónico es `carstenuhlig/omnicoder-2-9b:q4_k_m`.

## 9. OpenCode

Los MCP servers se ejecutan desde `opencode.json` usando `TONY_REPO_ROOT`:

```bash
opencode mcp list
```

El Code Indexer debe mostrar `TONY_INDEX_CHUNKER=tree-sitter`.

## 10. Tests principales

| Componente | Test |
|---|---|
| Bootstrap y requisitos | `tests/test_setup.py` |
| Code Indexer | `tests/test_code_index_core.py` |
| Judgment Memory | `tests/test_judgment_memory_ledger.py` |
| Tony Kernel | `tests/test_kernel_state_machine.py` |
| Kernel integration | `tests/test_kernel_integration.py` |
| SDD E2E | `tests/test_sdd_flow_e2e.py` |
| TypeScript | `make test-ts` |

`tests/test_setup.py` verifica además que el modelo OmniCoder 2 y tree-sitter sean los valores canónicos y que no reaparezcan referencias legacy.

## 11. Troubleshooting

### Python no cumple la versión

```bash
python3 --version
```

Debe ser Python 3.10 o superior.

### Falta Bun, OpenCode o GGA

```bash
command -v bun
command -v opencode
command -v gga
```

Los tres deben devolver una ruta.

### Docker no responde

```bash
docker info
docker compose version
```

El daemon debe estar activo.

### Ollama no responde

```bash
curl http://localhost:11434/api/tags
```

Si usás Ollama nativo:

```bash
ollama serve
```

### Qdrant no responde

```bash
curl http://localhost:6333/readyz
cd docker && docker compose up -d qdrant
```

### tree-sitter no se puede importar

```bash
python3 -m pip install -r requirements-dev.txt
python3 -c 'import tree_sitter, tree_sitter_languages'
```

No cambies el chunker a regex para ocultar el problema: tree-sitter es un requisito obligatorio.
