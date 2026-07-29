# docker/ — backing services (Ollama + Qdrant), NixOS notes

This directory only containerizes the two backing services that
`code-index/` and `judgment-memory/` talk to over HTTP: **Ollama**
(embeddings) and **Qdrant** (vectors).

**Where to run this from**: `docker-compose.yml` itself has no relative
dependency on the rest of the repo — it only binds ports on localhost, so
it doesn't matter whether you run `docker compose up` from inside this
overlay checkout or after copying `docker/` somewhere else entirely. The
verify commands further down *do* assume relative paths (`../judgment-memory/...`)
— if you already copied `judgment-memory/` to `~/tools/tonymem/` per
`TONY-AI-INSTALL.md`, just run them from there instead
(`~/tools/tonymem/judgment-memory/scripts/verify-qdrant.ts`), pointed at
the same `localhost:11434`/`localhost:6333` these containers expose either
way.

## Why the MCP servers themselves aren't containerized

`local-memory/server.py`, `code-index/server.py`, and
`judgment-memory/server.py` are stdlib-only Python, spawned directly by
OpenCode over stdio (`mcp.<name>.command` in `opencode.json` — literally
`["python3", "./judgment-memory/server.py"]`). Putting them in containers
would mean piping stdin/stdout across a container boundary for zero
benefit — they have no dependencies to isolate (no `pip install`, ever,
by design) and need direct filesystem access to `{cwd}/.tonymem/*.db`. On
NixOS this is actually the easy part: `pkgs.python3` in your shell/flake
is all they need, nothing to build.

Ollama and Qdrant are the opposite case — real services with real state,
version pinning, and (for Ollama) GPU driver concerns — which is exactly
what Docker Compose is for.

## Prereqs on NixOS

Docker itself isn't installed by default on NixOS; enable it (or Podman,
which speaks the same Compose file) in your system config:

```nix
# configuration.nix
virtualisation.docker.enable = true;
# your user needs to be in the docker group:
users.users.<you>.extraGroups = [ "docker" ];
```

Podman alternative (no daemon, often preferred on NixOS):

```nix
virtualisation.podman.enable = true;
virtualisation.podman.dockerCompat = true;   # `docker` becomes an alias
```

Rebuild (`sudo nixos-rebuild switch`) and log out/in for the group change
to apply. Either way, the compose commands below are identical — `docker
compose` (Docker) or `podman compose` (Podman, needs
`environment.systemPackages = [ pkgs.podman-compose ];` or
`pkgs.docker-compose` which also works against the Podman socket).

### GPU (optional)

Only needed if you want Ollama to use your GPU for these embedding calls
too — the models here (`nomic-embed-text`, `bge-m3`) are small enough that
CPU is genuinely fine for judgment-memory's usage pattern (one short text
embedded per recall/record, not bulk indexing).

```nix
hardware.nvidia-container-toolkit.enable = true;
```

(Requires your NVIDIA driver already configured via
`hardware.nvidia`/`services.xserver.videoDrivers`, and a docker/podman
daemon restart after enabling.) Then:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Bringing it up

```bash
cd docker
cp .env.example .env   # optional, only if you need non-default ports
docker compose up -d
docker compose logs -f ollama-pull   # watch model pulls, exits when done
docker compose ps                    # qdrant + ollama should show "healthy"
```

First run pulls `nomic-embed-text` and `bge-m3` (a few hundred MB total) —
`ollama-pull` is a one-shot container, it exits once done and won't
restart on its own; `docker compose up` again later is a fast no-op.

## Verifying it's actually working

Same two test scripts already in the repo, just pointed at these
containers — since the ports match the defaults, no env vars needed:

```bash
python3 ../judgment-memory/test_ledger.py        # mock-based, doesn't
                                                    # actually need these
                                                    # containers up, but
                                                    # good to run anyway
bun run ../judgment-memory/scripts/verify-qdrant.ts   # THIS one needs
                                                          # the containers
                                                          # up — real
                                                          # embed/upsert/
                                                          # search calls
```

`verify-qdrant.ts` should print `ALL CHECKS PASSED`. If it doesn't:

```bash
curl http://localhost:6333/readyz     # Qdrant
curl http://localhost:11434/api/tags  # Ollama — should list nomic-embed-text, bge-m3
docker compose logs qdrant
docker compose logs ollama
```

**This compose file was written but not executed from this sandbox** — no
Docker Hub access here, only pip/npm registries (see the repo's network
restrictions). Treat the healthcheck definitions in particular as
best-effort; if `qdrant` reports unhealthy despite `curl
http://localhost:6333/readyz` working fine, the `/dev/tcp` healthcheck is
the likely culprit (some qdrant image variants may lack `bash`) — delete
the `healthcheck:` block for that service, Compose works fine without it,
you'll just lose the `service_healthy` gate for `ollama-pull`.

## Pointing the rest of the repo at these containers

Nothing to change if you used the default ports — `TONY_OLLAMA_URL`
(`http://localhost:11434`) and `TONY_QDRANT_URL` (`http://localhost:6333`)
in `opencode.json`'s `mcp.code-index`/`mcp.judgment-memory` blocks already
match. If you changed `OLLAMA_PORT`/`QDRANT_PORT` in `.env`, update those
same env values in `opencode.json` and in
`config/tony-memory.yaml` (documentation only, but keep it honest).

## Tearing down

```bash
docker compose down          # stops containers, keeps the named volumes
                              # (qdrant_storage, ollama_models) — models
                              # stay pulled, Qdrant data stays indexed
docker compose down -v       # also deletes those volumes — re-running
                              # `up` after this re-pulls every model and
                              # starts Qdrant empty
```
