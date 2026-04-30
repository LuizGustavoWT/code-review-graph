# Test Failures Fix - Learnings

## 2026-04-30 - Initial Analysis
- fastmcp 3.2.4 removed `_tool_manager`, replaced with `_local_provider._components`
- Shebang detection NEVER implemented - only extension-based exists
- Module-scope calls dropped in 5 code paths due to `if enclosing_func:` guards
- GDScript has ZERO entries in type mappings
- Julia has wrong/insufficient mappings and no construct handlers
- Java method_declaration lacks dedicated `_get_name` handling
- Databricks header hardcoded to `\n`
- `_detect_serve_command` fallback uses `sys.executable`, not `"code-review-graph"`

## Conventions
- Extension > shebang (test explicitly enforces)
- Caller fallback pattern: `self._qualify(enclosing_func, ...) if enclosing_func else file_path`
- All verification via pytest - zero human intervention
- Commit after each task group

## 2026-04-30 - test_stdio_calls_mcp_run_stdio fix
- Fixed assertion at `tests/test_main.py:62` to expect `show_banner=False` kwarg
- Production code at `main.py:992` passes `mcp.run(transport="stdio", show_banner=False)`
- Test now passes (1 passed in 0.85s)

## 2026-04-30 - test_install_qoder_config fix
- Updated `tests/test_skills.py:666-667` to match `_detect_serve_command()` fallback
- Fallback when uvx absent: `sys.executable` as command, `["-m", "code_review_graph", "serve"]` as args
- Also added assertion for `args` field in the MCP server entry
- Test passes (1 passed in 0.51s)

## 2026-04-30: Fixed Databricks CRLF line ending detection

**Files changed:** `code_review_graph/parser.py`

**Two changes:**
1. **Header detection** (line 676-677): Changed from `source.startswith(b"# Databricks notebook source\n")` to `source.startswith((b"...\n", b"...\r\n"))` — a tuple of both LF and CRLF variants. The tuple form preserves the false-positive guard (extra chars after the phrase won't match either variant).

2. **Cell splitting** (line 1203): Changed `text.split("\n")` to `text.splitlines()` in `_parse_databricks_py_notebook`. `str.splitlines()` handles `\n`, `\r\n`, and `\r` automatically, removing trailing `\r` that `split("\n")` would leave on CRLF files.

**Verification:**
- `pytest tests/test_notebook.py::TestDatabricksPyNotebook -q` — 11/11 passed
- `pytest tests/test_notebook.py -q` — 46 passed, 2 xpassed (full suite regression-free)

**Key insight:** `str.splitlines()` is the idiomatic Python way to split text with unknown line endings. It strips all line ending characters from the result, which keeps downstream processing clean.

## 2026-04-30 - Migrated `_tool_manager` to `_local_provider._components`

**Files changed:**
- `code_review_graph/main.py:945` — `_apply_tool_filter` uses `mcp._local_provider._components` instead of `mcp._tool_manager._tools`
- `tests/test_main.py:231-246` — `_restore_tools` fixture updated to use new API
- `tests/test_main.py` (all assertions) — `get_tools()` → `list_tools()`

**Key changes:**
1. `_local_provider._components` is a `dict[str, FastMCPComponent]` (keys like `"tool:name"`)
2. `list_tools()` returns `Sequence[Tool]` (not dict) — use `{tool.name for tool in await mcp.list_tools()}`
3. `get_tools()` removed entirely in fastmcp 3.2.4
4. `mcp.remove_tool(name)` still works but deprecated (warning: use `mcp.local_provider.remove_tool(name)`)

**Verification:** `pytest tests/test_main.py::TestApplyToolFilter -q` — 6 passed

## 2026-04-30 - Fixed module-scope CALLS edges in parser.py

**Files changed:** `code_review_graph/parser.py`

**Problem:** When a function call occurs at module scope (not inside any function body), `enclosing_func` is `None` and 4 code paths dropped the CALLS edge entirely. `_extract_value_references` already had the correct pattern.

**Fixes applied to 4 functions:**

1. **`_extract_calls` (line 3024):**
   - Changed `if call_name and enclosing_func:` → `if call_name:`
   - Added caller fallback: `caller = self._qualify(enclosing_func, file_path, enclosing_class) if enclosing_func else file_path`

2. **`_extract_jsx_component_call` (line 3060):**
   - Removed `if not enclosing_func: return` guard
   - Added same caller fallback pattern

3. **`_extract_elixir_constructs` (line 2100):**
   - Removed `if enclosing_func:` guard around CALLS edge emission
   - Added same caller fallback pattern

4. **`_handle_r_call` (line 4647):**
   - Removed `if enclosing_func:` guard
   - Restructured to compute `call_name` first, then emit edge with fallback caller

5. **`_extract_value_references` (lines 3153-3156):**
   - Already correct — verified it uses `if enclosing_func: caller = self._qualify(...)` else `caller = file_path`

**Key insight:** The fallback pattern `caller = self._qualify(enclosing_func, ...) if enclosing_func else file_path` is the consistent way to handle both function-scope and module-scope callers. Using `file_path` as the caller makes `find_dead_code` see module-scope callers as valid, fixing dead code detection false positives.

**Verification:**
- `pytest tests/test_parser.py::TestModuleScopeCalls -q` — 5 passed
- `pytest tests/test_refactor.py::TestFindDeadCodeModuleScope -q` — 2 passed
- `pytest tests/test_parser.py -k "test_module_scope_calls" -q` — 2 passed
- `pytest tests/test_parser.py -q` — 90 passed (full suite regression-free)
