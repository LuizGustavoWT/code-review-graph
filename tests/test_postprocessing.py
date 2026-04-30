"""Tests for the shared post-processing pipeline."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from code_review_graph.graph import GraphStore
from code_review_graph.incremental import full_build
from code_review_graph.parser import EdgeInfo, NodeInfo
from code_review_graph.postprocessing import run_post_processing


def _get_signature(store, qualified_name):
    row = store._conn.execute(
        "SELECT signature FROM nodes WHERE qualified_name = ?",
        (qualified_name,),
    ).fetchone()
    return row["signature"] if row else None


class TestRunPostProcessing:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)
        self._seed_data()

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def _seed_data(self):
        self.store.upsert_node(
            NodeInfo(
                kind="File",
                name="/repo/app.py",
                file_path="/repo/app.py",
                line_start=1,
                line_end=50,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Class",
                name="Service",
                file_path="/repo/app.py",
                line_start=5,
                line_end=40,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="handle",
                file_path="/repo/app.py",
                line_start=10,
                line_end=20,
                language="python",
                parent_name="Service",
                params="request",
                return_type="Response",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="process",
                file_path="/repo/app.py",
                line_start=25,
                line_end=35,
                language="python",
            )
        )
        self.store.upsert_node(
            NodeInfo(
                kind="Test",
                name="test_handle",
                file_path="/repo/test_app.py",
                line_start=1,
                line_end=10,
                language="python",
                is_test=True,
            )
        )

        self.store.upsert_edge(
            EdgeInfo(
                kind="CONTAINS",
                source="/repo/app.py",
                target="/repo/app.py::Service",
                file_path="/repo/app.py",
            )
        )
        self.store.upsert_edge(
            EdgeInfo(
                kind="CONTAINS",
                source="/repo/app.py::Service",
                target="/repo/app.py::Service.handle",
                file_path="/repo/app.py",
            )
        )
        self.store.upsert_edge(
            EdgeInfo(
                kind="CALLS",
                source="/repo/app.py::Service.handle",
                target="/repo/app.py::process",
                file_path="/repo/app.py",
                line=15,
            )
        )
        self.store.commit()

    def test_computes_signatures(self):
        unsigned = self.store.get_nodes_without_signature()
        assert len(unsigned) > 0

        result = run_post_processing(self.store)

        assert result["signatures_computed"] > 0
        remaining = self.store.get_nodes_without_signature()
        assert len(remaining) == 0

    def test_function_signature_format(self):
        run_post_processing(self.store)

        sig = _get_signature(self.store, "/repo/app.py::Service.handle")
        assert sig == "def handle(request) -> Response"

    def test_class_signature_format(self):
        run_post_processing(self.store)

        sig = _get_signature(self.store, "/repo/app.py::Service")
        assert sig == "class Service"

    def test_test_signature_format(self):
        run_post_processing(self.store)

        sig = _get_signature(self.store, "/repo/test_app.py::test_handle")
        assert sig is not None
        assert sig.startswith("def test_handle(")

    def test_rebuilds_fts_index(self):
        result = run_post_processing(self.store)

        assert "fts_indexed" in result
        assert result["fts_indexed"] > 0

    def test_fts_search_works_after_post_processing(self):
        run_post_processing(self.store)

        from code_review_graph.search import hybrid_search

        hits = hybrid_search(self.store, "handle")
        names = {h["name"] for h in hits}
        assert "handle" in names

    def test_detects_flows(self):
        result = run_post_processing(self.store)

        assert "flows_detected" in result
        assert result["flows_detected"] >= 0

    def test_detects_communities(self):
        result = run_post_processing(self.store)

        assert "communities_detected" in result
        assert result["communities_detected"] >= 0

    def test_no_warnings_on_healthy_store(self):
        result = run_post_processing(self.store)

        assert "warnings" not in result

    def test_empty_store_no_crash(self):
        empty_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        empty_store = GraphStore(empty_tmp.name)
        try:
            result = run_post_processing(empty_store)
            assert result["signatures_computed"] == 0
            assert result["fts_indexed"] == 0
        finally:
            empty_store.close()
            Path(empty_tmp.name).unlink(missing_ok=True)

    def test_idempotent(self):
        first = run_post_processing(self.store)
        second = run_post_processing(self.store)

        assert second["fts_indexed"] == first["fts_indexed"]
        assert second["signatures_computed"] == 0

    def test_signature_truncated_at_512(self):
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="f",
                file_path="/repo/big.py",
                line_start=1,
                line_end=2,
                language="python",
                params="a" * 600,
            )
        )
        self.store.commit()

        run_post_processing(self.store)
        sig = _get_signature(self.store, "/repo/big.py::f")
        assert sig is not None
        assert len(sig) <= 512


class TestPostProcessingStepIsolation:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)
        self.store.upsert_node(
            NodeInfo(
                kind="Function",
                name="fn",
                file_path="/repo/a.py",
                line_start=1,
                line_end=5,
                language="python",
            )
        )
        self.store.commit()

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_fts_failure_does_not_block_flows(self):
        with patch(
            "code_review_graph.search.rebuild_fts_index",
            side_effect=ImportError("fts boom"),
        ):
            result = run_post_processing(self.store)

        assert "flows_detected" in result
        assert "communities_detected" in result
        assert "warnings" in result
        assert any("FTS" in w for w in result["warnings"])

    def test_flow_failure_does_not_block_communities(self):
        with patch(
            "code_review_graph.flows.trace_flows",
            side_effect=ImportError("flow boom"),
        ):
            result = run_post_processing(self.store)

        assert "communities_detected" in result
        assert "warnings" in result
        assert any("Flow" in w for w in result["warnings"])

    def test_community_failure_still_has_signatures(self):
        with patch(
            "code_review_graph.communities.detect_communities",
            side_effect=ImportError("comm boom"),
        ):
            result = run_post_processing(self.store)

        assert result["signatures_computed"] > 0
        assert "warnings" in result
        assert any("Community" in w for w in result["warnings"])


class TestToolBuildUsesSharedPipeline:
    def test_build_tool_runs_post_processing(self, tmp_path):
        py_file = tmp_path / "sample.py"
        py_file.write_text("def hello():\n    pass\n")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".code-review-graph").mkdir()

        db_path = tmp_path / ".code-review-graph" / "graph.db"
        store = GraphStore(db_path)
        try:
            mock_target = "code_review_graph.incremental.get_all_tracked_files"
            with patch(mock_target, return_value=["sample.py"]):
                full_build(tmp_path, store)

            unsigned_before_pp = store.get_nodes_without_signature()
            run_post_processing(store)
            unsigned_after_pp = store.get_nodes_without_signature()

            assert len(unsigned_before_pp) > 0
            assert len(unsigned_after_pp) == 0
        finally:
            store.close()


class TestWatchCallbackIntegration:
    def test_watch_accepts_callback_parameter(self):
        import inspect

        from code_review_graph.incremental import watch

        sig = inspect.signature(watch)
        assert "on_files_updated" in sig.parameters

    def test_watch_callback_not_called_without_updates(self, tmp_path):
        import threading

        from code_review_graph.incremental import watch

        (tmp_path / ".git").mkdir()
        db_path = tmp_path / "test.db"
        store = GraphStore(db_path)
        callback = MagicMock()

        try:

            def run_watch():
                try:
                    watch(tmp_path, store, on_files_updated=callback)
                except KeyboardInterrupt:
                    pass

            t = threading.Thread(target=run_watch, daemon=True)
            t.start()

            import time

            time.sleep(0.5)
            callback.assert_not_called()
        finally:
            store.close()


class TestDerivedEdges:
    """Tests for on-the-fly derived edge computation (CLASS_USES, MODULE_DEPENDS_ON)."""

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = GraphStore(self.tmp.name)

    def teardown_method(self):
        self.store.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_class_uses_derivation(self):
        """Class A.foo() calls B.bar() → CLASS_USES A → B."""
        # File nodes
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/a.py", file_path="/repo/a.py",
            line_start=1, line_end=20, language="python",
        ))
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/b.py", file_path="/repo/b.py",
            line_start=1, line_end=20, language="python",
        ))
        # Class A
        self.store.upsert_node(NodeInfo(
            kind="Class", name="A", file_path="/repo/a.py",
            line_start=3, line_end=18, language="python",
        ))
        # Class B
        self.store.upsert_node(NodeInfo(
            kind="Class", name="B", file_path="/repo/b.py",
            line_start=3, line_end=18, language="python",
        ))
        # Method A.foo
        self.store.upsert_node(NodeInfo(
            kind="Function", name="foo", file_path="/repo/a.py",
            line_start=5, line_end=15, language="python",
            parent_name="A",
        ))
        # Method B.bar
        self.store.upsert_node(NodeInfo(
            kind="Function", name="bar", file_path="/repo/b.py",
            line_start=5, line_end=15, language="python",
            parent_name="B",
        ))
        # CONTAINS edges
        self.store.upsert_edge(EdgeInfo(
            kind="CONTAINS", source="/repo/a.py::A",
            target="/repo/a.py::A.foo", file_path="/repo/a.py",
        ))
        self.store.upsert_edge(EdgeInfo(
            kind="CONTAINS", source="/repo/b.py::B",
            target="/repo/b.py::B.bar", file_path="/repo/b.py",
        ))
        # CALLS: A.foo → B.bar
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS", source="/repo/a.py::A.foo",
            target="/repo/b.py::B.bar", file_path="/repo/a.py",
            line=10,
        ))
        self.store.commit()

        used = self.store.get_class_uses("/repo/a.py::A")
        assert "/repo/b.py::B" in used
        assert len(used) == 1

    def test_class_uses_self_reference_omitted(self):
        """Self-calls within a class are excluded from CLASS_USES."""
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/a.py", file_path="/repo/a.py",
            line_start=1, line_end=20, language="python",
        ))
        self.store.upsert_node(NodeInfo(
            kind="Class", name="A", file_path="/repo/a.py",
            line_start=3, line_end=18, language="python",
        ))
        self.store.upsert_node(NodeInfo(
            kind="Function", name="foo", file_path="/repo/a.py",
            line_start=5, line_end=10, language="python",
            parent_name="A",
        ))
        self.store.upsert_node(NodeInfo(
            kind="Function", name="bar", file_path="/repo/a.py",
            line_start=12, line_end=17, language="python",
            parent_name="A",
        ))
        self.store.upsert_edge(EdgeInfo(
            kind="CONTAINS", source="/repo/a.py::A",
            target="/repo/a.py::A.foo", file_path="/repo/a.py",
        ))
        self.store.upsert_edge(EdgeInfo(
            kind="CONTAINS", source="/repo/a.py::A",
            target="/repo/a.py::A.bar", file_path="/repo/a.py",
        ))
        # Self-call: A.foo → A.bar
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS", source="/repo/a.py::A.foo",
            target="/repo/a.py::A.bar", file_path="/repo/a.py",
            line=8,
        ))
        self.store.commit()

        used = self.store.get_class_uses("/repo/a.py::A")
        assert used == []

    def test_module_depends_derivation(self):
        """File A imports File B + calls function in File B → MODULE_DEPENDS_ON."""
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/a.py", file_path="/repo/a.py",
            line_start=1, line_end=20, language="python",
        ))
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/b.py", file_path="/repo/b.py",
            line_start=1, line_end=20, language="python",
        ))
        # Function a_func in a.py
        self.store.upsert_node(NodeInfo(
            kind="Function", name="a_func", file_path="/repo/a.py",
            line_start=5, line_end=15, language="python",
        ))
        # Function b_func in b.py
        self.store.upsert_node(NodeInfo(
            kind="Function", name="b_func", file_path="/repo/b.py",
            line_start=5, line_end=15, language="python",
        ))
        # IMPORTS_FROM: a.py → b.py
        self.store.upsert_edge(EdgeInfo(
            kind="IMPORTS_FROM", source="/repo/a.py",
            target="/repo/b.py", file_path="/repo/a.py",
        ))
        # CALLS: a_func → b_func (cross-file)
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS", source="/repo/a.py::a_func",
            target="/repo/b.py::b_func", file_path="/repo/a.py",
            line=10,
        ))
        self.store.commit()

        deps = self.store.get_module_dependencies("/repo/a.py")
        assert "/repo/b.py" in deps

    def test_module_depends_both_paths(self):
        """File depends on another via import AND via call (deduplicated)."""
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/a.py", file_path="/repo/a.py",
            line_start=1, line_end=30, language="python",
        ))
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/b.py", file_path="/repo/b.py",
            line_start=1, line_end=20, language="python",
        ))
        self.store.upsert_node(NodeInfo(
            kind="File", name="/repo/c.py", file_path="/repo/c.py",
            line_start=1, line_end=20, language="python",
        ))
        # Function a_func
        self.store.upsert_node(NodeInfo(
            kind="Function", name="a_func", file_path="/repo/a.py",
            line_start=5, line_end=25, language="python",
        ))
        # Function b_func
        self.store.upsert_node(NodeInfo(
            kind="Function", name="b_func", file_path="/repo/b.py",
            line_start=5, line_end=15, language="python",
        ))
        # Function c_func
        self.store.upsert_node(NodeInfo(
            kind="Function", name="c_func", file_path="/repo/c.py",
            line_start=5, line_end=15, language="python",
        ))
        # IMPORTS_FROM: a.py → b.py (explicit import)
        self.store.upsert_edge(EdgeInfo(
            kind="IMPORTS_FROM", source="/repo/a.py",
            target="/repo/b.py", file_path="/repo/a.py",
        ))
        # CALLS: a_func → b_func
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS", source="/repo/a.py::a_func",
            target="/repo/b.py::b_func", file_path="/repo/a.py",
            line=10,
        ))
        # CALLS: a_func → c_func (cross-file, no explicit import)
        self.store.upsert_edge(EdgeInfo(
            kind="CALLS", source="/repo/a.py::a_func",
            target="/repo/c.py::c_func", file_path="/repo/a.py",
            line=15,
        ))
        self.store.commit()

        deps = self.store.get_module_dependencies("/repo/a.py")
        assert "/repo/b.py" in deps
        assert "/repo/c.py" in deps
