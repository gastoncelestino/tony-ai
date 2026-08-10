# Trigger Rules — Reglas Puras de Cuándo Dispara Review

> Reglas deterministas para decidir CUÁNDO y QUÉ review lanzar. El Review Contract completo (lentes, receipt validation, receipt actions) está en `review-contract-full.md` y se carga BAJO DEMANDA.

## Reglas de Trigger

### 1. Post-Apply
Después de que la fase `sdd-apply` completa: si NO existe receipt válido → dispara `review/start(target)` explícitamente. Si existe receipt válido → reutilizar, NO lanzar review.

### 2. Pre-Commit / Pre-Push / Pre-PR
Siempre: validar el receipt existente content-bound con nativo:
```
validate review receipt via mem_review/mem_search against AGENTS.md <gate> --cwd <repo>
```
**Nunca** iniciar reviewer, **nunca** resetear budget, **nunca** crear nuevo budget.

### 3. Release
- Si tag apunta a `origin/main` SHA actual + CI requerido pasa + remote head recheck + no fresh risk evidence → bypass receipt validation (fast path)
- Sino → fail closed via native receipt validation
- Major / post-incident releases → **siempre** extraordinary review explícita

### 4. Evidencia que Invalida/Escalada (sin reabrir review)
Nuevo CI fallando, vulnerabilidad, cambio de base, cambio de política, procedencia, o evidencia de release → invalida/escalada receipt existente. **No reabre** review de código unchanged.

### 5. Clasificación de Riesgo (para selección de lentes)
| Nivel | Criterio | Lentes |
|-------|----------|--------|
| **Low** | Solo docs, comments, formatting, typo-only strings (cero código/config) | Ninguna |
| **Medium** | Cualquier otro cambio | Exactamente UNA lente dominante |
| **High** | Security/auth/update/payments, data loss/exposure, permission changes, shell/process integration, **>400 authored changed lines** | 4R completo (4 lentes) |

*Goldens generados excluidos del threshold de 400 líneas pero mantienen snapshot identity.*

### 5. Tabla de Lentes por Señal de Riesgo
| Señal de Riesgo | Lente |
|-----------------|-------|
| Clear naming, structure, maintainability, small refactors | `review-readability` |
| Behavior, state, tests, determinism, regressions | `review-reliability` |
| Shell/process integration, partial failures, recovery, degraded dependencies | `review-resilience` |
| Security, permissions, data exposure/loss, architecture, dependencies | `review-risk` |

### 6. Gates de Receipt (Pre-commit / Pre-push / Pre-PR / Release)
En **todos los gates**: validar receipt content-bound existente con:
```
validate review receipt via mem_review/mem_search against AGENTS.md <gate> --cwd <repo>
```
**Nunca**: iniciar reviewer, resetear budget, crear nuevo budget.

### 5. Receipt Action Table
| Estado Receipt | Acción |
|----------------|--------|
| **missing** | Iniciar review explícitamente post-apply / post-implementation |
| **scope-changed** | Crear nuevo lineage (nuevo `lineageId`) |
| **invalidated** | Requerir acción explícita de maintainer |
| **escalated** | Stop |

Evidencia que invalida/escalada: nuevo CI, vulnerabilidad, base, política, procedencia, release → invalida/escalada sin reabrir review de código unchanged.

### 6. Selección de Lentes (Inside `review/start(target)` only)
- **Low** (solo docs/comments/formatting/typo-only strings; cero código/config) → sin lente
- **Medium** (cualquier otro cambio) → exactamente UNA lente dominante
- **High** (security/auth/update/payments, data loss/exposure, permission changes, shell/process integration, >400 authored lines) → 4R completo (4 lentes)

*Goldens excluidos del threshold 400 líneas; model/provider/profile/effort nunca son inputs del clasificador.*

### 7. Gates Específicos
- **Pre-commit**: validar receipt staged/intended vs receipt existente; nunca crear budget
- **Pre-push**: validar receipt commits pushed vs receipt existente
- **Pre-PR**: validar candidate tree, paths, policy, evidence, base relationship, receipt
- **Release**: validar immutable release tree, provenance, evidence, publication boundary

**En todos**: validar receipt content-bound; nunca iniciar reviewer ni resetear budget.

### 8. Post-SDD Apply
Después de `sdd-apply`: si NO existe receipt válido → `review/start(target)` explícito; si existe → reutilizar.