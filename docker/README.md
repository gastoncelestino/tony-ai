# docker/ — servicios de soporte (Ollama + Qdrant)

Esta carpeta solo containeriza los dos servicios de soporte que `code-index/` y `judgment-memory/` usan por HTTP: **Ollama** (embeddings) y **Qdrant** (vectores).

**Desde dónde correrlo**: `docker-compose.yml` no tiene dependencias relativas del resto del repo — solo bindea puertos en localhost, así que da igual correr `docker compose up` desde dentro de este checkout o después de copiar `docker/` a cualquier otro lado. Los comandos de verificación de más abajo sí asumen rutas relativas (`../judgment-memory/...`) — si ya copiaste `judgment-memory/` a `~/tools/tonymem/` según `INSTALL.md`, corralos desde ahí (`~/tests/judgment_qdrant.test.ts`), apuntando al mismo `localhost:11434`/`localhost:6333` que exponen estos containers de todas formas.

## Por qué los MCP servers no están containerizados

`local-memory/server.py`, `code-index/server.py` y `judgment-memory/server.py` son Python stdlib-only, spawneados directamente por OpenCode por stdio (`mcp.<name>.command` en `opencode.json` — literalmente `["python3", "./judgment-memory/server.py"]`). Meterlos en containers significaría pipear stdin/stdout atravesando un boundary de container para cero beneficio — no tienen dependencias que aislar (nunca hace falta `pip install`, por diseño) y necesitan acceso directo al filesystem de `{cwd}/.tonymem/*.db`. En Linux esto es lo más simple: el Python del sistema es todo lo que necesitan, nada para compilar.

Ollama y Qdrant son el caso opuesto — servicios reales con estado real, versionado y (para Ollama) consideraciones de GPU — que es exactamente para lo que sirve Docker Compose.

## Prerequisitos en Linux

Docker no viene instalado por defecto en la mayoría de las distros; instalalo desde tu gestor de paquetes:

```bash
# Debian/Ubuntu
sudo apt update && sudo apt install docker.io docker-compose

# Fedora/RHEL
sudo dnf install docker docker-compose

# Arch
sudo pacman -S docker docker-compose
```

Tu usuario necesita estar en el grupo `docker`:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Si preferís Podman (sin demonio, cada vez más común en Linux):

```bash
# Debian/Ubuntu
sudo apt install podman podman-compose

# Fedora
sudo dnf install podman podman-compose
```

`podman-compose` habla el mismo archivo Compose. Los comandos de abajo son iguales — `docker compose` (Docker) o `podman compose` (Podman).

### GPU (opcional)

Solo necesario si querés que Ollama use la GPU para estos embeddings — los modelos de este repo (`nomic-embed-text`, `bge-m3`) son chicos y la CPU alcanza perfectamente para el patrón de uso de judgment-memory (un texto corto embebido por recall/record, no indexación masiva).

```bash
# NVIDIA
sudo apt install nvidia-container-toolkit
sudo systemctl restart docker
```

Luego:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Levantar los servicios

```bash
cd docker
cp .env.example .env   # opcional, solo si necesitás puertos no default
docker compose up -d
docker compose logs -f ollama-pull   # seguí la descarga de modelos, sale cuando termina
docker compose ps                    # qdrant + ollama deberían decir "healthy"
```

La primera vez descarga `nomic-embed-text` y `bge-m3` (unos cientos de MB total) — `ollama-pull` es un container one-shot, sale cuando termina y no se reinicia solo; volver a correr `docker compose up` después es un no-op rápido.

## Verificar que anda

Mismos dos scripts del repo, apuntando a estos containers — como los puertos son los defaults, no hace falta cambiar variables de entorno:

```bash
python3 ../tests/test_judgment_memory_ledger.py   # mock-based, no necesita
                                                    # estos containers,
                                                    # pero es bueno correrlo
                                                    # igual
bun run ../tests/judgment_qdrant.test.ts   			# ESTE sí necesita
                                                        # los containers
                                                        # arriba — llamadas
                                                        # embed/upsert/search
                                                        # reales
```

`judgment_qdrant.test.ts` debería imprimir `ALL CHECKS PASSED`. Si no lo hace:

```bash
curl http://localhost:6333/readyz     # Qdrant
curl http://localhost:11434/api/tags  # Ollama — debería listar nomic-embed-text, bge-m3
docker compose logs qdrant
docker compose logs ollama
```

## Apuntar el resto del repo a estos containers

Si usaste los puertos default, no tenés que cambiar nada — `TONY_OLLAMA_URL` (`http://localhost:11434`) y `TONY_QDRANT_URL` (`http://localhost:6333`) en los bloques `mcp.code-index`/`mcp.judgment-memory` de `opencode.json` ya coinciden. Si cambiaste `OLLAMA_PORT`/`QDRANT_PORT` en `.env`, actualizá esos mismos valores en `opencode.json` y en `config/tony-memory.yaml` (es documentación, pero hay que mantenerla honesta).

## Bajar los servicios

```bash
docker compose down          # detiene containers, mantiene los named volumes
                            # (qdrant_storage, ollama_models) — los modelos
                            # quedan descargados, los datos de Qdrant se
                            # mantienen indexados
docker compose down -v       # también borra esos volumes — volver a correr
                            # `up` después re-pull todos los modelos y
                            # arranca Qdrant vacío
```
