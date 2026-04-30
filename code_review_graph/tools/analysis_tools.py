"""MCP tool wrappers for graph analysis features."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..analysis import (
    find_bridge_nodes,
    find_hub_nodes,
    find_knowledge_gaps,
    find_surprising_connections,
    generate_suggested_questions,
)
from ..constants import EdgeKind
from ..graph import GraphNode
from ._common import _get_store


def get_hub_nodes_func(
    repo_root: str = "",
    top_n: int = 10,
) -> dict[str, Any]:
    """Find the most connected nodes in the codebase graph.

    Hub nodes have the highest total degree (in + out edges).
    These are architectural hotspots -- changes to them have
    disproportionate blast radius.

    Args:
        repo_root: Repository root (auto-detected if empty).
        top_n: Number of top hubs to return (default 10).
    """
    store, _root = _get_store(repo_root or None)
    hubs = find_hub_nodes(store, top_n=top_n)
    return {
        "hub_nodes": hubs,
        "count": len(hubs),
        "next_tool_suggestions": [
            "get_impact_radius -- check blast radius of a hub",
            "query_graph callers_of -- see what calls a hub",
            "get_bridge_nodes -- find architectural chokepoints",
        ],
    }


def get_bridge_nodes_func(
    repo_root: str = "",
    top_n: int = 10,
) -> dict[str, Any]:
    """Find architectural chokepoints via betweenness centrality.

    Bridge nodes sit on the shortest paths between many node
    pairs. If they break, multiple code regions lose
    connectivity.

    Args:
        repo_root: Repository root (auto-detected if empty).
        top_n: Number of top bridges to return (default 10).
    """
    store, _root = _get_store(repo_root or None)
    bridges = find_bridge_nodes(store, top_n=top_n)
    return {
        "bridge_nodes": bridges,
        "count": len(bridges),
        "next_tool_suggestions": [
            "get_hub_nodes -- find most connected nodes",
            "get_impact_radius -- check blast radius",
            "detect_changes -- see if bridges are affected",
        ],
    }


def get_knowledge_gaps_func(
    repo_root: str = "",
) -> dict[str, Any]:
    """Identify structural weaknesses in the codebase.

    Finds: isolated nodes (disconnected), thin communities
    (< 3 members), untested hotspots (high-degree, no tests),
    and single-file communities.

    Args:
        repo_root: Repository root (auto-detected if empty).
    """
    store, _root = _get_store(repo_root or None)
    gaps = find_knowledge_gaps(store)
    total = sum(len(v) for v in gaps.values())
    return {
        "gaps": gaps,
        "total_gaps": total,
        "summary": {
            "isolated_nodes": len(gaps["isolated_nodes"]),
            "thin_communities": len(
                gaps["thin_communities"]
            ),
            "untested_hotspots": len(
                gaps["untested_hotspots"]
            ),
            "single_file_communities": len(
                gaps["single_file_communities"]
            ),
        },
        "next_tool_suggestions": [
            "refactor dead_code -- find unused symbols",
            "get_hub_nodes -- find high-impact nodes",
            "get_suggested_questions -- review prompts",
        ],
    }


def get_surprising_connections_func(
    repo_root: str = "",
    top_n: int = 15,
) -> dict[str, Any]:
    """Find unexpected architectural coupling in the codebase.

    Scores edges by surprise factors: cross-community,
    cross-language, peripheral-to-hub, cross-test-boundary.

    Args:
        repo_root: Repository root (auto-detected if empty).
        top_n: Number of top surprises to return (default 15).
    """
    store, _root = _get_store(repo_root or None)
    surprises = find_surprising_connections(
        store, top_n=top_n
    )
    return {
        "surprising_connections": surprises,
        "count": len(surprises),
        "next_tool_suggestions": [
            "get_architecture_overview -- community structure",
            "query_graph callers_of -- trace the coupling",
            "get_bridge_nodes -- find chokepoints",
        ],
    }


def get_suggested_questions_func(
    repo_root: str = "",
) -> dict[str, Any]:
    """Auto-generate review questions from graph analysis.

    Produces questions about: bridge nodes, untested hubs,
    surprising connections, thin communities, and untested
    hotspots.

    Args:
        repo_root: Repository root (auto-detected if empty).
    """
    store, _root = _get_store(repo_root or None)
    questions = generate_suggested_questions(store)
    by_priority: dict[str, list[dict[str, Any]]] = {
        "high": [], "medium": [], "low": [],
    }
    for q in questions:
        prio = q.get("priority", "medium")
        if prio in by_priority:
            by_priority[prio].append(q)
    return {
        "questions": questions,
        "count": len(questions),
        "by_priority": {
            k: len(v) for k, v in by_priority.items()
        },
        "next_tool_suggestions": [
            "get_knowledge_gaps -- structural weaknesses",
            "detect_changes -- risk-scored review",
            "get_architecture_overview -- community map",
        ],
    }


def dependency_matrix(
    scope: str = "",
    mode: str = "class_level",
    depth: int = 1,
    repo_root: str = "",
) -> dict[str, Any]:
    """Compute a dependency matrix for classes or modules in the given scope.

    Args:
        scope: File path prefix or class name to filter by.
        mode: "class_level" or "module_level".
        depth: Dependency traversal depth (1-3). Default 1 (direct only).
        repo_root: Repository root (auto-detected if empty).
    """
    store, _root = _get_store(repo_root or None)
    try:
        depth = max(1, min(depth, 3))
        scope_is_path = "/" in scope or "\\" in scope
        entities: list[GraphNode] = []

        if mode == "class_level":
            if scope_is_path:
                for file_path in store.get_all_files():
                    if file_path.startswith(scope):
                        for node in store.get_nodes_by_file(file_path):
                            if node.kind == "Class":
                                entities.append(node)
            elif scope:
                candidates = store.search_nodes(scope, limit=50)
                entities = [n for n in candidates if n.kind == "Class"]
            else:
                for file_path in store.get_all_files():
                    for node in store.get_nodes_by_file(file_path):
                        if node.kind == "Class":
                            entities.append(node)
        else:
            if scope:
                for file_path in store.get_all_files():
                    if file_path.startswith(scope):
                        node = store.get_node(file_path)
                        if node:
                            entities.append(node)
            else:
                for file_path in store.get_all_files():
                    node = store.get_node(file_path)
                    if node:
                        entities.append(node)

        truncated = False
        if len(entities) > 500:
            entities = entities[:500]
            truncated = True

        direct_deps: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        if mode == "class_level":
            for cls in entities:
                methods = []
                for e in store.get_edges_by_source(cls.qualified_name):
                    if e.kind == EdgeKind.CONTAINS:
                        child = store.get_node(e.target_qualified)
                        if child and child.kind in ("Function", "Method"):
                            methods.append(e.target_qualified)
                for method_qn in methods:
                    for e in store.get_edges_by_source(method_qn):
                        if e.kind == EdgeKind.CALLS:
                            callee_class = None
                            for ce in store.get_edges_by_target(e.target_qualified):
                                if ce.kind == EdgeKind.CONTAINS:
                                    container = store.get_node(ce.source_qualified)
                                    if container and container.kind == "Class":
                                        callee_class = ce.source_qualified
                                        break
                            if callee_class and callee_class != cls.qualified_name:
                                direct_deps[cls.qualified_name][callee_class] += 1
        else:
            for file_node in entities:
                for e in store.get_edges_by_source(file_node.qualified_name):
                    if e.kind == EdgeKind.IMPORTS_FROM:
                        target_fp = e.target_qualified
                        if target_fp and target_fp != file_node.qualified_name:
                            direct_deps[file_node.qualified_name][target_fp] += 1
                for node in store.get_nodes_by_file(file_node.qualified_name):
                    for e in store.get_edges_by_source(node.qualified_name):
                        if e.kind in (EdgeKind.CALLS, EdgeKind.IMPORTS_FROM):
                            target_node = store.get_node(e.target_qualified)
                            target_fp = target_node.file_path if target_node else None
                            if target_fp and target_fp != file_node.qualified_name:
                                direct_deps[file_node.qualified_name][target_fp] += 1

        matrix: list[dict] = []
        visited_pairs: set[tuple[str, str]] = set()

        for src in list(direct_deps.keys()):
            queue = [(src, 0)]
            visited = {src}
            while queue:
                current, cur_depth = queue.pop(0)
                if cur_depth >= depth:
                    continue
                for tgt, strength in direct_deps.get(current, {}).items():
                    pair = (src, tgt)
                    if pair not in visited_pairs:
                        visited_pairs.add(pair)
                        matrix.append({
                            "source": src,
                            "target": tgt,
                            "strength": strength if current == src else 1,
                        })
                    else:
                        for entry in matrix:
                            if entry["source"] == src and entry["target"] == tgt:
                                if current == src:
                                    entry["strength"] += strength
                                break
                    if tgt not in visited and cur_depth + 1 < depth:
                        visited.add(tgt)
                        queue.append((tgt, cur_depth + 1))

        total_entities = len(entities)
        if total_entities == 0:
            return {
                "status": "ok",
                "mode": mode,
                "scope": scope,
                "matrix": [],
                "coupling_score": 0.0,
                "hub_classes" if mode == "class_level" else "hub_modules": [],
                "leaf_classes" if mode == "class_level" else "leaf_modules": [],
                "truncated": truncated,
            }

        outgoing_counts: dict[str, int] = {}
        incoming_counts: dict[str, int] = {}
        for entry in matrix:
            src = entry["source"]
            tgt = entry["target"]
            outgoing_counts[src] = outgoing_counts.get(src, 0) + 1
            incoming_counts[tgt] = incoming_counts.get(tgt, 0) + 1

        all_entities_qn = {e.qualified_name for e in entities}
        connected = set(outgoing_counts.keys()) | set(incoming_counts.keys())
        hub_scores = {
            qn: outgoing_counts.get(qn, 0) + incoming_counts.get(qn, 0)
            for qn in all_entities_qn
        }
        sorted_hubs = sorted(hub_scores.items(), key=lambda x: x[1], reverse=True)
        leaves = [qn for qn in all_entities_qn if qn not in outgoing_counts]
        coupling_score = len(connected) / total_entities if total_entities > 0 else 0.0

        hub_key = "hub_classes" if mode == "class_level" else "hub_modules"
        leaf_key = "leaf_classes" if mode == "class_level" else "leaf_modules"

        return {
            "status": "ok",
            "mode": mode,
            "scope": scope,
            "matrix": matrix,
            "coupling_score": round(coupling_score, 3),
            hub_key: [{"name": qn, "score": score} for qn, score in sorted_hubs[:10]],
            leaf_key: leaves,
            "truncated": truncated,
        }
    finally:
        store.close()
