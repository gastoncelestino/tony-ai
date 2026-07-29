# Judgment Day Memory Bridge — Resumen Ejecutivo

**Qué es**: Judgment Day (la revisión dual con dos jueces ciegos de Tony-AI)
antes no tenía memoria — cada vez que juzgaba un target, empezaba de cero,
aunque ya se hubiera visto un problema parecido antes. Este bridge lo
conecta con TonyMem y Qdrant para que:

1. **Antes de juzgar**, se busque si ya se vio algo parecido ("¿ya vimos
   este problema?").
2. **Después de juzgar**, el resultado se guarde para la próxima vez.

```
Nueva tarea → Recall (TonyMem/Qdrant) → Judgment Day → Ledger + Qdrant → Recall futuro
```

## Qué se construyó

| Pieza | Qué hace |
|---|---|
| `judgment-memory/ledger.py` | Guarda cada juicio en una base SQLite propia y lo indexa en Qdrant para búsqueda semántica. |
| `judgment-memory/server.py` | Expone 4 herramientas al agente: `jd_recall` (buscar), `jd_record` (guardar), `jd_history` (listar), `jd_stats` (estadísticas). |
| `plugins/qdrant.ts` + `plugins/judgment-memory.ts` | Conectan Judgment Day con esa memoria dentro de OpenCode: buscan antes de juzgar, guardan después. |
| `skills/judgment-day/SKILL.md` | Recibió 2 líneas de diff (no se tocó el mecanismo) para pedir `jd_recall` al inicio y `jd_record` al final. |
| `commands/memory-search.md`, `memory-stats.md`, `judgment-history.md` | Comandos `/` para consultar la memoria a mano. |
| `docker/` | Ollama (embeddings) + Qdrant (vectores) en contenedor, listo para NixOS (Docker o Podman, GPU opcional). |
| `Makefile` | Atajos: `make up`, `make down`, `make verify`. |

## Cómo usarlo

**Instalación completa**: `TONY-AI-INSTALL.md`, sección 10 (paso a paso,
copy-paste). Resumen rápido:

```bash
cd docker && docker compose up -d      # levanta Ollama + Qdrant
make verify                            # corre los tests
```

Después, dentro de una sesión de OpenCode, no hay que hacer nada especial:
al decir *"juzgar esto: \<target\>"* el sistema busca contexto previo solo,
y al terminar el juicio lo guarda solo. Para consultar la memoria a mano:

```
/memory-search "oracle performance"
/judgment-history
/memory-stats
```

## Qué tan probado está

| Pieza | Estado |
|---|---|
| Ledger SQLite + pipeline completo (embed→Qdrant→recall) | ✅ Probado con test automatizado (`test_ledger.py`, 7/7 escenarios, incluyendo fallas de red controladas) |
| Servidor MCP (protocolo) | ✅ Probado con una sesión real |
| Cliente TS/Bun (`qdrant.ts`) | ⚠️ Escrito y tipado, con un smoke test listo (`scripts/verify-qdrant.ts`) — falta que alguien lo corra contra Ollama/Qdrant reales (yo no tengo esos servicios acá) |
| Plugin de OpenCode (hooks) | ⚠️ Sin probar en una sesión real — es lo único que solo se valida usándolo |
| `docker-compose.yml` | ⚠️ Sintaxis válida, pero nunca levantado de verdad (sin acceso a Docker en este entorno) |

**En criollo**: la lógica central (guardar, buscar, no duplicar, degradar
bien si algo está caído) está probada de verdad. Lo que falta es la última
milla — correrlo una vez en tu máquina real para confirmar que Docker,
Ollama y el plugin dentro de OpenCode se hablan entre sí como se espera.

## Siguiente paso sugerido

1. `docker compose up -d` en tu NixOS.
2. `make verify` (o los dos comandos por separado si preferís verlos
   separados: `python3 judgment-memory/test_ledger.py` y
   `bun run judgment-memory/scripts/verify-qdrant.ts`).
3. Un Judgment Day real de punta a punta, y confirmar en la transcripción
   que aparecen las llamadas a `jd_recall`/`jd_record`.

Documentación completa: `README.md` (visión general), `ARCHITECTURE.md`
(por qué cada decisión), `TONY-AI-INSTALL.md` (instalación paso a paso),
`docker/README.md` (notas NixOS), `judgment-memory/README.md` (referencia
técnica de esta pieza en particular).
