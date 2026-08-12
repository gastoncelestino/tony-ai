#!/usr/bin/env python3
"""
Prueba definitiva del flujo SDD completo (explore -> archive) contra el
kernel REAL, vía `python3 -m kernel.cli` — el mismo subprocess que invoca
plugins/tony-kernel/index.ts. No usa mocks en ningún punto.

Uso:
    pytest tests/test_sdd_flow_e2e.py        # vía pytest (recomendado)
    python3 tests/test_sdd_flow_e2e.py       # standalone, con --keep-tmp disponible
    make verify-sdd-flow                     # atajo (ver Makefile)

Aislamiento: corre con TONY_KERNEL_STATE_DIR y TONY_REPO_ROOT apuntando a
un directorio temporal descartable (tempfile.mkdtemp()), así que NO toca
.tony-kernel/kernel-state.json del proyecto real ni escribe nada dentro
del working tree. El directorio temporal se borra al final, pase lo que
pase (try/finally), salvo que se pase --keep-tmp para inspeccionarlo.

Casos cubiertos, intercalados en la corrida legítima:
  1. Saltar fases (explore -> apply directo, y explore -> archive directo)
  2. Evidencia fabricada / inválida en record_phase_completion
  3. Tampering de un artifact real (store=openspec) después de sellado
  4. Scope violation: gitDiff toca un archivo fuera de allowed_files
  5. Corrida legítima completa explore -> archive con evidencia y
     artifacts reales, confirmando que SÍ se puede llegar al final.

Sale con código 0 si todo se comportó como se esperaba, 1 si algo falló.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class FlowRunner:
    """Corre kernel.cli contra un estado y unos artifacts 100% aislados."""

    def __init__(self, repo_root: Path, keep_tmp: bool = False):
        self.repo_root = repo_root
        self.keep_tmp = keep_tmp
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="tony-sdd-flow-"))
        self.change_dir = self.tmp_dir / "sdd" / "demo-change"
        self.change_dir.mkdir(parents=True, exist_ok=True)
        self.failures: list[str] = []
        self.checks_run = 0

    # ── infra ──────────────────────────────────────────────────────────
    def cleanup(self) -> None:
        if self.keep_tmp:
            print(f"\n(--keep-tmp) directorio de prueba conservado en: {self.tmp_dir}")
            return
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def run_cli(self, *args: str) -> tuple[int, dict | str]:
        """Invoca kernel.cli exactamente como lo hace plugins/tony-kernel/index.ts,
        pero con estado y artifacts redirigidos al tmp_dir aislado."""
        env = {
            **os.environ,
            "TONY_KERNEL_STATE_DIR": str(self.tmp_dir / ".tony-kernel"),
            "TONY_REPO_ROOT": str(self.tmp_dir),
        }
        proc = subprocess.run(
            [sys.executable, "-m", "kernel.cli", *args],
            cwd=self.repo_root,  # kernel/ debe resolver como paquete real
            capture_output=True,
            text=True,
            env=env,
        )
        out = proc.stdout.strip()
        try:
            parsed = json.loads(out) if out else {}
        except json.JSONDecodeError:
            parsed = out
        return proc.returncode, parsed

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        self.checks_run += 1
        status = "PASS" if condition else "FAIL"
        print(f"[{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
        if not condition:
            self.failures.append(label)

    # ── helpers de dominio ────────────────────────────────────────────
    def artifact(self, kind: str, store: str = "openspec") -> dict:
        path = f"sdd/demo-change/{kind}.md"
        full = self.tmp_dir / path
        content = full.read_bytes() if full.exists() else b""
        return {
            "kind": kind,
            "path": path,
            "store": store,
            "hash": hashlib.sha256(content).hexdigest(),
            "validated": True,
        }

    def write_artifact_file(self, kind: str, content: str) -> Path:
        p = self.change_dir / f"{kind}.md"
        p.write_text(content)
        return p

    @staticmethod
    def valid_evidence(claim: str) -> dict:
        return {"type": "command", "claim": claim, "command": "true", "exit_code": 0, "stdout": "ok"}

    def reset(self) -> None:
        self.run_cli("reset")

    def current_phase(self) -> str:
        _, status = self.run_cli("status")
        return status["current_phase"]

    # ── casos ─────────────────────────────────────────────────────────
    def caso_1_saltar_fases(self) -> None:
        print("\n=== CASO 1: saltar fases ===")

        self.reset()
        _, result = self.run_cli("can_start_phase", "apply")
        self.check(
            "explore -> apply directo debe BLOCK",
            result.get("decision") != "proceed",
            detail=json.dumps(result),
        )
        self.check(
            "debe ser un salto de transición inválido, no solo 'faltan artifacts'",
            result.get("decision") == "block_invalid_transition",
            detail=json.dumps(result),
        )

        self.reset()
        _, result = self.run_cli("can_start_phase", "archive")
        self.check(
            "explore -> archive directo (sdd-archive sin pasar por nada) debe BLOCK",
            result.get("decision") != "proceed",
            detail=json.dumps(result),
        )

    def caso_2_evidencia_fabricada(self) -> None:
        print("\n=== CASO 2: evidencia fabricada / inválida ===")

        self.reset()
        self.write_artifact_file("explore", "explore notes v1\n")
        fake_evidence = [{"type": "command", "claim": "confío en que anduvo"}]  # sin exit_code -> inválida

        _, result = self.run_cli(
            "record_phase_completion",
            "explore",
            json.dumps([self.artifact("explore")]),
            json.dumps(fake_evidence),
        )
        self.check(
            "evidencia fabricada debe BLOCK (block_evidence_required)",
            result.get("decision") == "block_evidence_required",
            detail=json.dumps(result),
        )
        self.check(
            "el estado NO debe haber avanzado (sigue en explore)",
            self.current_phase() == "explore",
        )

    def caso_3_tampering(self) -> None:
        print("\n=== CASO 3: tampering de artifact real (store=openspec) ===")

        self.reset()
        explore_path = self.write_artifact_file("explore", "explore notes ORIGINAL\n")

        sealed_artifact = self.artifact("explore")  # hash computado ANTES del tampering
        _, result = self.run_cli(
            "record_phase_completion",
            "explore",
            json.dumps([sealed_artifact]),
            json.dumps([self.valid_evidence("explore completado")]),
        )
        self.check(
            "completar explore con artifact real y evidencia válida -> PHASE_COMPLETE",
            result.get("decision") == "phase_complete",
            detail=json.dumps(result),
        )

        # Alguien (agente, bug, humano) modifica el archivo DESPUÉS de sellado.
        explore_path.write_text("explore notes TAMPERED — esto no debería pasar el checksum\n")

        # Reusamos la MISMA referencia sellada (mismo hash original): le
        # preguntamos al kernel "¿el contenido actual en disco todavía
        # matchea lo que registraste al completar la fase?"
        _, checksum_result = self.run_cli(
            "verify_phase_checksum",
            "explore",
            json.dumps([sealed_artifact]),
        )
        self.check(
            "verify_phase_checksum debe detectar el tampering (status=modified)",
            checksum_result.get("status") == "modified",
            detail=json.dumps(checksum_result),
        )
        self.check(
            "el artifact 'explore' debe listarse como modificado",
            "explore" in checksum_result.get("modified_artifacts", []),
            detail=json.dumps(checksum_result),
        )

    def caso_4_scope_violation(self) -> None:
        print("\n=== CASO 4: scope violation ===")

        _, result = self.run_cli(
            "check_scope", "+++ b/kernel/schemas.py\n", json.dumps(["sdd/*"])
        )
        self.check(
            "modificar kernel/schemas.py estando en scope sdd/* debe BLOCK",
            result.get("decision") == "block_scope_violation",
            detail=json.dumps(result),
        )
        self.check(
            "scope_violations debe listar el archivo ofensor",
            "kernel/schemas.py" in result.get("scope_violations", []),
            detail=json.dumps(result),
        )

        _, result = self.run_cli(
            "check_scope", "+++ b/sdd/demo-change/spec.md\n", json.dumps(["sdd/*"])
        )
        self.check(
            "modificar sdd/demo-change/spec.md estando en scope sdd/* debe PROCEED",
            result.get("decision") == "proceed",
            detail=json.dumps(result),
        )

    def caso_5_corrida_legitima(self) -> None:
        print("\n=== CASO 5: corrida legítima completa explore -> archive ===")

        self.reset()
        plan = ["explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"]
        kind_by_phase = {
            "explore": "explore", "propose": "proposal", "spec": "spec",
            "design": "design", "tasks": "tasks", "apply": "apply-progress",
            "verify": "verify-report", "archive": "archive-report",
        }

        for phase in plan:
            _, gate = self.run_cli("can_start_phase", phase)
            self.check(f"can_start_phase({phase}) -> proceed", gate.get("decision") == "proceed",
                       detail=json.dumps(gate))
            self.run_cli("record_delegation", phase, "sub-agent")

            kind = kind_by_phase[phase]
            self.write_artifact_file(kind, f"{phase} content v1\n")
            _, completion = self.run_cli(
                "record_phase_completion",
                phase,
                json.dumps([self.artifact(kind)]),
                json.dumps([self.valid_evidence(f"{phase} verificado")]),
            )
            self.check(f"record_phase_completion({phase}) -> phase_complete",
                       completion.get("decision") == "phase_complete", detail=json.dumps(completion))

        _, final_status = self.run_cli("status")
        self.check(
            "estado final: current_phase == archive",
            final_status.get("current_phase") == "archive",
            detail=json.dumps(final_status),
        )

    # ── orquestación ──────────────────────────────────────────────────
    def run_all(self) -> int:
        print(f"Directorio aislado de la corrida: {self.tmp_dir}")
        print(f"(no toca {self.repo_root / '.tony-kernel'} ni el working tree real)")
        try:
            self.caso_1_saltar_fases()
            self.caso_2_evidencia_fabricada()
            self.caso_3_tampering()
            self.caso_4_scope_violation()
            self.caso_5_corrida_legitima()
        finally:
            self.cleanup()

        print("\n" + "=" * 60)
        if self.failures:
            print(f"RESULTADO: {len(self.failures)}/{self.checks_run} caso(s) fallaron:")
            for f in self.failures:
                print(f"  - {f}")
            return 1
        print(f"RESULTADO: {self.checks_run}/{self.checks_run} casos OK.")
        return 0


def test_sdd_flow_e2e() -> None:
    """pytest entry point: runs the full isolated adversarial flow (28 checks)."""
    runner = FlowRunner(REPO_ROOT)
    assert runner.run_all() == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Raíz del repo (donde vive kernel/). Default: dos niveles arriba de este script.",
    )
    parser.add_argument(
        "--keep-tmp",
        action="store_true",
        help="No borrar el directorio temporal al final (para inspeccionarlo a mano).",
    )
    args = parser.parse_args()

    runner = FlowRunner(Path(args.repo_root).resolve(), keep_tmp=args.keep_tmp)
    return runner.run_all()


if __name__ == "__main__":
    sys.exit(main())
