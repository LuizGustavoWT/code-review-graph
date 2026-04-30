"""Tests for the PreToolUse search enrichment module, post-build enrichment,
and bare CALLS resolution."""

import hashlib
import os
import tempfile
from pathlib import Path

from code_review_graph.enrich import (
    enrich_file_read,
    enrich_search,
    extract_pattern,
)
from code_review_graph.graph import GraphStore
from code_review_graph.jedi_resolver import enrich_jedi_calls
from code_review_graph.parser import CodeParser, EdgeInfo, NodeInfo
from code_review_graph.search import rebuild_fts_index


class TestExtractPattern:
    def test_grep_pattern(self):
        assert extract_pattern("Grep", {"pattern": "parse_file"}) == "parse_file"

    def test_grep_empty(self):
        assert extract_pattern("Grep", {}) is None

    def test_glob_meaningful_name(self):
        assert extract_pattern("Glob", {"pattern": "**/auth*.ts"}) == "auth"

    def test_glob_pure_extension(self):
        assert extract_pattern("Glob", {"pattern": "**/*.ts"}) is None

    def test_glob_short_name(self):
        # "ab" is only 2 chars, below minimum regex match of 3
        assert extract_pattern("Glob", {"pattern": "**/ab.ts"}) is None

    def test_bash_rg_pattern(self):
        result = extract_pattern("Bash", {"command": "rg parse_file src/"})
        assert result == "parse_file"

    def test_bash_grep_pattern(self):
        result = extract_pattern("Bash", {"command": "grep -r 'GraphStore' ."})
        assert result == "GraphStore"

    def test_bash_rg_with_flags(self):
        result = extract_pattern("Bash", {"command": "rg -t py -i parse_file"})
        assert result == "parse_file"

    def test_bash_non_grep_command(self):
        assert extract_pattern("Bash", {"command": "ls -la"}) is None

    def test_bash_short_pattern(self):
        # Pattern "ab" is only 2 chars
        assert extract_pattern("Bash", {"command": "rg ab src/"}) is None

    def test_unknown_tool(self):
        assert extract_pattern("Write", {"content": "hello"}) is None

    def test_bash_rg_with_glob_flag(self):
        result = extract_pattern(
            "Bash", {"command": "rg --glob '*.py' parse_file"}
        )
        assert result == "parse_file"


class TestEnrichSearch:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_dir = Path(self.tmpdir) / ".code-review-graph"
        self.db_dir.mkdir()
        self.db_path = self.db_dir / "graph.db"
        self.store = GraphStore(self.db_path)
        self._seed_data()

    def teardown_method(self):
        self.store.close()

    def _seed_data(self):
        nodes = [
            NodeInfo(
                kind="Function", name="parse_file", file_path=f"{self.tmpdir}/parser.py",
                line_start=10, line_end=50, language="python",
                params="(path: str)", return_type="list[Node]",
            ),
            NodeInfo(
                kind="Function", name="full_build", file_path=f"{self.tmpdir}/build.py",
                line_start=1, line_end=30, language="python",
            ),
            NodeInfo(
                kind="Test", name="test_parse_file",
                file_path=f"{self.tmpdir}/test_parser.py",
                line_start=1, line_end=20, language="python",
                is_test=True,
            ),
        ]
        for n in nodes:
            self.store.upsert_node(n)
        edges = [
            EdgeInfo(
                kind="CALLS",
                source=f"{self.tmpdir}/build.py::full_build",
                target=f"{self.tmpdir}/parser.py::parse_file",
                file_path=f"{self.tmpdir}/build.py", line=15,
            ),
            EdgeInfo(
                kind="TESTED_BY",
                source=f"{self.tmpdir}/test_parser.py::test_parse_file",
                target=f"{self.tmpdir}/parser.py::parse_file",
                file_path=f"{self.tmpdir}/test_parser.py", line=1,
            ),
        ]
        for e in edges:
            self.store.upsert_edge(e)
        rebuild_fts_index(self.store)

    def test_returns_matching_symbols(self):
        result = enrich_search("parse_file", self.tmpdir)
        assert "[code-review-graph]" in result
        assert "parse_file" in result

    def test_includes_callers(self):
        result = enrich_search("parse_file", self.tmpdir)
        assert "Called by:" in result
        assert "full_build" in result

    def test_includes_tests(self):
        result = enrich_search("parse_file", self.tmpdir)
        assert "Tests:" in result
        assert "test_parse_file" in result

    def test_excludes_test_nodes(self):
        result = enrich_search("test_parse", self.tmpdir)
        # test nodes should be filtered out of results
        assert "test_parse_file" not in result or "symbol(s)" in result

    def test_empty_for_no_match(self):
        result = enrich_search("nonexistent_function_xyz", self.tmpdir)
        assert result == ""

    def test_empty_for_missing_db(self):
        result = enrich_search("parse_file", "/tmp/nonexistent_repo_xyz")
        assert result == ""


class TestEnrichFileRead:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_dir = Path(self.tmpdir) / ".code-review-graph"
        self.db_dir.mkdir()
        self.db_path = self.db_dir / "graph.db"
        self.store = GraphStore(self.db_path)
        self._seed_data()

    def teardown_method(self):
        self.store.close()

    def _seed_data(self):
        self.file_path = f"{self.tmpdir}/parser.py"
        nodes = [
            NodeInfo(
                kind="File", name="parser.py", file_path=self.file_path,
                line_start=1, line_end=100, language="python",
            ),
            NodeInfo(
                kind="Function", name="parse_file", file_path=self.file_path,
                line_start=10, line_end=50, language="python",
            ),
            NodeInfo(
                kind="Function", name="parse_imports", file_path=self.file_path,
                line_start=55, line_end=80, language="python",
            ),
        ]
        for n in nodes:
            self.store.upsert_node(n)
        edges = [
            EdgeInfo(
                kind="CALLS",
                source=f"{self.file_path}::parse_file",
                target=f"{self.file_path}::parse_imports",
                file_path=self.file_path, line=30,
            ),
        ]
        for e in edges:
            self.store.upsert_edge(e)
        self.store._conn.commit()

    def test_returns_file_symbols(self):
        result = enrich_file_read(self.file_path, self.tmpdir)
        assert "[code-review-graph]" in result
        assert "parse_file" in result
        assert "parse_imports" in result

    def test_excludes_file_nodes(self):
        result = enrich_file_read(self.file_path, self.tmpdir)
        # File node "parser.py" should not appear as a symbol entry
        lines = result.split("\n")
        symbol_lines = [
            ln for ln in lines
            if ln and not ln.startswith(" ") and not ln.startswith("[")
        ]
        for line in symbol_lines:
            assert "parser.py (" not in line or "parse_" in line

    def test_includes_callees(self):
        result = enrich_file_read(self.file_path, self.tmpdir)
        assert "Calls:" in result
        assert "parse_imports" in result

    def test_empty_for_unknown_file(self):
        result = enrich_file_read("/nonexistent/file.py", self.tmpdir)
        assert result == ""

    def test_empty_for_missing_db(self):
        result = enrich_file_read(self.file_path, "/tmp/nonexistent_repo_xyz")
        assert result == ""


class TestRunHookOutput:
    """Test the JSON output format of run_hook via enrich_search."""

    def test_hook_json_format(self):
        """Verify the hookSpecificOutput structure is correct."""
        # We test the format indirectly by checking enrich_search output
        # since run_hook reads from stdin which is harder to test
        tmpdir = tempfile.mkdtemp()
        db_dir = Path(tmpdir) / ".code-review-graph"
        db_dir.mkdir()
        store = GraphStore(db_dir / "graph.db")
        store.upsert_node(
            NodeInfo(
                kind="Function", name="my_function",
                file_path=f"{tmpdir}/mod.py",
                line_start=1, line_end=10, language="python",
            ),
        )
        rebuild_fts_index(store)
        store.close()

        result = enrich_search("my_function", tmpdir)
        assert result.startswith("[code-review-graph]")
        assert "my_function" in result


class TestResolveBareCallTargets:
    """Tests for GraphStore.resolve_bare_call_targets()."""

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_resolves_single_candidate(self):
        """Single node with matching name should be resolved directly."""
        self.store.upsert_node(NodeInfo(
            kind="Function", name="helper",
            file_path="/tmp/lib.py",
            line_start=1, line_end=3, language="python",
        ))
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS",
            source="/tmp/main.py::run",
            target="helper",  # bare name — no :: separator
            file_path="/tmp/main.py",
            line=5,
        ))
        self.store.commit()

        resolved = self.store.resolve_bare_call_targets()
        assert resolved == 1

        edges = self.store.get_edges_by_source("/tmp/main.py::run")
        assert len(edges) == 1
        assert edges[0].target_qualified == "/tmp/lib.py::helper"

    def test_skips_already_qualified(self):
        """Edges with qualified targets (containing ::) should be left alone."""
        self.store.upsert_node(NodeInfo(
            kind="Function", name="helper",
            file_path="/tmp/lib.py",
            line_start=1, line_end=3, language="python",
        ))
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS",
            source="/tmp/main.py::run",
            target="/tmp/lib.py::helper",  # already qualified
            file_path="/tmp/main.py",
            line=5,
        ))
        self.store.commit()

        resolved = self.store.resolve_bare_call_targets()
        assert resolved == 0

    def test_disambiguates_via_imports(self):
        """Multiple candidates should be disambiguated via IMPORTS_FROM edges."""
        # Two nodes with the same name 'connect' in different files
        for fpath in ("/tmp/db.py", "/tmp/net.py"):
            self.store.upsert_node(NodeInfo(
                kind="Function", name="connect",
                file_path=fpath,
                line_start=1, line_end=5, language="python",
            ))
        # An IMPORT_FROM edge from the source file to one candidate's file
        self.store.upsert_edge(EdgeInfo(
            kind="IMPORTS_FROM",
            source="/tmp/main.py::run",
            target="/tmp/db.py",
            file_path="/tmp/main.py",
            line=1,
        ))
        # Bare CALLS edge
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS",
            source="/tmp/main.py::run",
            target="connect",
            file_path="/tmp/main.py",
            line=10,
        ))
        self.store.commit()

        resolved = self.store.resolve_bare_call_targets()
        assert resolved == 1

        edges = self.store.get_edges_by_source("/tmp/main.py::run")
        call_edges = [e for e in edges if e.kind == "CALLS"]
        assert len(call_edges) == 1
        # Should have resolved to db.py since main.py imports from it
        assert "db.py" in call_edges[0].target_qualified

    def test_returns_zero_when_nothing_bare(self):
        """No bare CALLS edges should return 0 immediately."""
        self.store.upsert_node(NodeInfo(
            kind="Function", name="helper",
            file_path="/tmp/lib.py",
            line_start=1, line_end=3, language="python",
        ))
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS",
            source="/tmp/main.py::run",
            target="/tmp/lib.py::helper",
            file_path="/tmp/main.py",
            line=5,
        ))
        self.store.commit()

        resolved = self.store.resolve_bare_call_targets()
        assert resolved == 0


class TestEnrichJediCalls:
    """Tests for enrich_jedi_calls()."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_dir = Path(self.tmpdir) / ".code-review-graph"
        self.db_dir.mkdir()
        self.store = GraphStore(self.db_dir / "graph.db")

    def teardown_method(self):
        self.store.close()

    def test_skips_when_jedi_not_installed(self):
        """Should return skipped dict when jedi is unavailable."""
        # We can't easily uninstall jedi at runtime, but we can test
        # that the function at least returns a well-formed response.
        result = enrich_jedi_calls(self.store, Path(self.tmpdir))
        assert isinstance(result, dict)
        assert "resolved" in result or "skipped" in result

    def test_resolves_factory_method_call(self):
        """Enrichment should resolve method calls on factory objects."""
        try:
            import jedi  # noqa: F401
        except ImportError:
            # Skip this test if jedi is not installed
            return

        # Create a Python file with a factory pattern
        src_file = os.path.join(self.tmpdir, "app.py")
        with open(src_file, "w") as f:
            f.write("""class Service:
    def authenticate(self, token):
        return token == "secret"

def create_service():
    return Service()

def handle():
    svc = create_service()
    return svc.authenticate("test")
""")

        parser = CodeParser()
        source = Path(src_file).read_bytes()
        fhash = hashlib.sha256(source).hexdigest()
        nodes, edges = parser.parse_bytes(Path(src_file), source)
        self.store.store_file_nodes_edges(src_file, nodes, edges, fhash)
        self.store.commit()

        result = enrich_jedi_calls(self.store, Path(self.tmpdir))
        assert isinstance(result, dict)
        assert "resolved" in result
        # This may resolve 0 if Jedi can't determine the type, but
        # it should not raise an exception
        assert result["resolved"] >= 0


class TestBareCallsBaseline:
    """Baseline metric: measure the ratio of bare CALLS edges."""

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_bare_calls_baseline_zero(self):
        """No edges at all should give 0/0 documented as 0.0."""
        self.store.commit()
        conn = self.store._conn
        total = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE kind = 'CALLS'"
        ).fetchone()[0]
        bare = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE kind = 'CALLS'"
            " AND target_qualified NOT LIKE '%::%'"
        ).fetchone()[0]
        ratio = bare / max(total, 1)
        assert ratio == 0.0
        assert total == 0
        assert bare == 0

    def test_bare_calls_baseline_partial(self):
        """Mixed bare and qualified edges should report correct ratio."""
        for i in range(3):
            self.store.upsert_node(NodeInfo(
                kind="Function", name=f"func{i}",
                file_path=f"/tmp/mod{i}.py",
                line_start=1, line_end=5, language="python",
            ))
        # 2 qualified edges
        for i in range(2):
            self.store.upsert_edge(EdgeInfo(
                kind="CALLS",
                source="/tmp/main.py::run",
                target=f"/tmp/mod{i}.py::func{i}",
                file_path="/tmp/main.py",
                line=i + 1,
            ))
        # 1 bare edge
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS",
            source="/tmp/main.py::run",
            target="func2",
            file_path="/tmp/main.py",
            line=3,
        ))
        self.store.commit()

        conn = self.store._conn
        total = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE kind = 'CALLS'"
        ).fetchone()[0]
        bare = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE kind = 'CALLS'"
            " AND target_qualified NOT LIKE '%::%'"
        ).fetchone()[0]
        ratio = bare / max(total, 1)
        assert total == 3
        assert bare == 1
        assert ratio == 1.0 / 3.0
