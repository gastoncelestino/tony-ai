import unittest

from kernel.evidence_ledger import EvidenceLedger
from kernel.schemas import Claim, ClaimStatus, Evidence, EvidenceType


class EvidenceLedgerTests(unittest.TestCase):
    def valid_evidence(self, claim: str) -> Evidence:
        return Evidence(
            type=EvidenceType.COMMAND,
            claim=claim,
            command="make test",
            exit_code=0,
            stdout="ok",
        )

    def invalid_evidence(self, claim: str) -> Evidence:
        return Evidence(
            type=EvidenceType.COMMAND,
            claim=claim,
            command="make test",
            exit_code=1,
            stderr="failed",
        )

    def test_claim_with_valid_evidence_is_supported(self):
        ledger = EvidenceLedger()
        claim = Claim(
            id="tests-pass",
            description="Tests pass",
            evidence=(self.valid_evidence("tests-pass"),),
            required=True,
        )
        ledger.add_claim(claim)

        self.assertTrue(ledger.has_evidence_for("tests-pass"))
        self.assertEqual(ledger.get_claim("tests-pass").evaluate(), ClaimStatus.SUPPORTED)
        self.assertTrue(ledger.all_required_supported())

    def test_claim_without_evidence_is_unsupported(self):
        ledger = EvidenceLedger()
        ledger.add_claim(Claim(id="tests-pass", description="Tests pass", required=True))

        self.assertFalse(ledger.has_evidence_for("tests-pass"))
        self.assertFalse(ledger.all_required_supported())
        self.assertEqual(ledger.get_required_unsupported(), [ledger.get_claim("tests-pass")])

    def test_invalid_evidence_does_not_support_claim(self):
        ledger = EvidenceLedger()
        claim = Claim(
            id="tests-pass",
            description="Tests pass",
            evidence=(self.invalid_evidence("tests-pass"),),
            required=True,
        )
        ledger.add_claim(claim)

        self.assertFalse(ledger.has_evidence_for("tests-pass"))
        self.assertFalse(ledger.all_required_supported())
        self.assertIn(claim, ledger.get_unsupported_claims())

    def test_optional_unsupported_claim_does_not_block_required_support(self):
        ledger = EvidenceLedger()
        required = Claim(
            id="tests-pass",
            description="Tests pass",
            evidence=(self.valid_evidence("tests-pass"),),
            required=True,
        )
        optional = Claim(
            id="docs-updated",
            description="Docs updated",
            required=False,
        )
        ledger.add_claim(required)
        ledger.add_claim(optional)

        self.assertTrue(ledger.all_required_supported())
        self.assertEqual(ledger.get_required_unsupported(), [])
        self.assertIn(optional, ledger.get_unsupported_claims())

    def test_required_unsupported_excludes_supported_and_optional_claims(self):
        ledger = EvidenceLedger()
        supported = Claim(
            id="tests-pass",
            description="Tests pass",
            evidence=(self.valid_evidence("tests-pass"),),
            required=True,
        )
        unsupported_required = Claim(
            id="build-pass",
            description="Build passes",
            required=True,
        )
        unsupported_optional = Claim(
            id="docs-updated",
            description="Docs updated",
            required=False,
        )
        for claim in (supported, unsupported_required, unsupported_optional):
            ledger.add_claim(claim)

        self.assertEqual(ledger.get_required_unsupported(), [unsupported_required])

    def test_unknown_claim_has_no_evidence(self):
        ledger = EvidenceLedger()

        self.assertFalse(ledger.has_evidence_for("missing-claim"))


if __name__ == "__main__":
    unittest.main()
