import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "judgment-memory"))
import ledger


def test_judgment_evidence_refs_round_trip(tmp_path):
    ledger.DB_PATH = str(tmp_path / "judgment-memory.db")
    ledger.init_db()

    record = {
        "execution_id": "jd-evidence-001",
        "project": "demo",
        "task": "validate evidence linkage",
        "final": "approve",
        "evidence_refs": ["evidence:abc", "evidence:abc", "evidence:def"],
    }

    result = ledger.save_judgment(record)
    assert result["action"] == "created"

    history = ledger.history(project="demo")
    assert history[0]["evidence_refs"] == ["evidence:abc", "evidence:def"]

    updated = {**record, "evidence_refs": ["evidence:def", "evidence:ghi"]}
    assert ledger.save_judgment(updated)["action"] == "updated"
    assert ledger.history(project="demo")[0]["evidence_refs"] == ["evidence:def", "evidence:ghi"]
