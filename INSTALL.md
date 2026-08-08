# Tony-AI - Instalación detallada

# 0. Prerequisitos
- **Python 3.10+** para los servidores MCP en Python.
- **Bun** para los scripts de verificación basados en TypeScript y plugins.
- **OpenCode CLI** (instalador oficial: https://opencode.ai)
- **Ollama** (https://ollama.com/download)
- **Docker** (opcional, para correr Qdrant + Ollama como servicios)

## Para características semánticas (code-index y judgment-memory)
- **Qdrant** corriendo localmente o remotamente.
- La capa de memoria local funciona sin Ollama ni Qdrant. La búsqueda semántica de código y el recall de juicios requieren ambos servicios.

# 1. Clonar repositorio
> El repo es privado: necesitás acceso concedido por el owner antes de clonar.

```bash
git clone https://github.com/gastoncelestino/tony-ai.git
cd tony-ai
```

# 2. Instalación automática (recomendada)
```bash
make docker-up     # Opcional: levanta Ollama + Qdrant en Docker (o `ollama serve` si lo tenés nativo)
./scripts/setup.sh    # Verifica dependencias, descarga modelos, configura .env
./scripts/health.sh   # Verificar estado del sistema
```

`setup.sh` hace:
1. Verifica dependencias (Python, Bun, OpenCode CLI, Docker)
2. Verifica que Ollama y Qdrant ya estén corriendo (no los levanta — usá `make docker-up` o `ollama serve` antes)
3. Descarga los modelos de Ollama (requiere Ollama respondiendo): qwen3-coder:30b, omnicoder:9b, deepseek-r1:14b, ornith:9b, bge-m3, nomic-embed-text
4. Configura `.env.example`
5. Regenera `opencode.json` con rutas portables usando `TONY_REPO_ROOT`

`health.sh` verifica:
1. OpenCode config válida
2. Los 3 MCP servers arrancan
3. Ollama responde y tiene los modelos
4. Qdrant responde
5. Pipeline de embeddings funcional

# 3. Instalación manual (si no hiciste la instalación automática)
## 3.1 Copiar configuración de OpenCode
```bash
mkdir -p ~/.opencode/plugins
cp opencode.json ~/.opencode/
cp AGENTS.md ~/.opencode/
cp plugins/tonymem.ts ~/.opencode/plugins/
cp plugins/qdrant.ts ~/.opencode/plugins/
cp plugins/judgment-memory.ts ~/.opencode/plugins/
```

## 3.2 Configurar variables de entorno
```bash
cp .env.example .env
```

Editá `.env` y ajustá `TONY_REPO_ROOT` a la ruta absoluta de tu clone:

```env
TONY_REPO_ROOT=/home/tu-usuario/proyectos/tony-ai
TONY_OLLAMA_URL=http://localhost:11434
TONY_QDRANT_URL=http://localhost:6333
JUDGMENT_EMBED_MODEL=nomic-embed-text
CODE_EMBED_MODEL=bge-m3
TONY_INDEX_CHUNKER=regex
```

Si usás Zsh:
```bash
echo 'export TONY_REPO_ROOT="'"$(pwd)"'"' >> ~/.zshrc
source ~/.zshrc
```

Si usás Bash:
```bash
echo 'export TONY_REPO_ROOT="'"$(pwd)"'"' >> ~/.bashrc
source ~/.bashrc
```

## 3.3 Deberías ver algo como:
```bash
📄 .env
📄 AGENTS.md
📄 opencode.json
📁 plugins
   📄 tonymem.ts
   📄 qdrant.ts
   📄 judgment-memory.ts
```

## 3.3 Iniciar servicios de soporte
```bash
cd docker
docker compose up -d
docker compose ps
```

Deberías ver algo como:
| NAME | IMAGE | COMMAND | SERVICE | STATUS | PORTS |
|------|-------|---------|---------|--------|-------|
| tony-ai-qdrant | qdrant/qdrant:latest | /bin/qdrant... | qdrant | running | 0.0.0.0:6333->6333/tcp |
| tony-ai-ollama | ollama/ollama:latest | /usr/bin/ollama... | ollama | running | 0.0.0.0:11434->11434/tcp |

## 3.4 Descargar modelos de Ollama
## 3.4.1 Modelos grandes (descargan lentamente)
```bash
ollama pull qwen3-coder:30b
ollama pull deepseek-r1:14b
```
## 3.4.2 Modelos medianos
```bash
ollama pull omnicoder:9b
ollama pull ornith:9b
```
## 3.4.3 Modelos pequeños (rápidos)
```bash
ollama pull bge-m3
ollama pull nomic-embed-text
```

# 4. Verificar instalación
```bash
make health          # Verificación end-to-end
make test            # Ejecutar todos los tests
```


# 5. Correr el suite de tests
## 5.1 Correr tests de Python + TypeScript. 
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

## 5.2 Verificar el pipeline real de Qdrant/Ollama
```bash
opencode mcp list
```

## 5.3 Correr el indexador de código
```bash
cd code-index
python3 core.py index --path /ruta/al/repo --project mi-proyecto
python3 core.py search --query "manejo de reintentos HTTP" --project mi-proyecto
python3 core.py status --path /ruta/al/repo --project mi-proyecto
```

## 5.4 Correr tests de judgment-memory
```bash
cd judgment-memory
python3 test_ledger.py
```

## 5.5 Correr local-memory manualmente
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


# 6. Troubleshooting

## OpenCode no encuentra los MCP servers
Verificá que `opencode.json` no tenga rutas absolutas:
```bash
grep -E '/home/[a-zA-Z0-9_]+/' opencode.json
```
Si encuentra algo, corré `make bootstrap` para regenerar las rutas con `{env:TONY_REPO_ROOT}`.

## Ollama no responde
```bash
curl http://localhost:11434/api/tags
```
Si no responde, iniciá el servicio:
```bash
ollama serve
```
O con Docker:
```bash
cd docker && docker compose up -d ollama
```

## Qdrant no responde
```bash
curl http://localhost:6333/readyz
```
Si no responde, iniciá el servicio:
```bash
cd docker && docker compose up -d qdrant
```

## Falla el smoke test de embeddings
Verificá que los modelos estén descargados:
```bash
ollama list | grep bge-m3
ollama list | grep nomic-embed-text
```
Si no están, descargalos:
```bash
ollama pull bge-m3
ollama pull nomic-embed-text
```

## Error: "module not found" en Python
Los servidores MCP usan solo stdlib — no requieren `pip install` ni dependencias externas.

Si te faltan módulos como `tree_sitter`, es porque activaste `TONY_INDEX_CHUNKER=tree-sitter`. Instalá las dependencias opcionales:
```bash
pip install -r requirements-optional.txt
```
O volver al chunker por defecto (regex, stdlib):
```bash
export TONY_INDEX_CHUNKER=regex
```

## Los comandos /sdd-* no aparecen en autocompletado
Reiniciá OpenCode CLI después de copiar `opencode.json` y `AGENTS.md` a `~/.opencode/`.
