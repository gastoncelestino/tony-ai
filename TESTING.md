# Tony-AI — Testing

## Estrategia general
```text
                    Tony-AI Testing
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
    Python tests      TypeScript tests   Configuración
    (deterministas)   (deterministas)    (estructura)
        │                 │                   │
     pytest          Bun + tree-sitter   validate-config
     + runner        + real plugins       + opencode.json
     standalone
        │
    Sin Pytest
    (solo stdlib)
        │
        └─── Fallback para CI aislada
        
        ┌──────────────────────────────┐
        │   Smoke tests (separados)    │
        │   Ollama + Qdrant (opcional) │
        │   make verify-qdrant         │
        │   make health                │
        └──────────────────────────────┘
```
## 1. Qué necesito
### Requisitos mínimos
- **Python 3.10+** (CI testea 3.10, 3.11, 3.12)
- **Bun 1.3.14** (o compatible en local)
- **make** (Makefile)

### Instalación
**Setup completo**
```bash
./scripts/setup.sh
```

### Verificar instalación
```bash
python3 --version        		# 3.10+
bun --version            		# 1.3.14+
python3 -m pytest --version		# pytest x.x.x
make --version					# GNU Make x.x.x
```

### Verificar pytest
```bash
# Ver si pytest está disponible
make check-test-deps			# pytest x.x.x
```
---

## 2. ¿Qué comando usar?
| Feature | Ejecutar | Verifica | Necesita |
|-----------|----------|------|------|
| Setup Completo | `make bootstrap` | Validación Proyecto | No necesita Bun |
| Suite completa + infraestructura | `make test-all` | `test` + `test-kernel` + `health` | Bun + Ollama + Qdrant |
| Feature/bugfix normal | `make test` | Python + TypeScript + config | Bun |
| Solo Python | `make test-python` | Solo tests Python | Bun |
| Solo TypeScript | `make test-ts` | Solo tests TypeScript | Bun |
| Health check | `make health` | Health check infraestructura | Ollama, Qdrant |
| Indexación real Ollama + Qdrant | `make verify-qdrant` | verifica Qdrant | Ollama, Qdrant |
| Kernel | `make test-kernel` | Kernel + SDD + TypeScript kernel | Bun |
| Verificar SDD E2E | `make verify-sdd-flow` | Flujo E2E SDD local | No necesita Bun |
| Valida naming conventions | `make check-test-discovery` | Validación Discovery | No necesita Bun |
| Python coverage | `make coverage-python` | Coverage Python (40% threshold) | Bun |
| TypeScript coverage | `make coverage-ts` | Coverage TypeScript | Bun |
| Cobertura completa Python + TS | `make coverage` | Coverage Python + TypeScript | Bun |
| Configuración | `make validate-config` | Valida `opencode.json`, prompts, agentes, MCP y referencias | Bun |
---

## 3. Cómo ejecutar tests

### Ejecutar directamente (diagnóstico)

```bash
# Python con pytest
python3 -m pytest tests -v
```
```bash
# Python con runner standalone (sin pytest)
python3 tests/python_verify.py tests
```

El runner standalone usa solo stdlib. Si pytest pasó pero standalone no, significa el test depende de algo no instalable sin pip. Usar pytest en ese caso.

```bash
# TypeScript
bun test tests
```

```bash
# Validación de config
bun run tests/validate_config.verify.ts
```
Validación de `opencode.json`, prompts, agentes, MCP y referencias de archivos.

### Tests específicos

**Python:**
```bash
python3 -m pytest tests/test_kernel_state_machine.py -v
python3 -m pytest tests/test_sdd_flow_e2e.py -v
python3 -m pytest tests/test_code_index_core.py -v
```

**TypeScript:**
```bash
bun test tests/tony_kernel_hooks.test.ts
bun test tests/judgment_memory_hooks.test.ts
```

### Tests por categoría (markers)

```bash
python3 -m pytest -m concurrency    # Escenarios de concurrencia
python3 -m pytest -m mcp            # Contrato MCP JSON-RPC
python3 -m pytest -m "not concurrency"
```

## 4. Antes de hacer `commit`, `push` a rama local, a `main` o `dev`

```bash
make test # verifica suite local completa
```

Verifica que tu código NO rompió nada en la suite local (Python + TypeScript + config).

**Si `make test` falla, NO hagas commit. Arreglá el problema primero.**


## Documentación
[README.md](README.md) — qué es Tony-AI, propuesta de valor, quickstart y visión general.   
[INSTALL.md](INSTALL.md) — instalación y configuración del entorno.  
[ARCHITECTURE.md](ARCHITECTURE.md) — componentes, responsabilidades, flujos, contratos y persistencia.  
[AGENTS.md](AGENTS.md) — reglas operativas para agentes y desarrollo.  
[TESTING.md](TESTING.md) — estrategia, comandos y cobertura de pruebas.  
