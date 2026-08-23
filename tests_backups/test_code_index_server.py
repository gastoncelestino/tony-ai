"""Regression tests for the code-index MCP server wiring."""

import os
import sys
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "code-index"))

import server


def test_code_reindex_delegates_to_index_repo():
    expected = {"files_scanned": 2, "files_indexed": 2, "chunks_upserted": 3, "errors": []}
    with patch.object(server.core, "index_repo", return_value=expected) as index_repo:
        result = server.code_reindex({"path": "/tmp/project", "project": "demo"})

    assert result == expected
    index_repo.assert_called_once_with("/tmp/project", "demo")
