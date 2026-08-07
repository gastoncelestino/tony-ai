# Tony-AI - Instalación detallada

# 0. Prerequisitos (lo que tenes que instalar para que funcione)
- **Python 3.10+** para los servidores MCP en Python.
- **Bun** para los scripts de verificación basados en TypeScript y plugins.
- **Docker** si querés los servicios de Qdrant + Ollama.
- **OpenCode CLI** (instalador oficial: https://opencode.ai)
- **Ollama** (https://ollama.com/download)

## Requerido para características semánticas
- **Qdrant** corriendo localmente o remotamente.
- La capa de memoria local funciona sin Ollama ni Qdrant. La búsqueda semántica de código y el recall de juicios requieren ambos servicios.


# 1. Clonar repositorio
```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
```

# 2. Instalación manual o automática
# 2.1 Instalación automática
```bash
./scripts/setup.sh    # Instalar todo automáticamente
./scripts/health.sh   # Verificar estado del sistema
```

## 2.2 setup.sh — Instalador automático:
1. Verifica dependencias (Docker, Ollama, Bun)
2. Descarga modelos faltantes
3. Configura .env
4. Inicia servicios
5. Descarga modelo de embeddings


## 2.3 health.sh — Verificación de salud:
1. Servicios Docker activos
2. Conectividad Ollama/Qdrant
3. Funcionalidad de embeddings
4. Integridad de bases de datos


# 2. Instalación manual (si no hiciste la instalación automática)
## 2.1 Crear la carpeta .opencode en tu perfil de usuario si no existe
```bash
mkdir "$env:USERPROFILE/.opencode"
mkdir "$env:USERPROFILE/.opencode/plugins"
```

## 2.2 Copiar opencode.json
```bash
copy /tony-ai/opencode.json "$env:USERPROFILE/.opencode/opencode.json"
```

## 2.3 Copiar AGENTS.md
```bash
copy /tony-ai/AGENTS.md "$env:USERPROFILE/.opencode/AGENTS.md"
```

## 2.4 Copiar los plugins TypeScript
```bash
copy /tony-ai/plugins/tonymem.ts "$env:USERPROFILE/.opencode/plugins/"
copy /tony-ai/plugins/qdrant.ts "$env:USERPROFILE/.opencode/plugins/"
copy /tony-ai/plugins/judgment-memory.ts "$env:USERPROFILE/.opencode/plugins/"
```

# 3. Deberías ver algo como:
```bash
📄 opencode.json
📄 AGENTS.md
📁 plugins
   📄 tonymem.ts
   📄 qdrant.ts
   📄 judgment-memory.ts
```

# 4. Iniciar Ollama y Qdrant con Docker Compose
```bash
cd docker
cp .env.example .env   # opcional
docker compose up -d  # inicia Qdrant (vector DB) en el puerto 6333 y Ollama en el puerto 11434
docker compose ps   # Verificar servicios
```

```bash
Deberías ver algo como:
```
|     NAME     |    IMAGE     |    COMMAND   |  SERVICE     |     STATUS   |    PORTS     |
|--------------|--------------|--------------|--------------|--------------|--------------|
| tony-ai-qdrant | qdrant/qdrant:latest |  "/bin/qdrant --config…" | qdrant   |  running (healthy) | 0.0.0.0:6333->6333/tcp |
| tony-ai-ollama | ollama/ollama:latest |  "/usr/bin/ollama bind_…" | ollama  |  running (healthy) | 0.0.0.0:11434->11434/tcp |


```bash
docker compose logs -f ollama-pull
```

# 5. Descargar modelos de Ollama
## 5.1 Modelos grandes (descargan lentamente)
```bash
ollama pull qwen3-coder:30b
ollama pull deepseek-r1:14b
```
## 5.2 Modelos medianos
```bash
ollama pull omnicoder:9b
ollama pull ornith:9b
```
## 5.3 Modelos pequeños (rápidos)
```bash
ollama pull bge-m3
ollama pull nomic-embed-text
```

# 6. Correr el suite de tests
## 6.1 Correr tests de Python + TypeScript. 
```bash
make test   # Ejecutar todos los tests
```

```bash
[PASS] chunk_lines handles empty input
[PASS] content_hash produces correct hash
[PASS] embed_texts handles batch
[PASS] qdrant_upsert and search roundtrip via mock
[PASS] point_id deterministic per project+path+start_line
[PASS] collection name sanitization
[PASS] qdrant client methods (embed/upsert/search/delete) via mock server
[PASS] index_repo incremental: unchanged files skipped, changed files re-indexed, deleted files removed
...
[PASS] All test_hooks passed
Total tests: 11
Passed: 11
Failed: 0

ALL ASSERTIONS PASSED

[PASS] test_treesitter_chunking
  tree-sitter chunking produced 4 chunks from nested Python
ALL TESTS PASSED
 ✨  test_core.py (Python)
✅ test_hooks.ts (TypeScript)
```

Si todos los tests pasan (Passed: 11 / All tests passed), entonces tu instalación de Tony-AI está completa y funciona correctamente.

```bash
make verify-qdrant   # probar el pipeline vectorial real Qdrant
make docker-up       # iniciar servicios Docker
make docker-down     # detener servicios Docker
make health          # OpenCode/MCP/Ollama/Qdrant/embeddings check
make clean           # eliminar bases de datos/index SQLite locales
```

## 6.2 Verificar el pipeline real de Qdrant/Ollama
```bash
opencode mcp list
```

## 6.3 Correr el indexador de código
```bash
cd code-index
python3 core.py index --path /ruta/al/repo --project mi-proyecto
python3 core.py search --query "manejo de reintentos HTTP" --project mi-proyecto
python3 core.py status --path /ruta/al/repo --project mi-proyecto
```

## 6.4 Correr tests de judgment-memory
```bash
cd judgment-memory
python3 test_ledger.py
```

## 6.5 Correr local-memory manualmente
```bash
cd local-memory
python3 server.py
```

| Componente 	| Test         | Qué cubre    |
|--------------|--------------|--------------|
| TonyMem server 					| `local-memory/server.py` (manual JSON-RPC) 	| Sesión completa: save, search, context, session-summary, prompt-capture 		|
| TonyMem plugin 					| `plugins/tonymem.ts` (tipado `tsc`) 			| Tipado contra stubs de `bun:sqlite`/`@opencode-ai/plugin` 					|
| Code Indexer 						| `code-index/test_core.py` 					| Chunking + mock HTTP end-to-end, 4/4 escenarios 								|
| DCP config 						| validado contra `dcp.schema.json` 			| Schema completo, `additionalProperties: false` 								|
| Judgment Day Memory Bridge 		| `judgment-memory/test_ledger.py` 				| Mock Ollama+Qdrant, 7/7 escenarios incl. camino feliz 						|
| Judgment Day Memory Bridge 		| `judgment-memory/test_hooks.ts` 				| Hooks de plugin (`chat.message`, `tool.execute.after`, `system.transform`) 	|
| Judgment Day Memory Bridge 		| `judgment-memory/scripts/verify-qdrant.ts` 	| Smoke test del cliente TS contra servicios reales 	

# 7 Gracias totales