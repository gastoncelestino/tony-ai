# Tony-AI — Instalación

## 1. Requisitos

Tony-AI tiene dos niveles de ejecución:

- **Suite local de desarrollo/tests:** Python 3.10+, Bun y las dependencias de `requirements-dev.txt`.
- **Runtime completo:** además requiere OpenCode CLI, Ollama, Docker + Compose, Qdrant y GGA.

| Requisito | Uso | Obligatorio para |
|---|---|---|
| Python 3.10+ | MCP servers, Kernel y tooling | Desarrollo y runtime |
| Bun | Plugins y tests TypeScript | Desarrollo y runtime OpenCode |
| OpenCode CLI | Orquestación de agentes/SDD | Runtime |
| Ollama | Modelos locales y embeddings | Runtime |
| Docker + Compose | Qdrant y Ollama | Bootstrap/runtime |
| GGA | Revisión de código antes de commit | Bootstrap/runtime |
| tree-sitter + `tree-sitter-language-pack` | Chunking estructural del Code Indexer | Desarrollo/runtime |

El bootstrap oficial valida estos requisitos y falla si no puede completar alguno de los checks críticos. Aunque Ollama puede ejecutarse fuera de Docker, `setup.sh` requiere que el daemon de Docker esté disponible porque también administra los servicios de soporte.

## 2. Clonar el repositorio

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
git checkout dev
```

## 3. Bootstrap recomendado

Ejecutar desde la raíz del repositorio:

```bash
./scripts/setup.sh
```

El bootstrap es idempotente y realiza, en este orden general:

1. verifica Python 3.10+, Bun, OpenCode CLI, Docker y Ollama;
2. verifica GGA y, si no está instalado, intenta clonarlo e instalarlo en un directorio temporal;
3. comprueba por separado la disponibilidad de Ollama y Qdrant;
4. inicia mediante Docker solamente el servicio de soporte que falte;
5. descarga los modelos locales requeridos;
6. instala `requirements-dev.txt` y verifica `tree_sitter` y `tree_sitter_language_pack`;
7. regenera `opencode.json` con `TONY_REPO_ROOT` y fuerza `TONY_INDEX_CHUNKER=tree-sitter`;
8. escribe `.env.example` con la configuración detectada.

El script también crea `opencode.json.bak` antes de modificar la configuración. Ese archivo es generado y no debe versionarse.

### Modelos descargados

```text
qwen3-coder:30b
carstenuhlig/omnicoder-2-9b:q4_k_m
deepseek-r1:14b
ornith:9b
bge-m3
nomic-embed-text
```

El modelo canónico de implementación es `carstenuhlig/omnicoder-2-9b:q4_k_m`.

## 4. Configuración del entorno

El bootstrap genera `.env.example`. Si se necesita una configuración persistente para el shell local:

```bash
cp .env.example .env
```

Los endpoints principales son:

```env
TONY_REPO_ROOT=/ruta/absoluta/al/clone
TONY_OLLAMA_URL=http://localhost:11434
TONY_QDRANT_URL=http://localhost:6333
TONY_INDEX_CHUNKER=tree-sitter
```

### Persistencia local

Los valores por defecto de los servidores MCP son archivos locales dentro del repositorio:

```text
local-memory/memory.db
judgment-memory/judgment-memory.db
code-index/.codeindex/
.tony-kernel/kernel-state.json
```

Pueden cambiarse mediante las variables que consumen los componentes correspondientes, en particular `LOCAL_MEMORY_DB` y `JUDGMENT_MEMORY_DB` para las bases SQLite.

## 5. Ollama y Qdrant

El bootstrap detecta cada servicio de forma independiente.

### Ollama nativo

Si Ollama ya está ejecutándose en `http://localhost:11434`, Tony-AI reutiliza esa instancia y no levanta otro contenedor de Ollama.

Verificación:

```bash
curl http://localhost:11434/api/tags
```

Si es necesario iniciarlo manualmente:

```bash
ollama serve
```

### Qdrant mediante Docker

```bash
cd docker
docker compose up -d qdrant
```

Verificación:

```bash
curl http://localhost:6333/readyz
docker compose ps
```

### Ambos servicios mediante Docker

Si ninguno está disponible:

```bash
cd docker
docker compose up -d ollama qdrant
```

No ejecute una segunda instancia de Ollama sobre el puerto `11434` si ya existe una instancia nativa activa.

## 6. GGA

GGA es parte del entorno requerido por el proyecto. Verifique:

```bash
gga --version
```

`setup.sh` intenta instalarlo automáticamente si `gga` no está en `PATH`. Para instalaciones manuales, asegúrese de que el ejecutable quede disponible en `PATH`, normalmente mediante `~/.local/bin`.

## 7. tree-sitter

El Code Indexer usa **tree-sitter obligatoriamente** para chunking estructural. No existe un modo soportado basado en regex.

La dependencia se instala desde:

```bash
python3 -m pip install -r requirements-dev.txt
```

Verificación:

```bash
python3 -c 'import tree_sitter, tree_sitter_language_pack; print("tree-sitter OK")'
```

Si aparece un error de importación, corrija la instalación de Python antes de continuar. No cambie `TONY_INDEX_CHUNKER` a `regex` para ocultar el problema.

## 8. OpenCode y MCP

`opencode.json` registra los servidores MCP y los agentes del proyecto. El bootstrap reemplaza las rutas locales frágiles por referencias basadas en `TONY_REPO_ROOT`.

Verifique la configuración:

```bash
bun run tools/validate-config.ts
```

Y, si OpenCode está instalado:

```bash
opencode mcp list
```

El health check también verifica que los cuatro servidores MCP puedan responder a `initialize`:

- `local-memory/server.py`
- `code-index/server.py`
- `judgment-memory/server.py`
- `kernel/mcp_server.py`

## 9. Verificación después de instalar

### Suite local

No requiere Ollama, Qdrant ni Docker:

```bash
make test
```

También puede ejecutarse la suite Python directamente:

```bash
python3 -m pytest tests
python3 tools/run-python-tests.py tests
```

El segundo comando es el runner Python standalone y no requiere Pytest.

### Health check completo

Requiere la infraestructura externa disponible:

```bash
make health
```

`health.sh` verifica configuración de OpenCode, los cuatro MCP servers, Ollama, Qdrant, almacenamiento local y un roundtrip real de embeddings/Qdrant.

### Smoke test de Qdrant

```bash
make verify-qdrant
```

### Validación de configuración

```bash
make validate-config
```

## 10. Comandos de desarrollo habituales

```bash
make test
make test-python
make test-ts
make test-kernel
make coverage
make health
```

Para levantar o detener los servicios Docker:

```bash
make docker-up
make docker-down
```

`make docker-up` levanta el stack definido en `docker/docker-compose.yml` y muestra los logs del proceso de pull de Ollama.

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

Cada comando debe devolver una ruta válida.

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

Si utiliza Ollama nativo:

```bash
ollama serve
```

### Qdrant no responde

```bash
curl http://localhost:6333/readyz
cd docker && docker compose up -d qdrant
```

### `tree_sitter` no se puede importar

```bash
python3 -m pip install -r requirements-dev.txt
python3 -c 'import tree_sitter, tree_sitter_language_pack'
```

### OpenCode informa rutas inválidas

Ejecute nuevamente:

```bash
./scripts/setup.sh
bun run tools/validate-config.ts
```

El bootstrap regenera las rutas MCP utilizando `TONY_REPO_ROOT`.

### El health check falla aunque `make test` pasa

Esto es posible y no implica necesariamente un fallo del código. `make test` valida la suite local sin servicios externos; `make health` valida además Ollama, Qdrant, MCP y embeddings reales. Revise primero:

```bash
curl http://localhost:11434/api/tags
curl http://localhost:6333/readyz
docker compose -f docker/docker-compose.yml ps
```

## 12. Referencias

- [README.md](README.md) — introducción, quickstart y uso.
- [ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura, memoria, SDD y Tony Kernel.
- [TESTING.md](TESTING.md) — estrategia completa de pruebas y CI.
- `scripts/setup.sh` — bootstrap reproducible del entorno.
- `scripts/health.sh` — verificación end-to-end.
