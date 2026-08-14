# Tony-AI
`Tony-AI` es un sistema de orquestación de agentes de IA para desarrollo de software basado en Spec-Driven Development (SDD), que utiliza múltiples LLMs locales y memoria persistente para planificar, implementar, revisar y reutilizar conocimiento operativo de los cambios realizados.  
Combina tres subsistemas principales:   

* `local-memory/` — memoria persistente y duradera basada en SQLite.
* `code-index/` — indexación y búsqueda semántica del código mediante Ollama + Qdrant.
* `judgment-memory/` — almacenamiento y recuperación de decisiones, revisiones y juicios previos para reutilizar conocimiento durante futuras tareas.

Los servicios definidos en `docker/` proporcionan la infraestructura local para Ollama y Qdrant cuando estos servicios no están disponibles en el host.   

## ¿Cómo funciona?
`Tony-AI` orquesta el desarrollo de software mediante un flujo de trabajo basado en **Spec-Driven Development (SDD)**. El proceso separa la planificación de la implementación, la revisión, la verificación y el archivado, y utiliza agentes especializados para cada etapa.

El flujo general es:
**exploración → propuesta → spec → diseño → tareas → implementación → revisión → verificación → archivado**

**Tony Kernel** actúa como capa de control del flujo. Intercepta las transiciones entre fases y valida que cada etapa haya producido los artifacts y la evidencia necesarios antes de permitir avanzar.  

Entre sus controles se incluyen la validación de artifacts, verificación de checksums, scope guard y comprobaciones de evidencia.   
Si una condición obligatoria falla, la transición se bloquea y se informa el motivo exacto.

## Flujo de agentes
El trabajo comienza con el **Planning Engine**, que analiza el pedido y construye el contexto necesario para trabajar sobre el repositorio. A partir de esa planificación, el agente de **Implementation** realiza los cambios correspondientes.

Después de implementar, `Tony-AI` puede ejecutar una **Revisión 4R** para analizar los cambios y, cuando se solicita explícitamente un juicio, activar **Judgment Day**. Judgment Day recupera juicios anteriores relevantes antes de evaluar el cambio y registra el resultado una vez finalizado el juicio.

Finalmente, **Verify** ejecuta las verificaciones definidas por el flujo SDD. Cuando la implementación supera las validaciones requeridas, el proceso puede pasar a **Archive**, donde se consolida el estado final del trabajo.
```mermaid
flowchart LR
    U["Pedido / Proyecto"]
    P["Planning<br/>Qwen3-Coder 30B"]
    I["Implementation<br/>OmniCoder 2 9B"]
    R["Review 4R<br/>DeepSeek-R1 14B"]
    V["Verify<br/>sdd-verify"]
    A["Archive<br/>Ornith 9B"]

    U --> P --> I --> R --> V --> A

    I -.-> JD["Judgment Day<br/>DeepSeek-R1 + Qwen3-Coder"]
    JD --> V

    JDM["Judgment Memory<br/>jd_recall"] -.-> JD
    JD -.-> JDR["jd_record<br/>ledger + Qdrant"]
```

## Contexto y memoria
Tony-AI separa la orquestación del workflow de los sistemas que aportan contexto y memoria.

```text
                         OpenCode
                            │
                   Tony Orchestrator
                    │       │       │
                    │       │       └── Judgment Memory
                    │       └────────── Code Index
                    └────────────────── TonyMem
                            │
                           DCP
                            │
                         SDD phase
                            │
                       Tony Kernel
```

- **TonyMem** aporta decisiones, descubrimientos y contexto persistente.
- **Code Index** aporta conocimiento semántico sobre el código.
- **Judgment Memory** aporta juicios y lecciones de revisiones anteriores.
- **DCP** administra el contexto utilizado por OpenCode.
- **Tony Kernel** no decide qué trabajo hacer: controla si una transición de fase está permitida.

El objetivo no es entrenar los modelos, sino conservar, indexar y recuperar conocimiento operativo para reutilizarlo en tareas posteriores.

```text
Nueva tarea
    │
    ├── TonyMem ──────────────► decisiones y contexto previo
    ├── Code Index ───────────► código relacionado
    ├── Judgment Memory ──────► revisiones y lecciones previas
    └── DCP ──────────────────► contexto relevante
                                      │
                                      ▼
                               Agente / Orchestrator
                                      │
                                      ▼
                                 SDD Phase
                                      │
                                      ▼
                                 Tony Kernel
```
							   
## Kernel
Si algo falla, el Kernel te dice exactamente por qué:

- **Artifacts faltantes o con hash inválido** → volvé a generar el artifact de la fase actual
- **Diff fuera de allowed_files** → revisá el scope en `openspec/change-request.md`
- **Salto de fase** → completá la fase anterior antes de avanzar
```mermaid
flowchart TB
    K["Tony Kernel<br/>Phase Gate · Scope Guard · Artifacts · Checksums · Evidence"]

    subgraph WF["SDD Workflow"]
        direction LR
        P["Planning"]
        I["Implementation"]
        R["Review 4R"]
        V["Verify"]
        A["Archive"]

        P --> I --> R --> V --> A
        I -.-> JD["Judgment Day"]
        JD --> V
    end

    K -.->|"gobierna transiciones"| WF
```
El Kernel comprueba que el cambio esté en condiciones de avanzar antes de permitir la siguiente fase.   
Entre otras cosas, controla: artifacts requeridos; checksums; alcance permitido de los cambios; evidencias; estado de la fase; transiciones válidas.   
Esto permite que el workflow no dependa únicamente de que un agente "recuerde" qué debe hacer: las condiciones críticas del proceso son verificadas por una capa de control.
	
## Arquitectura
                         ┌──────────────────────────┐
                         │        OpenCode          │
                         │   Agent Orchestrator     │
                         │          + SDD           │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │       Tony Kernel        │
                         │                          │
                         │ Phase Gate · Scope Guard │
                         │ Artifacts · Checksums    │
                         │ Evidence · Transitions   │
                         └────────────┬─────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
                 ▼                    ▼                    ▼
        ┌────────────────┐   ┌────────────────┐   ┌──────────────────┐
        │ local-memory   │   │   code-index   │   │ judgment-memory  │
        │                │   │                │   │                  │
        │ Memoria        │   │ Búsqueda       │   │ Memoria de       │
        │ persistente    │   │ semántica      │   │ juicios          │
        │ SQLite         │   │ del código     │   │                  │
        └───────┬────────┘   └───────┬────────┘   └────────┬─────────┘
                │                    │                     │
                ▼                    ▼                     ▼
        ┌──────────────┐      ┌────────────────┐    ┌────────────────┐
        │    SQLite    │      │ Ollama +       │    │ SQLite +       │
        │              │      │ Qdrant         │    │ Qdrant         │
        │ decisiones + │      │ embeddings +   │    │ ledger +       │
        │ contexto     │      │ vector search  │    │ recuperación   │
        └──────────────┘      └────────────────┘    └────────────────┘
Para una descripción más profunda de los componentes y sus interfaces, consultá [ARCHITECTURE.md](ARCHITECTURE.md)

# Requisitos
- **Python 3.10+** — servidores MCP y tooling Python.
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
python3 --version
python3 -m pip --version
```
- **Bun** — scripts TypeScript y plugins.
```bash
sudo apt update && sudo apt install -y unzip curl && curl -fsSL https://bun.sh/install | bash
source ~/.bashrc
bun --version
```
- **OpenCode CLI** — orquestador SDD.
```bash
curl -fsSL https://opencode.ai/install | bash
source ~/.bashrc
opencode --version
```
- **Ollama** — ejecución de LLM locales.
```bash
sudo apt-get install zstd
curl -fsSL https://ollama.com/install.sh | sh
source ~/.bashrc
ollama --version
curl http://localhost:11434/api/tags
```
- **Docker + Docker Compose** — infraestructura de servicios, incluido Qdrant.
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker --version
docker compose version
```
- **GGA (Gentleman Guardian Angel)** — code review. 
Se instala automáticamente desde `scripts/setup.sh`
- **tree-sitter** — chunking estructural del Code Indexer.  
- **tree-sitter-language-pack** — grammars utilizadas por el Code Indexer.

## Modelos locales por defecto

| Función | Modelo |
|---|---|
| Planning / propuesta | `qwen3-coder:30b` |
| Implementación | `carstenuhlig/omnicoder-2-9b:q4_k_m` |
| Review / Judgment | `deepseek-r1:14b` |
| Archive / jd-fix-agent | `ornith:9b` |
| Code embeddings | `bge-m3` |
| Judgment embeddings | `nomic-embed-text` |

Los modelos se ejecutan localmente mediante Ollama.

# Instalación

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
git checkout dev
./scripts/setup.sh
```
Valida las dependencias, instala `requirements-dev.txt`, tree-sitter, levanta los servicios Docker, descarga todos los modelos, genera `.env.example` y configuración de OpenCode.

Después:

```bash
./scripts/health.sh
```
Es el chequeo de salud end-to-end de `Tony-AI`. No instala ni configura cosas: verifica que el sistema ya configurado funcione.

Para la instalación detallada, consultá [INSTALL.md](INSTALL.md).

# Cómo empezar con Tony-AI
```bash
# 1. Inicializá el proyecto (una sola vez)
/sdd-init
```

```bash
# 2. Creá un cambio nuevo
/sdd-new "agregar rate limiting al endpoint de login"

El orquestador hace el trabajo pesado: explora el código, arma una propuesta, genera la spec, el diseño y las tareas. Podés intervenir en cualquier momento:

/sdd-explore "chequear si hay middleware de auth existente"
/sdd-propose   # ajustar la propuesta si hace falta
/sdd-design    # modificar el diseño antes de implementar
```

```bash
# 3. Implementar y verificar
/sdd-apply                    # implementá las tareas
/sdd-verify                   # validá contra las specs
/sdd-archive                  # cerrá el cambio
```

```bash
# 4. Consultá memoria en cualquier momento
/memory-search "rate limiting"
/memory-stats
/judgment-history
/kernel-status                # estado actual del Kernel (fase, artifacts, checksums)
```

```bash
# 5. Qué ocurre si algo falla

El Kernel bloquea la transición y señala la condición que impide avanzar.

Por ejemplo:

- Artifacts faltantes → completar o regenerar el artifact.
- Diff fuera de `allowed_files` → revisar el scope.
- Salto de fase → completar la fase anterior.
```

```bash
# 6. Iterar sobre un cambio existente
Para retomar un cambio anterior:

/sdd-load <change-id>          # retomá un cambio anterior
/sdd-apply                     # seguí con las tareas pendientes
/sdd-verify                    # re-validá si tocaste specs
/sdd-archive                   # cerrá la nueva iteración
```

```bash
# 7. Activar Judgment Day

`juzgar esto` recupera juicios anteriores relevantes, ejecuta los dos jueces configurados y registra el resultado en Judgment Memory para futuras revisiones.

Actualmente la configuración incluye:
- `jd-judge-a`
- `jd-judge-b`
```

```bash
# 8. Memoria de prompts
TonyMem también puede capturar prompts mediante el hook chat.message de tonymem.ts.

Estas entradas se almacenan con:

type='prompt-capture'

Los prompts capturados se utilizan para reconstruir contexto de la sesión, pero se excluyen de las búsquedas normales de mem_search, ya que son bookkeeping y no decisiones o descubrimientos.

- Llamado por el hook `chat.message` en `tonymem.ts`
- Captura prompts crudos con `type='prompt-capture'`
- Excluido de búsquedas por defecto (bookkeeping)
- Se puede filtrar explícitamente si necesitás revisar prompts

Estas entradas se usan para `mem_context` (recuperar el contexto de la sesión actual) pero **se excluyen por defecto de `mem_search`** — no son decisiones ni descubrimientos, son bookkeeping interno. Si necesitás buscar prompts, filtrá explícitamente por `type='prompt-capture'`.
```

```bash
# 9. TonyMem - Memoria Persistente
`local-memory/` mantiene decisiones, descubrimientos y contexto persistente entre sesiones.

## Cada decisión/descubrimiento se guarda en SQLite
mem_save(
  task="manejo retry HTTP",
  observation="usar exponential backoff"
)

# Luego se recupera en nuevas conversaciones
mem_search("retry HTTP") → encuentra la decisión guardada

Reutiliza: Decisiones arquitectónicas, bugs resueltos, patrones de código
```

```bash
# 10. Judgment Memory - Lecciones de Revisiones

# Después de cada Judgment Day:
jd_record(task="validar JWT", final="approve", lesson="siempre verificar signature expiration")
# Futuras tareas similares recuerdan esta lección

Reutiliza: Errores de review, mejores prácticas validadas
```

```bash
# 11. Code Indexer - Conocimiento del Codebase
- Indexa incrementalmente (solo cambios)
- Embeddings semánticos con bge-m3
- Búsquedas como "cómo se maneja la autenticación" te encuentran código relevante

Representa: Crecimiento del codebase, patrones emergentes
```

```bash
# 12. Hooks de OpenCode (tonymem.ts)
// Hook que captura automáticamente lo que haces
"chat.message" → mem_save_prompt() // guarda prompts
"task.execute.after" → guarda discoveries importantes
```

```bash
# 13. Cómo funciona el aprendizaje en práctica:
Usuario: "Implementa login con refresh token"

1. `/sdd-new` → delega `sdd-explore` + `sdd-propose` a sub-agentes
2. `mem_search()` → encuentra decisión previa sobre JWT
3. `code_search()` → encuentra cómo funciona auth actual
4. `jd_recall()` → recuerda lección sobre token expiration
5. `/sdd-tasks` → genera plan de implementación
6. `/sdd-apply` → implementa las tareas
7. `/sdd-verify` → valida contra specs
8. `/sdd-archive` → cierra el cambio, guarda `archive-report`
9. `juzgar esto` → dos jueces review + lesson guardada en `jd_record`
```

```bash
# 14. Cómo se reutiliza el conocimiento

Un flujo típico puede verse así:

Usuario
  │
  │ "Implementa login con refresh token"
  ▼
/sdd-new
  │
  ├── sdd-explore
  ├── sdd-propose
  │
  ├── mem_search()
  │      └── recupera decisiones previas
  │
  ├── code_search()
  │      └── encuentra código relacionado
  │
  ├── jd_recall()
  │      └── recupera lecciones de revisiones anteriores
  │
  ├── sdd-tasks
  │
  ├── sdd-apply
  │
  ├── sdd-verify
  │
  ├── sdd-archive
  │
  └── juzgar esto
         │
         ├── jueces
         └── jd_record()
               └── nueva lección para futuras revisiones

La diferencia fundamental es que el conocimiento generado durante el trabajo no desaparece al terminar la sesión.

Tony-AI conserva decisiones, descubrimientos, contexto, conocimiento, semántico del código, resultados de revisiones, lecciones de Judgment Day.

Ese conocimiento puede recuperarse posteriormente para informar nuevas tareas.
```
## Comandos
| Comando | Descripción | Fuente | Offline |
|---------|-------------|--------|---------|
| `/sdd-init` | Inicializar contexto SDD | SQLite + config | ✅ |
| `/sdd-new <change>` | Nuevo cambio con SDD completo | Sub-agentes planning | ❌ |
| `/sdd-explore <task>` | Investigar una idea | Sub-agente explore | ❌ |
| `/sdd-propose` | Crear propuesta PRD | Sub-agente propose | ❌ |
| `/sdd-spec` | Especificación técnica | Sub-agente spec | ❌ |
| `/sdd-design` | Diseño técnico | Sub-agente design | ❌ |
| `/sdd-tasks` | Generar plan de tareas | Sub-agente tasks | ❌ |
| `/sdd-apply [change]` | Implementar tareas | Sub-agente writer | ❌ |
| `/sdd-verify [change]` | Validar implementación | Sub-agente verify | ❌ |
| `/sdd-archive [change]` | Cerrar cambio y archivar | SQLite/JSON | ✅ |
| `/sdd-onboard` | Walkthrough guiado de SDD | Sub-agente onboard | ❌ |
| `/sdd-status [change]` | Ver estado del cambio | Artifact store | ✅ |
| `/sdd-continue [change]` | Ejecutar siguiente fase | Sub-agentes | ❌ |
| `/sdd-ff <name>` | Fast-forward: propuesta → tareas | Sub-agentes planning | ❌ |
| `/memory-search "query"` | Búsqueda semántica en TonyMem + Judgment Memory | SQLite + Qdrant | ✅ / ❌ |
| `/memory-stats` | Estadísticas de memoria | SQLite | ✅ |
| `/judgment-history [project]` | Ver historial de juicios | SQLite ledger | ✅ |
| `juzgar esto` | Activar Judgment Day | 2 jueces + memoria | ❌ |
| `/kernel-status` | Estado del Kernel (fase actual, artifacts, checksums) | kernel-state.json | ✅ |
| `/kernel-reset` | Resetear estado del Kernel (solo desarrollo) | kernel-state.json | ✅ |

💡 Todo funciona offline excepto los comandos que requieren sub-agentes (`/sdd-new`, `/sdd-explore`, `/sdd-propose`, `/sdd-spec`, `/sdd-design`, `/sdd-tasks`, `/sdd-apply`, `/sdd-verify`, `/sdd-onboard`, `/sdd-continue`, `/sdd-ff`, `juzgar esto`) y búsqueda semántica (`/memory-search` con Qdrant/Ollama).

## Testing
Tony-AI separa las pruebas de código de las verificaciones que requieren infraestructura externa.
La suite local **no necesita Ollama, Qdrant ni Docker**. Esto permite ejecutar la mayoría de las pruebas incluso en un entorno sin los servicios de IA configurados.
- **Python + pytest** para desarrollo y CI.
- **Runner Python standalone** (`tools/run-python-tests.py`) sin dependencias externas.
- **Bun** para los tests TypeScript.
- **Validación directa de configuración y prompts SDD**.
- **Tests focalizados del Tony Kernel**.
- **Tests de integración del plugin Judgment Memory**.

La ejecución recomendada es:
```bash
python3 -m pip install -r requirements-dev.txt
make test
```
También pueden ejecutarse las suites individualmente:
```bash
make test-python
make test-ts
make test-kernel
```

Para ejecutar Python sin pytest:
```bash
python3 tools/run-python-tests.py tests
```

## Categorías de tests
Los tests Python pueden filtrarse por categoría:
```bash
python3 -m pytest -m concurrency
python3 -m pytest -m mcp
python3 -m pytest -m "not concurrency"
```

## Code Review automático
`GGA` valida los archivos staged contra tu `AGENTS.md` antes de cada commit, usando OpenCode como proveedor de IA.
El repo ya incluye `.gga` (config) y el agente `gga-reviewer` en `opencode.json`. Solo falta instalar el hook:
```bash
gga install          # crea .git/hooks/pre-commit (local, no se commitea)
gga config           # verificar configuración
gga run              # revisar archivos staged
gga run --pr-mode    # revisar todos los cambios del PR vs main
gga run --no-cache   # ignorar cache y revisar todo
```

## Documentación
[INSTALL.md](INSTALL.md) — instalación y configuración detallada.  
[ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura interna y componentes.  
[AGENTS.md](AGENTS.md) — define las reglas de comportamiento y desarrollo que deben seguir los agentes que trabajan sobre `Tony-AI`.  
[TESTING.md](TESTING.md) — es la guía oficial de estrategia y ejecución de pruebas de `Tony-AI`.  

## Estado del proyecto
`Tony-AI` está diseñado para ejecutarse localmente, manteniendo los modelos, memoria y datos semánticos bajo control del entorno del desarrollador.

El objetivo no es solamente generar código con LLMs, sino proporcionar un workflow de desarrollo verificable, persistente y basado en especificaciones, donde los agentes pueden reutilizar el conocimiento acumulado del proyecto y donde el Kernel controla las condiciones necesarias para avanzar entre fases.

## Agradecimientos
Algunos conceptos de SDD, orquestador, prompts, skills y comandos se basan en el repositorio de github `gentle-ai` de Alan Buscaglia (`The Gentleman`), a quien agradecemos por su contenido y aportes a la comunidad.
