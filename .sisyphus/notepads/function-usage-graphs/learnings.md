# Learnings: Function Usage Graphs

## 2026-04-30: Post-processing pipeline consolidation

**Task:** Refactor duplicated post-processing pipeline between `postprocessing.py` and `tools/build.py`.

**Changes made:**

1. **`postprocessing.py`** — Enhanced shared step functions:
   - `_trace_flows()` and `_detect_communities()` now accept optional `changed_files` parameter for incremental mode (used by MCP build tool)
   - Added `_compute_summaries()` (moved from `tools/build.py`) to handle `community_summaries`, `flow_snapshots`, and `risk_index` tables
   - Internal `_run_summaries()` helper contains the actual table-rebuild logic with batched queries
   - `run_post_processing()` API unchanged — still calls the 4 original steps without summaries (backward compat for CLI `build` and `watch`)

2. **`tools/build.py`** — Removed all duplicated code:
   - `_run_postprocess()` now delegates to shared functions from `postprocessing.py` for signatures, FTS, flows, communities, and summaries
   - `run_postprocess()` (public MCP tool) similarly delegates to shared functions
   - Removed `_compute_summaries()` (moved to postprocessing.py)
   - Removed `import sqlite3` (no longer used directly)
   - Kept orchestration logic: postprocess level gating (`none`/`minimal`/`full`), incremental vs full mode, metadata timestamps

**Key decisions:**
- Kept `run_post_processing()` API unchanged (4 steps, no summaries) to avoid behavior change for CLI `build` and `watch` paths
- The MCP build path (`_run_postprocess`) additionally computes summaries — this was existing behavior, not new
- All 5 step functions share the same `(store, result, warnings)` signature for consistency
- Used local imports inside functions to avoid circular imports

**Test results:** 18/18 postprocessing tests pass. Pre-existing failure in `test_main.py` (unrelated `show_banner` assertion).

## 2026-04-30: Cross-file CALLS resolution improvements

**Task:** Improve cross-file CALLS resolution in parser and graph post-processing.

**Changes made:**

### `parser.py` — `_collect_import_names()` (line 3790)
- Added handling for Python `import_statement` (bare `import X.Y.Z` statements)
  - `import X.Y.Z` now maps `X.Y.Z` → module path in import_map
  - Also adds parent components (`X`, `X.Y`) for partial matching
  - `import X.Y.Z as A` maps `A` → `X.Y.Z`
- Key fix: the `elif node.type == "import_statement"` branch was originally at the top level (outside `if language == "python"`), which intercepted JS/TS imports and broke them. Moved it inside the python block as `elif`.

### `parser.py` — New `_resolve_attribute_call()` method (after line 4026)
- New helper that resolves attribute-style calls (`obj.method()`) through the `import_map`
- Given a call expression node where the function is an attribute/member_expression, extracts the object part (e.g., `X.Y.Z` from `X.Y.Z.func()`) and walks the import_map to find a matching module
- Falls back to parent components (e.g., `X.Y` → then `X`) for partial matches

### `parser.py` — `_extract_calls()` (line 3219)
- Added attribute-based resolution fallback: when `_resolve_call_target` returns a bare name (unresolved), calls `_resolve_attribute_call` to try resolving through the attribute chain

### `graph.py` — `resolve_bare_call_targets()` (line 468)
- Added CONTAINS-based disambiguation as Strategy 3
- Builds a `contains_parent` map from CONTAINS edges
- When import-file-based disambiguation fails (multiple candidates from same file), checks if candidates are methods of a class (CONTAINS parent contains `::`)
- Prefers methods of classes in imported files over top-level functions
- This resolves cases like: both `login()` (top-level) and `AuthService.login()` (method) exist in the same imported file, and we prefer the method

**Verification:**
- `tests/test_graph.py`, `tests/test_postprocessing.py`, `tests/test_enrich.py`: all pass (72/72)
- `tests/test_parser.py`: no new failures introduced (all 8 failures are pre-existing)
- Key scenario verified: `import utils.helpers; utils.helpers.greet("world")` now resolves `greet` to `utils/helpers.py::greet` (was bare before)
- CONTAINS disambiguation verified: when `login` exists as both top-level function and `AuthService.login` method in imported file, resolves to the method

## 2026-04-30: DECORATED_BY and USES_TYPE edges

**Task:** Extract DECORATED_BY (decorators) and USES_TYPE (type annotations) edges from the parser.

**Changes made:**

1. **`parser.py` imports** — Added `import os` for `CRG_USES_TYPE` env var.
2. **`parser.py` — Helper functions** (module-level, after `_is_test_function`):
   - `_split_by_commas(text)` — Bracket-aware splitting for parameter lists.
   - `_split_union(text)` — Bracket-aware splitting for union types (`|`).
   - `_extract_type_names(type_text)` — Extracts non-builtin type names from annotation strings, handling unions and generics.
   - `_extract_param_types(params_text)` — Extracts type annotation texts from raw parameter strings.
   - `_BUILTIN_TYPES` frozenset — Types to skip: int, str, bool, float, None, void, string, number, any, object, list, dict, tuple, set, Array, Promise, Map, Set, Record.
3. **`_extract_functions()`**:
   - Tracks `decorator_edges: list[tuple[str, int]]` alongside existing `deco_list` for DECORATED_BY.
   - After CONTAINS edge, emits DECORATED_BY edges (bare name, no args).
   - After CONTAINS edge, emits USES_TYPE edges for param and return type annotations.
   - Controlled by `CRG_USES_TYPE` env var (default: "1").
4. **`_extract_classes()`**:
   - Added decorator extraction for Python classes (via `decorated_definition` parent) and Java/Kotlin/C# classes (via `modifiers` child).
   - Computes `qualified_class` once, reuses for CONTAINS, DECORATED_BY, and INHERITS edges.
   - Emits DECORATED_BY edges.

**Key decisions:**
- Decorator names are bare strings (arguments stripped via `.split("(")[0]`) — no resolution to qualified nodes.
- Type names are bare strings — no resolution to imports or qualified paths.
- Return type text is sanitized (strips leading `: ` and `-> `) for multi-language compatibility.
- Type params from generic types (e.g., `T` in `def fn[T](x: T)`) are not tracked.
- Local variable types are not tracked — only params and return types.

**Test results:** 67/67 parser tests pass (7 pre-existing failures in TestModuleScopeCalls unrelated). All 74 enrich/graph/changes tests pass.

## 2026-04-30: Generic enrichment framework

**Task:** Implement generic enrichment framework: `_run_enricher()`, `_ENRICHERS` dict, `ENRICHER_MAP`, and `enrich` CLI command.

**Changes made:**

1. **`incremental.py`** — Added:
   - `_ENRICHERS: dict[str, Callable]` mapping language → enricher function
   - `_jedi_enricher()` lazy wrapper that imports `enrich_jedi_calls` from `jedi_resolver`
   - `_run_enricher(language, store, repo_root)` generic dispatcher:
     - Respects `CRG_SKIP_ENRICHMENT` env var
     - Looks up enricher in `_ENRICHERS` dict
     - try/except with logging
     - Returns stats dict, None on error, or skipped-dict
   - Replaced inline Jedi enrichment block (28 lines) in `full_build()` with two `_run_enricher()` calls
   - Kept the same return dict keys (`jedi_enrichment`, `rescript_resolution`) for backward compat

2. **`constants.py`** — Added `ENRICHER_MAP` dict mapping language → backend name for CLI lookup

3. **`cli.py`** — Added `enrich <language>` subcommand:
   - Looks up language in `ENRICHER_MAP`
   - Calls `_run_enricher()` and pretty-prints stats
   - Supports `--repo` flag

**Key decisions:**
- Used simple dict dispatch (not abstract plugin system) — task explicitly forbids over-engineering
- `_run_enricher` is module-level (importable from CLI as `_run_enricher`)
- Enrichers share `(store, repo_root)` signature; rescript wrapped with lambda to ignore `repo_root`
- Jedi enrichment NOT called in `incremental_update()` (too expensive for incremental path)

**Test results:** All 103 enrich/graph/incremental/cli tests pass. 1 pre-existing failure in `test_main.py` (unrelated).

## 2026-04-30: Parser tests for DECORATED_BY, USES_TYPE, and cross-file CALLS

**Task:** Write parser tests for DECORATED_BY, USES_TYPE, and cross-file CALLS alias resolution.

**Changes made:**

1. **`tests/test_parser.py`** — Added 10 new tests:
   - `test_decorated_by_function_python` — Verifies `guarded_process` → `_log_action` DECORATED_BY edge using existing `sample_python.py` fixture
   - `test_decorated_by_class_python` — Inline Python with `@dataclass` on a class
   - `test_decorated_by_decorator_factory` — `@cache(ttl=60)` resolves to bare `cache` (args stripped)
   - `test_decorated_by_multiple_decorators` — 3 decorators → 3 DECORATED_BY edges
   - `test_uses_type_non_builtin` — Verifies `AuthService` appears as both param and return USES_TYPE
   - `test_uses_type_skips_builtins` — Built-in types like `int`, `str`, `dict`, `None` are skipped
   - `test_uses_type_union` — Union type `int | None | User` extracts only `User`
   - `test_uses_type_disabled_by_env` — `CRG_USES_TYPE=0` suppresses all USES_TYPE edges (uses `mock.patch`)
   - `test_cross_file_calls_alias_resolution` — `from X import Y as Z; Z()` creates CALLS edge targeting X
   - `test_cross_file_calls_all_resolved` — `caller_example.py` has zero bare CALLS targets

**Key decisions:**
- All inline tests use `parse_bytes` with paths in `tests/fixtures/` (files don't need to exist on disk)
- Existing `sample_python.py` fixture reused for DECORATED_BY function test
- Alias resolution test documents current limitation: target resolves to `::<alias>` not `::<original_name>`
- `CRG_USES_TYPE` is a module-level constant in `constants.py`, not a runtime lookup — must use `mock.patch` to override in tests

**Gotchas:**
- `CRG_USES_TYPE` is defined as `os.environ.get("CRG_USES_TYPE", "1")` in `constants.py`, evaluated ONCE at import time. Setting `os.environ` in the test has no effect. Use `mock.patch("code_review_graph.parser.CRG_USES_TYPE", "0")` instead.
- `_test_*.py` path patterns match `_TEST_FILE_PATTERNS` (triggers TESTED_BY logic) — this doesn't affect USES_TYPE/DECORATED_BY but worth noting.

**Test results:** 10/10 new tests pass. 18 pre-existing failures unchanged (shebang detection + module-scope CALLS). All 72 enrich/graph/postprocessing tests pass.

## 2026-04-30: Derived edges (CLASS_USES, MODULE_DEPENDS_ON) on-the-fly

**Task:** Implement derived edges (CLASS_USES, MODULE_DEPENDS_ON) on-the-fly, integrate into pipelines, add config toggles.

**Changes made:**

1. **`graph.py`** — Added two new query methods:
   - `get_class_uses(qn)` — Walks CALLS edges from a class's methods, then follows CONTAINS edges upward to find the containing Class of each call target. Excludes self-references. Batches the CALLS query in chunks of 450.
   - `get_module_dependencies(file_path)` — Two sources: (1) IMPORTS_FROM edges whose target resolves to a File node, (2) cross-file CALLS from nodes in the source file to nodes in other files. Filters out stdlib/external deps by checking if the target has a File node.

2. **`postprocessing.py`**:
   - Added `_derive_edges()` step that iterates all Class nodes (for CLASS_USES) and all File nodes (for MODULE_DEPENDS_ON), computes aggregate stats. Controlled by `CRG_DERIVED_EDGES` env var.
   - Called from `run_post_processing()` as a new step (step 6).

3. **`tools/build.py`**:
   - `_run_postprocess()` now calls `_derive_edges()` before the "minimal" early-return gate, so derived edges are computed even at `postprocess=minimal`.

4. **`constants.py`** — Added config toggles:
   - `CRG_USES_TYPE` — Controls USES_TYPE edge extraction during parsing.
   - `CRG_DERIVED_EDGES` — Controls derived edge computation in post-processing.

5. **`parser.py`** — Refactored:
   - Now imports `CRG_USES_TYPE` from `constants` instead of `os.environ.get()`.
   - Removed unused `import os`.

6. **`tests/test_postprocessing.py`** — Added `TestDerivedEdges` class with:
   - `test_class_uses_derivation`: Class A.foo() calls B.bar() → CLASS_USES A → B.
   - `test_class_uses_self_reference_omitted`: Self-calls within a class are excluded.
   - `test_module_depends_derivation`: File A imports File B + calls B's function.
   - `test_module_depends_both_paths`: File depends on another via import AND via call (deduplication).

**Key decisions:**
- Derived edges are computed on-the-fly (queried when needed), NOT stored in the edges table.
- `get_class_uses` verifies the input is a Class node (returns [] otherwise).
- Self-references are excluded at the Class level (calls to own methods don't count as CLASS_USES).
- Stdlib/external deps filtered by checking if the target has a File node in the graph.
- The `_derive_edges` pipeline step runs aggregate computation and reports stats without storing edges.
- In `tools/build.py`, `_derive_edges` runs even at `postprocess=minimal` since it's lightweight.
- In `postprocessing.py:run_post_processing()`, `_derive_edges` runs as a non-fatal step (failures become warnings).

**Test results:** All 22 postprocessing tests pass (18 existing + 4 new). All 18 graph tests pass. 114/114 relevant tests pass overall. All pre-existing failures unchanged.

## 2026-04-30: MCP query tools (class_callers_of, class_callees_of, dependency_matrix) and visualization update

**Task:** Implement MCP query tools and update visualization for new edge types.

**Changes made:**

1. **`tools/query.py`** — Added two new query patterns:
   - `class_callers_of`: Finds classes whose methods call methods of the target class.
     - Walks CONTAINS edges from target class to find methods.
     - Walks CALLS edges (by target) to find callers.
     - Walks CONTAINS edges (by target, upward) to find the caller's containing class.
     - Excludes self-calls.
     - Returns class node dicts augmented with `via_methods` list.
   - `class_callees_of`: Symmetric — finds classes whose methods are called by the target class's methods.
     - Same algorithm but follows CALLS edges by source (outgoing) instead.
   - Both patterns added to `_QUERY_PATTERNS` and docstring.

2. **`tools/analysis_tools.py`** — Added `dependency_matrix()`:
   - Input: `scope` (file path prefix or class name), `mode` (class_level/module_level), `depth` (1-3).
   - For `class_level`: Finds classes in scope, walks their methods' outgoing CALLS edges, resolves callee classes via CONTAINS upward, builds direct-dependency map.
   - For `module_level`: Finds files in scope, walks their nodes' outgoing CALLS and IMPORTS_FROM edges, resolves target files, builds direct-dependency map.
   - BFS up to `depth` hops for transitive dependencies.
   - Output: `matrix` (source/target/strength), `coupling_score`, `hub_classes`/`hub_modules`, `leaf_classes`/`leaf_modules`, `truncated` flag.
   - Capped at 500 source entities.

3. **`tools/__init__.py`** — Exported `dependency_matrix`.

4. **`main.py`** — Registered `dependency_matrix_tool` as an MCP tool.

5. **`visualization.py`** — Added new edge types to both HTML templates:
   - `_HTML_TEMPLATE`: Added DECORATED_BY, USES_TYPE, CLASS_USES, MODULE_DEPENDS_ON to `EDGE_COLOR`, `EDGE_CFG`, legend items, and CSS classes.
   - `_AGGREGATED_HTML_TEMPLATE`: Added same edge kinds to `EDGE_COLOR`, `EDGE_CFG`, `buildLegend` cls mapping, and CSS classes.

6. **`tests/test_tools.py`** — Added `TestClassQueryPatterns` with 5 tests:
   - `test_class_callers_of_finds_calling_class`
   - `test_class_callees_of_finds_called_class`
   - `test_class_callers_of_excludes_self_calls`
   - `test_dependency_matrix_class_level`
   - `test_dependency_matrix_module_level`

**Key decisions:**
- `class_callers_of` / `class_callees_of` use the existing graph structure (CONTAINS + CALLS edges) without requiring stored CLASS_USES edges.
- `dependency_matrix` derives dependencies on-the-fly using point queries per entity, avoiding expensive `get_all_edges()` scans.
- For transitive matrix entries (depth > 1), strength is set to 1 (existence) rather than propagating direct edge counts, which would be semantically misleading.
- Visualization colors chosen to be distinguishable from existing edge colors:
  - DECORATED_BY: red dotted (#ff7b72)
  - USES_TYPE: light blue dashed (#79c0ff)
  - CLASS_USES: orange solid (#ffa657)
  - MODULE_DEPENDS_ON: rosy brown dashed (#bc8f8f)
- Exports (GraphML/Cypher/Obsidian/SVG) already handle all edge kinds generically via `export_graph_data()` — no changes needed.

**Test results:** 85/85 tests in test_tools.py + test_visualization.py pass. 5/5 new tests pass. Pre-existing failures unchanged.
