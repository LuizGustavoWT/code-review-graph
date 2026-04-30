# Work Plan: Fix All Test Failures (61 failed + 6 errors)

## TL;DR

> **Quick Summary**: Fix 67 test failures across 10 categories in the code-review-graph project, caused by fastmcp 3.x API migration, missing parser features (shebang detection, GDScript/Julia support), and module-scope call edge omissions.
>
> **Deliverables**:
> - All 1116+ passing tests continue passing
> - All 61 failed tests now pass
> - All 6 error tests now pass
> - Zero regressions in the test suite
>
> **Estimated Effort**: Large (10 categories, ~15-20 file changes)
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Wave 1 (simple fixes) → Wave 2 (parser logic) → Final verification

---

## Context

### Original Request
User ran `pytest` and got 61 failed + 6 errors (out of 1116 passed). Asked to analyze and fix.

### Interview Summary
**Root causes by category**:
1. **fastmcp 3.2.4 API** (6 errors): `_tool_manager` removed, replaced by `_local_provider._components`
2. **show_banner kwarg** (1 failure): Test expects `{"transport": "stdio"}` but code passes `show_banner=False`
3. **Shebang detection** (11 failures): `detect_language()` only checks extension, never implemented
4. **Module-scope CALLS** (7+2=9 failures): 5 code paths drop edges when `enclosing_func` is None
5. **Java parsing** (5 failures): method names vs return types, base types include keywords, no import resolver
6. **PHP call detection** (1 failure): `_get_call_name` doesn't handle PHP AST structure
7. **GDScript** (9 failures): Zero entries in type mapping dictionaries
8. **Julia** (22 failures): Wrong mappings, missing construct handlers
9. **Databricks CRLF** (1 failure): Header detection hardcoded to `\n`
10. **Skills/qoder test** (1 failure): Test expectation outdated vs implementation

### Metis Review
**Key findings**:
- Fix order matters: Category 4 (module-scope calls) is a prerequisite for Category 9 (dead code)
- Scope must be locked: ONLY fix what tests test, no full language support
- Shebang order constraint: extension > shebang (test explicitly enforces this)
- No new tree-sitter grammar installs without verification
- Must verify after EACH category to isolate regressions

---

## Work Objectives

### Core Objective
Make all 61 failed tests + 6 errors pass without breaking any currently passing tests.

### Concrete Deliverables
- `pytest -q` returns 0 failures, 0 errors
- All 10 test categories independently pass

### Definition of Done
- [ ] `pytest tests/test_main.py -q` passes
- [ ] `pytest tests/test_parser.py -q` passes
- [ ] `pytest tests/test_multilang.py -q` passes
- [ ] `pytest tests/test_notebook.py -q` passes
- [ ] `pytest tests/test_refactor.py -q` passes
- [ ] `pytest tests/test_skills.py -q` passes
- [ ] `pytest -q` (full suite) shows 0 failed, 0 errors

### Must Have
- Fix all 61 FAILED assertions
- Fix all 6 ERROR (AttributeError) exceptions
- Zero regressions in previously passing tests
- Each fix verified with pytest after implementation

### Must NOT Have (Guardrails)
- NO new language support beyond making tests pass
- NO refactoring/restructuring alongside fixes
- NO new tree-sitter grammar package installs
- NO changing behavior of passing tests
- NO scope creep: only fix what tests test

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is via pytest commands.

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: Already exist - run them
- **Framework**: pytest 8.x

### QA Policy
Every task MUST be verified by running the relevant pytest subset.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Simple fixes - no parser logic changes):
├── Task 1: Fix _tool_manager in main.py [quick]
├── Task 2: Fix show_banner assertion in test_main.py [quick]
├── Task 3: Fix _restore_tools fixture in test_main.py [quick]
├── Task 4: Fix test_skills.py Qoder expectation [quick]
├── Task 5: Fix Databricks CRLF detection [quick]

Wave 2 (Parser logic changes - MAX PARALLEL):
├── Task 6: Implement shebang detection in detect_language() [unspecified-high]
├── Task 7: Fix module-scope CALLS edges (5 code paths) [unspecified-high]
├── Task 8: Fix Java parsing (name extraction + base types + import resolution) [unspecified-high]
├── Task 9: Fix PHP call detection [quick]
├── Task 10: Add GDScript type mappings [unspecified-high]
├── Task 11: Fix Julia parsing (mappings + construct handlers) [unspecified-high]

Wave FINAL:
├── Task 12: Full suite regression verification [unspecified-high]
```

### Dependency Matrix
- **Tasks 1-5**: Independent, can start immediately. Task 3 depends on Task 1.
- **Tasks 6-11**: Independent of each other, depend on no Wave 1 task.
- **Task 12**: Depends on ALL tasks 1-11.

---

## TODOs

- [x] 1. Migrate `_tool_manager` to `_local_provider._components` in main.py

  **What to do**:
  - In `code_review_graph/main.py`, line 945: change `mcp._tool_manager._tools.keys()` to iterate over `mcp._local_provider._components` and filter for `Tool` instances
  - Pattern: `from fastmcp.tools.base import Tool` and `[name for name, c in mcp._local_provider._components.items() if isinstance(c, Tool)]`
  - Verify the tool name format from `_components` dict keys (may be `"tool:name"` format - strip the `"tool:"` prefix)

  **Must NOT do**:
  - Do NOT change the logic of `_apply_tool_filter`, only the dict access
  - Do NOT add async to `_apply_tool_filter` (called from sync `main()`)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 3
  - **Blocked By**: None

  **References**:
  - `code_review_graph/main.py:945` - The `_apply_tool_filter` function using `mcp._tool_manager._tools`
  - `tests/test_main.py:231-234` - Same pattern in test fixture (will be fixed in Task 3)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_main.py::TestApplyToolFilter -q` passes all 6 tests

  **QA Scenarios**:
  ```
  Scenario: _apply_tool_filter works with fastmcp 3.2.4
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_main.py::TestApplyToolFilter -v`
    Expected Result: All 6 TestApplyToolFilter tests pass (no AttributeError)
    Evidence: .sisyphus/evidence/task-1-tool-filter-pass.txt
  ```

  **Commit**: YES
  - Message: `fix(main): migrate _tool_manager to _local_provider._components for fastmcp 3.x`
  - Files: `code_review_graph/main.py`
  - Pre-commit: `pytest tests/test_main.py::TestApplyToolFilter -q`

---

- [x] 2. Fix `show_banner` assertion in test_stdio_calls_mcp_run_stdio

  **What to do**:
  - In `tests/test_main.py`, line 62: change the expected assertion from `[{"transport": "stdio"}]` to `[{"transport": "stdio", "show_banner": False}]`
  - The production code at `main.py:988` correctly passes `show_banner=False`; the test just needs to expect it

  **Must NOT do**:
  - Do NOT remove `show_banner=False` from production code (it's intentional)
  - Do NOT change `test_http_calls_mcp_run_with_host_port` - that test doesn't fail

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (independent of Task 1)
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `tests/test_main.py:54-62` - The test function `test_stdio_calls_mcp_run_stdio`
  - `code_review_graph/main.py:986-988` - The production code passing `show_banner=False`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_main.py::TestServeMainTransport::test_stdio_calls_mcp_run_stdio -q` passes

  **QA Scenarios**:
  ```
  Scenario: show_banner assertion updated
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_main.py::TestServeMainTransport::test_stdio_calls_mcp_run_stdio -v`
    Expected Result: Test passes
    Evidence: .sisyphus/evidence/task-2-show-banner-pass.txt
  ```

  **Commit**: NO (group with Task 3)
  - Message: `fix(tests): update test_stdio_calls_mcp_run_stdio to expect show_banner=False`
  - Files: `tests/test_main.py`

---

- [x] 3. Fix `_restore_tools` fixture in test_main.py

  **What to do**:
  - In `tests/test_main.py`, lines 231-234: change the fixture `_restore_tools` to snapshot and restore tools via `mcp._local_provider._components` instead of `mcp._tool_manager._tools`
  - Pattern: save `dict(mcp._local_provider._components)` before test, restore with `clear()` + `update()` after
  - Also need to update tests that call `mcp.get_tools()` (async) - check if `await mcp.get_tools()` works or if we need synchronous access to `_local_provider._components`
  - The test methods are async (`@pytest.mark.asyncio`), so `await mcp.get_tools()` should work. Verify this.

  **Must NOT do**:
  - Do NOT remove the `_restore_tools` fixture or make it no-op

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 1 fixing main.py)
  - **Parallel Group**: Wave 1 (after Task 1)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `tests/test_main.py:231-234` - The `_restore_tools` fixture
  - `tests/test_main.py:242-286` - The 6 async tests using fixture

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_main.py::TestApplyToolFilter -q` passes all 6 tests

  **QA Scenarios**:
  ```
  Scenario: TestApplyToolFilter works after fixture fix
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_main.py::TestApplyToolFilter -v`
    Expected Result: All 6 tests pass
    Evidence: .sisyphus/evidence/task-3-test-apply-tool-filter-pass.txt
  ```

  **Commit**: YES (with Task 2)
  - Message: `fix(tests): migrate _restore_tools fixture from _tool_manager to _local_provider`
  - Files: `tests/test_main.py`

---

- [x] 4. Fix test_skills.py Qoder config expectation

  **What to do**:
  - In `tests/test_skills.py`, line 666-667: update the expected command
  - The `_detect_serve_command` function in `skills.py` falls back to `(sys.executable, ["-m", "code_review_graph", "serve"])`
  - Update the test to handle this: when `uvx` is not present, expect `sys.executable` as the command with `["-m", "code_review_graph", "serve"]` as args
  - Check if the test structure expects command and args separately, or as a single command string

  **Must NOT do**:
  - Do NOT change the production code in `skills.py`
  - Do NOT force `"code-review-graph"` as fallback (the sys.executable approach is intentional)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `tests/test_skills.py:660-670` - The test function
  - `code_review_graph/skills.py:190-204` - `_detect_serve_command` function showing fallback behavior

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_skills.py::TestInstallPlatformConfigs::test_install_qoder_config -q` passes

  **QA Scenarios**:
  ```
  Scenario: test_install_qoder_config passes
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_skills.py::TestInstallPlatformConfigs::test_install_qoder_config -v`
    Expected Result: Test passes
    Evidence: .sisyphus/evidence/task-4-skills-qoder-pass.txt
  ```

  **Commit**: YES
  - Message: `fix(tests): update qoder config test to match _detect_serve_command fallback`
  - Files: `tests/test_skills.py`

---

- [x] 5. Fix Databricks CRLF detection

  **What to do**:
  - In `code_review_graph/parser.py`, line 676-677: change the header detection to handle `\r\n`
  - Instead of `source.startswith(b"# Databricks notebook source\n")`, do one of:
    a) `source.lstrip(b"\r").startswith(b"# Databricks notebook source\n")` - handles CRLF but not the content check
    b) `source.startswith((b"# Databricks notebook source\n", b"# Databricks notebook source\r\n"))` - cleanest
    c) Check first line via `source.split(b"\n", 1)[0]` then strip `\r`
  - Also fix `_parse_databricks_py_notebook` at line ~1203 where `text.split("\n")` should use `splitlines()` or handle `\r\n` to avoid trailing `\r` on lines

  **Must NOT do**:
  - Do NOT change the false-positive guard (extra characters after header). Keep `== len(HEADER)` or any boundary check intact.
  - Do NOT change the actual notebook parsing logic, only line ending handling

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `code_review_graph/parser.py:674-679` - The header detection
  - `code_review_graph/parser.py:1196-1210` (approx) - `_parse_databricks_py_notebook` with `split("\n")`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_notebook.py::TestDatabricksPyNotebook::test_databricks_header_crlf_line_endings -q` passes
  - [ ] All other notebook tests still pass: `pytest tests/test_notebook.py -q`

  **QA Scenarios**:
  ```
  Scenario: CRLF detection works
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_notebook.py::TestDatabricksPyNotebook -v`
    Expected Result: All Databricks tests pass including CRLF test
    Evidence: .sisyphus/evidence/task-5-crlf-pass.txt
  ```

  **Commit**: YES
  - Message: `fix(parser): handle CRLF line endings in Databricks header detection`
  - Files: `code_review_graph/parser.py`

---

- [x] 6. Implement shebang detection in `CodeParser.detect_language()`

  **What to do**:
  - In `code_review_graph/parser.py`, modify `detect_language()` (line 642):
    1. First check `path.suffix.lower()` in `EXTENSION_TO_LANGUAGE` (existing behavior)
    2. If extension gives a language, return it immediately (extension > shebang, per test constraint)
    3. If no extension match, read first 2 bytes of file
    4. If starts with `b"#!"`, extract the interpreter path from the first line
    5. Map known interpreters to languages:
       - `bash`, `sh` → `bash`
       - `python`, `python3`, `python2` → `python`
       - `node` → `javascript`
       - `ruby` → `ruby`
       - `perl` → `perl`
       - Handle `#!/usr/bin/env <interpreter>` pattern
       - Handle `#!/usr/bin/env -S <interpreter> <flags>` pattern
       - Handle direct paths: `#!/bin/bash`, `#!/usr/bin/python3`, `#!/bin/node`
    6. Handle flags after interpreter name (e.g., `#!/bin/bash -e` → interpreter is `bash`)
    7. If no mapping found, return `None`
  - Must handle all shebang test cases (11 tests + edge cases)

  **Shebang mapping table**:
  | Shebang pattern | Language |
  |---|---|
  | `#!/bin/bash`, `#!/usr/bin/env bash`, `#!/bin/sh` | `bash` |
  | `#!/usr/bin/python3`, `#!/usr/bin/env python3`, `#!/bin/python` | `python` |
  | `#!/usr/bin/env node`, `#!/bin/node` | `javascript` |
  | `#!/usr/bin/env ruby` | `ruby` |
  | `#!/usr/bin/env perl` | `perl` |

  **Must NOT do**:
  - Do NOT override extension-based detection (test explicitly enforces: extension > shebang)
  - Do NOT crash on binary files, empty files, or files with no shebang
  - Do NOT add interpreters not in the test cases (no `ocaml`, `rust`, etc. mapping beyond None)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `code_review_graph/parser.py:642-643` - Current `detect_language()` implementation
  - `tests/test_parser.py:24-131` - All shebang tests
  - `tests/test_parser.py:134-159` - End-to-end shebang parse test (bash functions)
  - `tests/fixtures/` - No specific fixture, tests create temp files

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_parser.py -k "shebang" -q` passes (11 tests)
  - [ ] `pytest tests/test_parser.py::TestCodeParser::test_parse_shebang_script_produces_function_nodes -q` passes

  **QA Scenarios**:
  ```
  Scenario: All shebang tests pass
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_parser.py -k shebang -v`
    Expected Result: All 11 shebang tests pass, including the critical extension-over-shebang test
    Evidence: .sisyphus/evidence/task-6-shebang-pass.txt
  ```

  **Commit**: YES
  - Message: `feat(parser): implement shebang detection in detect_language() for extension-less scripts`
  - Files: `code_review_graph/parser.py`

---

- [x] 7. Fix module-scope CALLS edges (5 code paths)

  **What to do**:
  - In `code_review_graph/parser.py`, fix the 5 code paths where CALLS edges are dropped when `enclosing_func` is `None`:
    1. **`_extract_calls` (line ~3024)**: Change `if call_name and enclosing_func:` to always emit when `call_name` is truthy, using `file_path` as caller when `enclosing_func` is `None`
    2. **`_extract_jsx_component_call` (line ~3060)**: Remove the `if not enclosing_func: return` early return, add `caller = file_path` fallback
    3. **`_extract_elixir_constructs` (line ~2100)**: Remove the `if enclosing_func:` guard, use `file_path` as caller
    4. **`_extract_value_references` (line ~3153)**: Already has the correct pattern (`caller = file_path` when `enclosing_func` is None) - verify it works
    5. **`_handle_r_call` (line ~4647)**: Remove the `if enclosing_func:` guard, use `file_path` as caller
  - The pattern in all cases: `caller = self._qualify(enclosing_func, ...) if enclosing_func else file_path`
  - This automatically fixes the 2 dead code detection failures (Category 9) as a side effect

  **Must NOT do**:
  - Do NOT change the `_qualify` method or call target resolution
  - Do NOT add new call types or change how calls inside functions work
  - Do NOT change the test files

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None (fixes Category 9 as side effect)

  **References**:
  - `code_review_graph/parser.py:~2100` - `_extract_elixir_constructs`
  - `code_review_graph/parser.py:~3024` - `_extract_calls`
  - `code_review_graph/parser.py:~3060` - `_extract_jsx_component_call`
  - `code_review_graph/parser.py:~3153` - `_extract_value_references` (already correct, verify)
  - `code_review_graph/parser.py:~4647` - `_handle_r_call`
  - `tests/test_parser.py:TestModuleScopeCalls` - 5 tests
  - `tests/test_refactor.py:TestFindDeadCodeModuleScope` - 2 tests (auto-fixed)

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_parser.py::TestModuleScopeCalls -q` passes (5 tests)
  - [ ] `pytest tests/test_refactor.py::TestFindDeadCodeModuleScope -q` passes (2 tests)
  - [ ] `pytest tests/test_parser.py -k "test_module_scope_calls" -q` passes (2 tests in TestCodeParser)

  **QA Scenarios**:
  ```
  Scenario: Module-scope CALLS edges created correctly
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_parser.py::TestModuleScopeCalls -v`
      2. Run `pytest tests/test_refactor.py::TestFindDeadCodeModuleScope -v`
    Expected Result: All module-scope/dead-code tests pass
    Evidence: .sisyphus/evidence/task-7-module-scope-pass.txt

  Scenario: No regression in call-heavy tests
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_multilang.py -q`
    Expected Result: No additional failures (or fewer)
    Evidence: .sisyphus/evidence/task-7-no-regression.txt
  ```

  **Commit**: YES
  - Message: `fix(parser): emit CALLS edges for module-scope calls using file_path as caller`
  - Files: `code_review_graph/parser.py`

---

- [x] 8. Fix Java parsing (name extraction + base types + import resolution)

  **What to do**:
  - **A. Fix method name extraction** in `_get_name`:
    - Add a Java-specific branch before the generic loop (around line 4014)
    - For `method_declaration`: find the `identifier` child (method name), skip `type_identifier` and `void_type` children
    - Pattern: similar to Go's `method_declaration` handler at line ~4001-4004

  - **B. Fix base types** in `_get_bases`:
    - In the Java/C# branch (line ~4098), instead of appending `child.text.decode()`, recurse into the child's children to find `type_identifier` nodes
    - `superclass` contains: `extends` keyword + `type_identifier`
    - `super_interfaces` contains: `implements` keyword + `type_list` > `type_identifier`
    - Extract only the type identifier text, not the full node text

  - **C. Add Java import resolution** in `_do_resolve_module`:
    - Add a `java` / `kotlin` / `scala` case before the generic fallback (around line ~3700)
    - Convert dot-notation `com.example.auth.User` to path `com/example/auth/User.java`
    - Search in standard Maven/Gradle dirs: `src/main/java/`, `src/test/java/`
    - Also search from repo root directly
    - Handle static imports: `import static com.example.util.Helper.MAX` should resolve to `Helper.java` and then append `MAX` as a qualifier

  **Must NOT do**:
  - Do NOT add Maven/Gradle dependency resolution (no JARs, no external deps)
  - Do NOT handle wildcard imports (`import com.example.*`)
  - Do NOT change `_get_bases` for other languages

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `code_review_graph/parser.py:~3936` - `_get_name` method
  - `code_review_graph/parser.py:~4098` - `_get_bases` Java/C# branch
  - `code_review_graph/parser.py:~3669` - `_do_resolve_module`
  - `tests/test_multilang.py:TestJavaParsing` - 3 tests
  - `tests/test_multilang.py:TestJavaImportResolution` - 2 tests
  - `tests/fixtures/SampleJava.java` - Java fixture file

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_multilang.py -k "Java" -q` passes (5 tests)

  **QA Scenarios**:
  ```
  Scenario: All Java tests pass
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_multilang.py -k "Java" -v`
    Expected Result: All 5 Java tests pass
    Evidence: .sisyphus/evidence/task-8-java-pass.txt
  ```

  **Commit**: YES
  - Message: `fix(parser): fix Java method name extraction, base types, and import resolution`
  - Files: `code_review_graph/parser.py`

---

- [x] 9. Fix PHP call detection

  **What to do**:
  - In `code_review_graph/parser.py`:
    1. Add `"nullsafe_member_call_expression"` and `"scoped_call_expression"` to `_CALL_TYPES["php"]` 
    2. In `_get_call_name` (line ~4304), add PHP handling after the Perl check (line ~4363):
       - If `language == "php"` and `first.type == "name"`: return `first.text.decode(...)` (handles `function_call_expression`)
       - If `language == "php"` and node type is `member_call_expression`/`nullsafe_member_call_expression`: the second child is the member name
       - If `language == "php"` and node type is `scoped_call_expression`: find the `name` child

  **Must NOT do**:
  - Do NOT change other languages' call detection
  - Do NOT add full PHP support, only what `sample.php` fixture needs

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `code_review_graph/parser.py:~286` - `_CALL_TYPES["php"]`
  - `code_review_graph/parser.py:~4304` - `_get_call_name` function
  - `tests/test_multilang.py::TestPHPParsing::test_finds_calls`
  - `tests/fixtures/sample.php`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_multilang.py -k "PHP" -q` passes (1 test)

  **QA Scenarios**:
  ```
  Scenario: PHP call detection works
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_multilang.py -k "PHP" -v`
    Expected Result: PHP parsing test passes
    Evidence: .sisyphus/evidence/task-9-php-pass.txt
  ```

  **Commit**: YES (with Task 10 or 11)
  - Message: `fix(parser): add PHP nullsafe/scoped call handling and fix call name extraction`
  - Files: `code_review_graph/parser.py`

---

- [x] 10. Add GDScript type mappings

  **What to do**:
  - In `code_review_graph/parser.py`, add `"gdscript"` entries to all four type mapping dictionaries:
    - `_CLASS_TYPES["gdscript"]` = `["class_definition", "class_name_statement"]`
    - `_FUNCTION_TYPES["gdscript"]` = `["function_definition"]`
    - `_IMPORT_TYPES["gdscript"]` = `["extends_statement"]`
    - `_CALL_TYPES["gdscript"]` = `["call", "attribute_call"]`
  - In `_get_name`, add GDScript-specific handling:
    - For `class_definition`: the name is in a `name` child
    - For `class_name_statement`: the name is in a `name` child  
    - For `function_definition`: the name is in a `name` child
  - In `_get_bases` or in the class extraction, handle `extends_statement` for inheritance:
    - GDScript `extends Node` uses `extends` keyword + `type` child containing `identifier`
  - For `call_expression` (called `call` in GDScript), the first child may be the function name - check the actual AST structure
  - **Important**: First verify that the tree-sitter-gdscript grammar is available. Run `python3 -c "from tree_sitter_language_pack import get_binding; get_binding('gdscript')"` or similar. If not available, the tests will need to be skipped.

  **Must NOT do**:
  - Do NOT add beyond what `tests/fixtures/sample.gd` requires
  - Do NOT install new packages without confirming grammar availability

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `code_review_graph/parser.py:lines 132-303` - Type mapping dictionaries
  - `code_review_graph/parser.py:~3936` - `_get_name` method
  - `tests/test_multilang.py:TestGDScriptParsing` - 9 tests
  - `tests/fixtures/sample.gd` - GDScript fixture

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_multilang.py -k "GDScript" -q` passes (9 tests)

  **QA Scenarios**:
  ```
  Scenario: All GDScript tests pass
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_multilang.py -k "GDScript" -v`
    Expected Result: All 9 GDScript tests pass
    Evidence: .sisyphus/evidence/task-10-gdscript-pass.txt
  ```

  **Commit**: YES (with Task 9 or 11)
  - Message: `feat(parser): add GDScript type mappings and name extraction`
  - Files: `code_review_graph/parser.py`

---

- [x] 11. Fix Julia parsing (mappings + construct handlers)

  **What to do**:
  - In `code_review_graph/parser.py`:
    1. **Fix type mappings**:
       - `_CLASS_TYPES["julia"]` add `"module_definition"` and `"enum_definition"` 
       - `_FUNCTION_TYPES["julia"]` fix: replace `"short_function_definition"` with `"assignment"` and add `"macro_definition"`
       - `_IMPORT_TYPES["julia"]` already has correct types but extraction logic needs fix
       
    2. **Fix `_get_name` for Julia**: Add a Julia-specific branch that handles deeply nested names:
       - `module_definition` → `identifier` child
       - `struct_definition` → `type_head` > `identifier` (or `binary_expression` for inheritance)
       - `abstract_definition` → `type_head` > `identifier`
       - `function_definition` → `signature` > `call_expression` > `identifier` (need to recurse)
       - `macro_definition` → `signature` > `call_expression` > `identifier`
       - `assignment` (short func) → find `call_expression` child, then `identifier`
       
    3. **Fix `_extract_import` for Julia**: Parse `using_statement` and `import_statement` to extract individual module/symbol names:
       - `using LinearAlgebra` → extract `LinearAlgebra`
       - `using Statistics: mean, std` → extract `Statistics.mean`, `Statistics.std`
       - `import JSON` → extract `JSON`
       - `import Base: show, print` → extract `Base.show`, `Base.print`
       
    4. **Add Julia construct handlers** in `_extract_from_tree`:
       - `macrocall_expression`: check if it's `@testset` → create Test node; if `@enum` → create Class node + Function nodes for variants
       - `export_statement` / `public_statement`: emit REFERENCES edges with `julia_export` / `julia_public` extra
       - `include("file.jl")` calls in `_extract_calls`: emit IMPORTS_FROM edges (not just CALLS)
       
  - **Important**: First verify that the tree-sitter-julia grammar is available. Run `python3 -c "from tree_sitter_language_pack import get_binding; get_binding('julia')"`. If not available, tests fail.

  **Must NOT do**:
  - Do NOT add full Julia language support - only what 22 tests test
  - Do NOT install new packages without confirming grammar availability

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `code_review_graph/parser.py` - Type mappings, `_get_name`, `_extract_import`, `_extract_from_tree`, `_extract_calls`
  - `tests/test_multilang.py:TestJuliaParsing` - 22 tests
  - `tests/fixtures/sample.jl` - Julia fixture

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_multilang.py -k "Julia" -q` passes (22 tests)

  **QA Scenarios**:
  ```
  Scenario: All Julia tests pass
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest tests/test_multilang.py -k "Julia" -v`
    Expected Result: All 22 Julia tests pass
    Evidence: .sisyphus/evidence/task-11-julia-pass.txt
  ```

  **Commit**: YES
  - Message: `feat(parser): fix Julia type mappings, name extraction, import parsing, and construct handlers`
  - Files: `code_review_graph/parser.py`

---

## Final Verification Wave

- [ ] F1. **Full Suite Regression Verification**

  **What to do**:
  1. Run the full pytest suite: `pytest -q 2>&1`
  2. Verify zero failures and zero errors
  3. If any failures remain, identify which categories still fail and return to fix them
  4. If previously-passing tests broke, roll back the offending change

  **Acceptance Criteria**:
  - [ ] `pytest -q` shows "N passed" with 0 failed, 0 errors
  - [ ] Each category independently passes: compare against the initial 61 failed + 6 errors

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO (sequential - depends on all tasks)

  **QA Scenarios**:
  ```
  Scenario: Full suite passes
    Tool: Bash (pytest)
    Steps:
      1. Run `pytest -q`
    Expected Result: No failures, no errors
    Evidence: .sisyphus/evidence/task-final-full-suite-pass.txt

  Scenario: Category breakdown verification
    Tool: Bash (pytest)
    Steps:
      1. Run individual category tests to confirm each passes
      - `pytest tests/test_main.py -q`
      - `pytest tests/test_parser.py -q`
      - `pytest tests/test_multilang.py -q`
      - `pytest tests/test_notebook.py -q`
      - `pytest tests/test_refactor.py -q`
      - `pytest tests/test_skills.py -q`
    Expected Result: Each test file shows zero failures
    Evidence: .sisyphus/evidence/task-final-category-breakdown.txt
  ```

---

## Commit Strategy

- **Task 1**: `fix(main): migrate _tool_manager to _local_provider._components for fastmcp 3.x`
- **Task 2+3**: `fix(tests): update _restore_tools fixture and show_banner assertion for fastmcp 3.x`
- **Task 4**: `fix(tests): update qoder config test to match _detect_serve_command fallback`
- **Task 5**: `fix(parser): handle CRLF line endings in Databricks header detection`
- **Task 6**: `feat(parser): implement shebang detection in detect_language()`
- **Task 7**: `fix(parser): emit CALLS edges for module-scope calls`
- **Task 8**: `fix(parser): fix Java parsing (names, bases, import resolution)`
- **Task 9+10**: `fix(parser): add PHP call detection and GDScript type mappings`
- **Task 11**: `feat(parser): fix Julia parsing support`

---

## Success Criteria

### Verification Commands
```bash
pytest -q  # Expected: 0 failed, 0 errors
pytest tests/test_main.py -q
pytest tests/test_parser.py -q
pytest tests/test_multilang.py -q
pytest tests/test_notebook.py -q
pytest tests/test_refactor.py -q
pytest tests/test_skills.py -q
```

### Final Checklist
- [ ] All 61 previously-failed tests now pass
- [ ] All 6 previously-errored tests now pass
- [ ] Zero regressions (all originally-passing tests still pass)
- [ ] Shebang detection does NOT override extension-based detection
- [ ] Module-scope calls emit CALLS edges with file_path as caller
- [ ] Dead code detection correctly considers module-scope callers
- [ ] Databricks detection works with both LF and CRLF
