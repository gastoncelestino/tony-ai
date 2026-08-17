import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "judgment-memory"))

import ledger


def _record(refs):
    return {
        "execution_id": "jd-lineage-001",
        "project": "lineage-test",
        "task": "validate evidence",
        "final": "approve",
        "evidence_refs": refs,
    }


def test_record_judgment_validates_refs_before_persistence():
    tmp = tempfile.mkdtemp()
    ledger.DB_PATH = os.path.join(tmp, "judgment-memory.db")
    ledger.init_db()

    def validator(refs):
        assert refs == ["evidence:1", "evidence:1"]
        return ("evidence:1",)

    result = ledger.record_judgment(
        _record(["evidence:1", "evidence:1"]),
        index=False,
        evidence_validator=validator,
    )

    assert result["action"] == "created"
    assert ledger.history(project="lineage-test")[0]["evidence_refs"] == ["evidence:1"]


def test_record_judgment_rejects_invalid_refs_before_persistence():
    tmp = tempfile.mkdtemp()
    ledger.DB_PATH = os.path.join(tmp, "judgment-memory.db")
    ledger.init_db()

    def validator(refs):
        raise ValueError("unknown evidence ref")

    try:
        ledger.record_judgment(
            _record(["evidence:missing"]),
            index=False,
            evidence_validator=validator,
        )
    except ValueError as exc:
        assert str(exc) == "unknown evidence ref"
    else:
        raise AssertionError("expected validation failure")

    assert ledger.history(project="lineage-test") == []
