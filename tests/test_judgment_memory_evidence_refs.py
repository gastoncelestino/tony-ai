import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "judgment-memory"))
import ledger


def test_judgment_evidence_refs_round_trip():
    tmp_path = tempfile.mkdtemp()
    original_db_path = ledger.DB_PATH
    ledger.DB_PATH = os.path.join(tmp_path, "judgment-memory.db")
    try:
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
        assert ledger.history(project="demo")[0]["evidence_refs"] == ["evidence:abc", "evidence:def"]
        updated = {**record, "evidence_refs": ["evidence:def", "evidence:ghi"]}
        assert ledger.save_judgment(updated)["action"] == "updated"
        assert ledger.history(project="demo")[0]["evidence_refs"] == ["evidence:def", "evidence:ghi"]
    finally:
        ledger.DB_PATH = original_db_path
        shutil.rmtree(tmp_path, ignore_errors=True)
