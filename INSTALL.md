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
10. valida que `.env` tiene todas las variables obligatorias y que los URLs/rutas son accesibles.
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
TONY_REPO_ROOT=/path/to/tony-ai          # → reemplazado con ruta real
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

El instalador regenera las rutas MCP utilizando `TONY_REPO_ROOT`.

### El health check falla aunque `make test` pasa

Esto es posible y no implica necesariamente un fallo del código. `make test` valida la suite local sin servicios externos; `make health` valida además Ollama, Qdrant, MCP y embeddings reales. Revise primero:

```bash
curl http://localhost:11434/api/tags
curl http://localhost:6333/readyz
docker compose -f docker/docker-compose.yml ps
```

## Documentación
[INSTALL.md](INSTALL.md) — instalación y configuración detallada.  
[ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura interna y componentes.  
[AGENTS.md](AGENTS.md) — define las reglas de comportamiento y desarrollo que deben seguir los agentes.  
[TESTING.md](TESTING.md) — es la guía oficial de estrategia y ejecución de pruebas.