# Tony-AI

Tony-AI es un sistema de orquestación de agentes de IA para desarrollo de software basado en SDD (Spec-Driven Development), con memoria persistente, búsqueda semántica de código y Judgment Memory usando modelos locales.

## Requisitos obligatorios

La instalación soportada requiere **todos** estos componentes:

- **Python 3.10+** — servidores MCP y tooling Python.
- **Bun** — scripts TypeScript y plugins.
- **OpenCode CLI** — orquestador SDD.
- **Ollama** — ejecución de LLM locales.
- **Docker + Docker Compose** — infraestructura de servicios, incluido Qdrant.
- **GGA (Gentleman Guardian Angel)** — code review obligatorio.
- **tree-sitter + tree-sitter-languages** — chunking estructural obligatorio del Code Indexer.

No hay dependencias opcionales en el bootstrap oficial: `scripts/setup.sh` falla si falta cualquiera de estos requisitos.

## Modelos por defecto

| Función | Modelo |
|---|---|
| Planning / propuesta | `qwen3-coder:30b` |
| Implementación | `carstenuhlig/omnicoder-2-9b:q4_k_m` |
| Review / Judgment | `deepseek-r1:14b` |
| Archive / jd-fix-agent | `ornith:9b` |
| Code embeddings | `bge-m3` |
| Judgment embeddings | `nomic-embed-text` |

## Instalación

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
git checkout dev
./scripts/setup.sh
```

El bootstrap valida las dependencias, instala `requirements-dev.txt` incluyendo tree-sitter, levanta únicamente los servicios Docker que falten, descarga todos los modelos y genera `.env.example` y una configuración portable de OpenCode.

Después:

```bash
./scripts/health.sh
make test
```

Para la instalación detallada, consultá [INSTALL.md](INSTALL.md).

## Arquitectura

```text
                         ┌──────────────────────┐
                         │     OpenCode / SDD   │
                         │     Orquestador      │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │    Tony Kernel       │
                         │ Phase Gate / Scope   │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
       ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
       │  TonyMem     │      │ Code Index   │      │ Judgment Mem │
       │ SQLite       │      │ tree-sitter  │      │ SQLite/Qdrant│
       └──────────────┘      │ Ollama/Qdrant│      └──────────────┘
                             └──────────────┘
```

El Code Indexer usa **tree-sitter obligatoriamente** para dividir el código respetando estructuras sintácticas como funciones, clases y métodos antes de generar embeddings. El bootstrap oficial ya no usa `regex` como chunker.

## Flujo SDD

1. Explorar
2. Proponer
3. Especificar
4. Diseñar
5. Crear tareas
6. Aplicar
7. Verificar
8. Archivar

El Kernel valida artifacts, checksums, scope y evidencias antes de permitir avanzar de fase.

## Servicios

Ollama puede ejecutarse de forma nativa o mediante Docker, pero debe responder en `http://localhost:11434`. Qdrant debe responder en `http://localhost:6333`.

El bootstrap detecta cada servicio independientemente para evitar el conflicto de puerto cuando Ollama ya está instalado en el host y Qdrant corre en Docker.

## Configuración

`.env.example` contiene la configuración canónica:

```env
TONY_REPO_ROOT=/path/to/tony-ai
TONY_OLLAMA_URL=http://localhost:11434
TONY_QDRANT_URL=http://localhost:6333
JUDGMENT_EMBED_MODEL=nomic-embed-text
CODE_EMBED_MODEL=bge-m3
TONY_IMPLEMENTATION_MODEL=carstenuhlig/omnicoder-2-9b:q4_k_m
TONY_INDEX_CHUNKER=tree-sitter
```

## Tests

```bash
make test
pytest tests
python3 tools/run-python-tests.py tests
```

`tests/test_setup.py` comprueba sintaxis del bootstrap, requisitos obligatorios, tree-sitter, modelo OmniCoder 2, configuración de OpenCode y `.env.example`.

## Comandos principales

```text
/sdd-init
/sdd-new "descripción del cambio"
/sdd-explore
/sdd-propose
/sdd-spec
/sdd-design
/sdd-tasks
/sdd-apply
/sdd-verify
/sdd-archive
/memory-search "query"
/memory-stats
/judgment-history
juzgar esto
```

## Code Review

GGA valida los cambios staged contra `AGENTS.md`. Es un requisito del entorno de desarrollo de Tony-AI, no una herramienta opcional del bootstrap.
