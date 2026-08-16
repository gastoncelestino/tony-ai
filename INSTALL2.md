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
| Docker + Compose | Qdrant y Ollama | Instalador/runtime |
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

1. verifica Python 3.10+, Bun, OpenCode CLI, Docker y Ollama;
2. verifica GGA y, si no está instalado, intenta clonarlo e instalarlo en un directorio temporal;
3. comprueba por separado la disponibilidad de Ollama y Qdrant;
4. inicia mediante Docker solamente el servicio de soporte que falte;
5. descarga los modelos locales requeridos;
6. instala `requirements-dev.txt` y verifica `tree_sitter` y `tree_sitter_language_pack`;
7. regenera `opencode.json` con `TONY_REPO_ROOT` y fuerza `TONY_INDEX_CHUNKER=tree-sitter`;
8. verifica que `.env.example` existe en el repositorio (no lo modifica);
9. crea `.env` copiando desde `.env.example` (si no existe ya);
10. valida que `.env` tiene todas las variables obligatorias y que los URLs/rutas son accesibles;
11. crea `opencode.json.bak` antes de modificar la configuración.

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

`.env.example` es estático y se entrega con el repositorio.
El instalador `setup.sh` verifica su existencia y automáticamente crea `.env` copiando la configuración y reemplazando las rutas reales del sistema.

```env
TONY_REPO_ROOT=/path/to/tony-ai
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

El instalador detecta cada servicio de forma independiente.

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

`setup.sh` intenta instalarlo automáticamente si `gga` no está en `PATH`.

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

### Docker no responde

```bash
docker info
docker compose version
```

### Ollama no responde

```bash
curl http://localhost:11434/api/tags
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

```bash
./scripts/setup.sh
bun run tools/validate-config.ts
```

El instalador regenera las rutas MCP utilizando `TONY_REPO_ROOT`.

### El health check falla aunque `make test` pasa

Esto es posible y no implica necesariamente un fallo del código. `make test` valida la suite local sin servicios externos; `make health` valida además Ollama, Qdrant, MCP y embeddings reales.

## Fuentes de verdad

- `INSTALL2.md` describe el procedimiento de instalación y configuración.
- `scripts/setup.sh` es la fuente de verdad para el comportamiento real del instalador.
- `scripts/health.sh` es la fuente de verdad para el health check.
- `README.md` es la fuente de verdad para el quickstart general.
- `ARCHITECTURE.md` es la fuente de verdad para la arquitectura.
- Código y tests son la fuente definitiva cuando existe una contradicción con la documentación.

## Documentación
[README.md](README.md) — qué es Tony-AI, propuesta de valor, quickstart y visión general.
[INSTALL.md](INSTALL.md) — instalación y configuración del entorno.
[ARCHITECTURE.md](ARCHITECTURE.md) — componentes, responsabilidades, flujos, contratos y persistencia.
[AGENTS.md](AGENTS.md) — reglas operativas para agentes y desarrollo.
[TESTING.md](TESTING.md) — estrategia, comandos y cobertura de pruebas.