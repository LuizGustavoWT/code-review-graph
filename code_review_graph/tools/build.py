"""Tool 1: build_or_update_graph + run_postprocess."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..incremental import full_build, incremental_update
from ._common import _get_store

logger = logging.getLogger(__name__)


def _run_postprocess(
    store: Any,
    build_result: dict[str, Any],
    postprocess: str,
    full_rebuild: bool = False,
    changed_files: list[str] | None = None,
) -> list[str]:
    """Run post-build steps based on *postprocess* level.

    When *full_rebuild* is False and *changed_files* are available,
    uses incremental flow/community detection for faster updates.

    Returns a list of warning strings (empty on success).
    """
    warnings: list[str] = []
    build_result["postprocess_level"] = postprocess

    if postprocess == "none":
        return warnings

    # -- Signatures + FTS (fast, always run unless "none") --
    from ..postprocessing import _compute_signatures, _rebuild_fts_index

    _compute_signatures(store, build_result, warnings)
    _rebuild_fts_index(store, build_result, warnings)

    # -- Derived edges (on-the-fly, config-gated) --
    from ..postprocessing import _derive_edges

    _derive_edges(store, build_result, warnings)

    if postprocess == "minimal":
        return warnings

    # -- Expensive: flows + communities + summaries (only for "full") --
    from ..postprocessing import _compute_summaries, _detect_communities, _trace_flows

    use_incremental = not full_rebuild and bool(changed_files)
    inc_files = changed_files if use_incremental else None

    _trace_flows(store, build_result, warnings, changed_files=inc_files)
    _detect_communities(store, build_result, warnings, changed_files=inc_files)
    _compute_summaries(store, build_result, warnings)

    store.set_metadata(
        "last_postprocessed_at",
        time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    store.set_metadata("postprocess_level", postprocess)

    return warnings


def build_or_update_graph(
    full_rebuild: bool = False,
    repo_root: str | None = None,
    base: str = "HEAD~1",
    postprocess: str = "full",
    recurse_submodules: bool | None = None,
) -> dict[str, Any]:
    """Build or incrementally update the code knowledge graph.

    Args:
        full_rebuild: If True, re-parse every file. If False (default),
                      only re-parse files changed since ``base``.
        repo_root: Path to the repository root. Auto-detected if omitted.
        base: Git ref for incremental diff (default: HEAD~1).
        postprocess: Post-processing level after build:
            ``"full"`` (default) — signatures, FTS, flows, communities.
            ``"minimal"`` — signatures + FTS only (fast, keeps search working).
            ``"none"`` — skip all post-processing (raw parse only).
        recurse_submodules: If True, include files from git submodules
            via ``git ls-files --recurse-submodules``. When None
            (default), falls back to the CRG_RECURSE_SUBMODULES
            environment variable. Default: disabled.

    Returns:
        Summary with files_parsed/updated, node/edge counts, and errors.
    """
    store, root = _get_store(repo_root)
    try:
        if full_rebuild:
            result = full_build(root, store, recurse_submodules)
            build_result = {
                "status": "ok",
                "build_type": "full",
                "summary": (
                    f"Full build complete: parsed {result['files_parsed']} files, "
                    f"created {result['total_nodes']} nodes and "
                    f"{result['total_edges']} edges."
                ),
                **result,
            }
        else:
            result = incremental_update(root, store, base=base)
            if result["files_updated"] == 0:
                return {
                    "status": "ok",
                    "build_type": "incremental",
                    "summary": "No changes detected. Graph is up to date.",
                    "postprocess_level": postprocess,
                    **result,
                }
            build_result = {
                "status": "ok",
                "build_type": "incremental",
                "summary": (
                    f"Incremental update: {result['files_updated']} files re-parsed, "
                    f"{result['total_nodes']} nodes and "
                    f"{result['total_edges']} edges updated. "
                    f"Changed: {result['changed_files']}. "
                    f"Dependents also updated: {result['dependent_files']}."
                ),
                **result,
            }

        # Pass changed_files for incremental flow/community detection
        changed = result.get("changed_files") if not full_rebuild else None
        warnings = _run_postprocess(
            store,
            build_result,
            postprocess,
            full_rebuild=full_rebuild,
            changed_files=changed,
        )
        if warnings:
            build_result["warnings"] = warnings
        return build_result
    finally:
        store.close()


def run_postprocess(
    flows: bool = True,
    communities: bool = True,
    fts: bool = True,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Run post-processing steps on an existing graph.

    Useful for running expensive steps (flows, communities) separately
    from the build, or for re-running after the graph has been updated
    with ``postprocess="none"``.

    Args:
        flows: Run flow detection. Default: True.
        communities: Run community detection. Default: True.
        fts: Rebuild FTS index. Default: True.
        repo_root: Repository root path. Auto-detected if omitted.

    Returns:
        Summary of what was computed.
    """
    store, _root = _get_store(repo_root)
    result: dict[str, Any] = {"status": "ok"}
    warnings: list[str] = []

    try:
        from ..postprocessing import _compute_signatures

        _compute_signatures(store, result, warnings)

        if fts:
            from ..postprocessing import _rebuild_fts_index

            _rebuild_fts_index(store, result, warnings)

        if flows:
            from ..postprocessing import _trace_flows

            _trace_flows(store, result, warnings)

        if communities:
            from ..postprocessing import _detect_communities

            _detect_communities(store, result, warnings)

        store.set_metadata(
            "last_postprocessed_at",
            time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        result["summary"] = "Post-processing complete."
        if warnings:
            result["warnings"] = warnings
        return result
    finally:
        store.close()
