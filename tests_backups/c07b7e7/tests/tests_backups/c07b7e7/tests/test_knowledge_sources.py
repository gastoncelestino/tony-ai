import json
from pathlib import Path

from knowledge.sources import get_enabled_sources


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "knowledge_sources.json"
OPENCODE_PATH = ROOT / "opencode.json"
CONTEXT7_PLUGIN_PATH = ROOT / "plugins" / "context7-allowlist.ts"
PROJECT_CODE_PLUGIN_PATH = ROOT / "plugins" / "project-code-context.ts"
CONTEXT_ASSEMBLY_PLUGIN_PATH = ROOT / "plugins" / "context-assembly.ts"
EXPECTED_LIBRARY_IDS = {
    "python": "/websites/python_3_14",
    "fastapi": "/websites/fastapi_tiangolo",
    "react": "/reactjs/react.dev",
    "postgresql": "/supabase/postgres",
}


def load_sources() -> dict:
    with SOURCES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_knowledge_sources_are_valid_and_unique():
    data = load_sources()
    sources = data["sources"]
    assert sources
    assert len({source["id"] for source in sources}) == len(sources)
    assert all(source["enabled"] is True for source in sources)
    assert all(source["library_id"].startswith("/") for source in sources)
    assert all(source["url"].startswith("https://") for source in sources)


def test_approved_library_ids_match_context7():
    sources = {source["id"]: source for source in load_sources()["sources"]}
    assert set(sources) == set(EXPECTED_LIBRARY_IDS)
    for source_id, library_id in EXPECTED_LIBRARY_IDS.items():
        assert sources[source_id]["library_id"] == library_id


def test_opencode_allows_context7_tools():
    with OPENCODE_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    assert config["mcp"]["context7"]["enabled"] is True
    assert config["permission"]["context7_*"] == "allow"


def test_context7_allowlist_plugin_is_loaded():
    with OPENCODE_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    assert "plugins/context7-allowlist.ts" in config["plugin"]
    assert CONTEXT7_PLUGIN_PATH.is_file()


def test_project_code_context_plugin_is_loaded():
    with OPENCODE_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    assert "plugins/project-code-context.ts" in config["plugin"]
    assert PROJECT_CODE_PLUGIN_PATH.is_file()


def test_context_assembly_plugin_is_loaded():
    with OPENCODE_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    assert "plugins/context-assembly.ts" in config["plugin"]
    assert CONTEXT_ASSEMBLY_PLUGIN_PATH.is_file()


def test_approved_sources_are_explicitly_enabled():
    sources = load_sources()["sources"]
    assert {source["id"] for source in sources if source["enabled"]} == set(EXPECTED_LIBRARY_IDS)


def test_get_enabled_sources_returns_the_closed_allowlist():
    sources = get_enabled_sources()
    assert {source["id"] for source in sources} == set(EXPECTED_LIBRARY_IDS)
    assert all(source["enabled"] is True for source in sources)
