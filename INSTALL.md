# Tony-AI — Instalación

## 1. Requisitos

Tony-AI tiene dos niveles de ejecución:

- **Suite local de desarrollo/tests:** Python 3.10+, Bun y las dependencias de `requirements-dev.txt`.
- **Runtime completo:** además requiere OpenCode CLI, llama.cpp (llama-server) + llama-swap, Qdrant y GGA.

| Requisito | Uso | Obligatorio para |
|---|---|---|
| Python 3.10+ | MCP servers, Kernel y tooling | Desarrollo y runtime |
| Bun | Plugins y tests TypeScript | Desarrollo y runtime OpenCode |
| OpenCode CLI | Orquestación de agentes/SDD | Runtime |
| llama.cpp + llama-swap | Modelos locales y embeddings | Runtime |
| Qdrant | Vector store | Instalador/runtime |
| GGA | Revisión de código antes de commit | Instalador/runtime |
| tree-sitter + `tree-sitter-language-pack` | Chunking estructural del Code Indexer | Desarrollo/runtime |

El instalador `setup.sh` valida estos requisitos y falla si no puede completar alguno de los componentes requeridos.

## 2. Clonar el repositorio

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
git checkout dev
```

## 3. Instalación recomendada

Ejecutar desde la raíz del repositorio:

```bash
./scripts/setup.sh
```

La configuración inicial es reutilizable y ejecuta, secuencialmente:

1. verifica Python 3.10+, Bun, OpenCode CLI, llama-server y llama-swap;
2. verifica GGA y, si no está instalado, intenta clonarlo e instalarlo en un directorio temporal;
3. copia `config.yaml` de llama-swap al directorio de runtime (`~/.tony-ai/llama-swap/config.yaml`);
4. comprueba por separado la disponibilidad de llama-swap y Qdrant;
5. si Qdrant no responde y hay un binario nativo declarado en `TONY_QDRANT_BIN`, lo autoarranca;
6. verifica que los modelos de chat y de embeddings estén declarados en llama-swap (y opcionalmente los "calienta" con una request mínima);
7. instala `requirements-dev.txt` y verifica `tree_sitter` y `tree_sitter_language_pack`;
8. regenera `opencode.json` con `TONY_REPO_ROOT` y fuerza `TONY_INDEX_CHUNKER=tree-sitter`;
9. verifica que `.env.example` existe en el repositorio (no lo modifica);
10. crea `.env` copiando desde `.env.example` (si no existe ya);
11. valida que `.env` tiene todas las variables obligatorias y que los URLs/rutas son accesibles.
12. crea `opencode.json.bak` antes de modificar la configuración.

### Modelos declarados en llama-swap

```text
qwen3-coder:30b
omnicoder:9b
deepseek-r1:14b
bge-m3
nomic-embed-text
```

El modelo canónico de implementación es `omnicoder:9b`. Los GGUF de cada modelo se descargan aparte (no los baja `setup.sh`) y se declaran en `config.yaml` de llama-swap con su ruta local.

## 4. Configuración del entorno

`.env.example` es estático y se entrega con el repositorio.  
El instalador `setup.sh` verifica su existencia y automáticamente crea `.env` copiando la configuración y reemplazando las rutas reales del sistema.

```env
TONY_REPO_ROOT=/path/to/tony-ai          # → reemplazado con ruta real
TONY_LLAMASWAP_URL=http://localhost:8080
TONY_EMBEDDINGS_URL=http://localhost:8080
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

## 5. llama-swap y Qdrant

El instalador detecta cada servicio de forma independiente. Ninguno de los dos requiere Docker.

### llama-swap (modelos de chat y embeddings)

Si `llama-swap` ya está ejecutándose en `http://localhost:8080`, Tony-AI reutiliza esa instancia.

Verificación:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/v1/models
```

Si es necesario iniciarlo manualmente:

```bash
llama-swap --config ~/.tony-ai/llama-swap/config.yaml --listen localhost:8080
```

### Qdrant nativo

```bash
qdrant
```

(o el binario que hayas declarado en `TONY_QDRANT_BIN`). `setup.sh` lo autoarranca en background si está disponible y no responde todavía.

Verificación:

```bash
curl http://localhost:6333/readyz
```

## 6. GGA

GGA es parte del entorno requerido por el proyecto. Verifique:

```bash
gga --version
```

`setup.sh` intenta instalarlo automáticamente si `gga` no está en `PATH`. Para instalaciones manuales, asegúrese de que el ejecutable quede disponible en `PATH`, normalmente mediante `~/.local/bin`.

## 7. Troubleshooting

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

### llama-swap no responde

```bash
curl http://localhost:8080/health
```

Si es necesario iniciarlo manualmente:

```bash
llama-swap --config ~/.tony-ai/llama-swap/config.yaml --listen localhost:8080
```

### Qdrant no responde

```bash
curl http://localhost:6333/readyz
qdrant   # o el binario declarado en TONY_QDRANT_BIN
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
bun run tests/validate_config.verify.ts
```

El instalador regenera las rutas MCP utilizando `TONY_REPO_ROOT`.

### El health check falla aunque `make test` pasa

Esto es posible y no implica necesariamente un fallo del código. `make test` valida la suite local sin servicios externos; `make health` valida además llama-swap, Qdrant, MCP y embeddings reales. Revise primero:

```bash
curl http://localhost:8080/health
curl http://localhost:6333/readyz
```

## Documentación
[README.md](README.md) — qué es Tony-AI, propuesta de valor, quickstart y visión general.   
[INSTALL.md](INSTALL.md) — instalación y configuración del entorno.  
[ARCHITECTURE.md](ARCHITECTURE.md) — componentes, responsabilidades, flujos, contratos y persistencia.  
[AGENTS.md](AGENTS.md) — reglas operativas para agentes y desarrollo.  
[TESTING.md](TESTING.md) — estrategia, comandos y cobertura de pruebas.  
