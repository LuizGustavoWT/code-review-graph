# Final QA Report — Function Usage Graphs

## Scenarios

| # | Scenario | Status | Evidence |
|---|----------|--------|----------|
| 1 | EdgeKind constants | PASS | scenario-01-edgekind.txt |
| 2 | DECORATED_BY extraction | PASS | scenario-02-decorated-by.txt |
| 3 | USES_TYPE extraction | PASS | scenario-03-uses-type.txt |
| 4 | Cross-file CALLS resolution | PASS | scenario-04-crossfile-calls.txt |
| 5 | CLASS_USES derivation | PASS | scenario-05-class-uses.txt |
| 6 | MODULE_DEPENDS_ON derivation | PASS | scenario-06-module-depends.txt |
| 7 | class_callers_of query | PASS | scenario-07-class-callers.txt |
| 8 | class_callees_of query | PASS | scenario-08-class-callees.txt |
| 9 | dependency_matrix tool | PASS | scenario-09-dep-matrix.txt |
| 10 | Config toggles (CRG_USES_TYPE, CRG_DERIVED_EDGES) | PASS | scenario-10-config-toggles.txt |
| 10b | CRG_USES_TYPE=0 disables USES_TYPE | PASS | scenario-10b-uses-type-off.txt |
| 10c | CRG_DERIVED_EDGES=0 disables postprocessing stats | PASS | scenario-10c-derived-off.txt |
| 11 | Enrichment framework | PASS | scenario-11-enrichment.txt |
| 12 | Cross-task integration | PASS | scenario-integration.txt |

**Scenarios 12/12 pass**

## Integration

Cross-task integration tested end-to-end:
- Parser creates CALLS + CONTAINS + INHERITS + IMPORTS_FROM edges
- Derived edges (CLASS_USES, MODULE_DEPENDS_ON) computed on-the-fly
- query_graph patterns class_callers_of / class_callees_of return correct classes
- dependency_matrix runs in both class_level and module_level modes
- Build pipeline calls resolve_bare_call_targets and _run_enricher

**Integration 7/7 checks pass**

## Unit Tests (targeted)

- test_decorated_by_function_python PASSED
- test_decorated_by_class_python PASSED
- test_decorated_by_decorator_factory PASSED
- test_decorated_by_multiple_decorators PASSED
- test_uses_type_non_builtin PASSED
- test_uses_type_skips_builtins PASSED
- test_uses_type_union PASSED
- test_uses_type_disabled_by_env PASSED
- test_cross_file_calls_alias_resolution PASSED
- test_cross_file_calls_all_resolved PASSED
- test_class_uses_derivation PASSED
- test_class_uses_self_reference_omitted PASSED
- test_module_depends_derivation PASSED
- test_module_depends_both_paths PASSED

## Issues Found

1. **Bare edge-kind string literals in communities.py** — `communities.py` uses bare strings like `"CALLS"` instead of `EdgeKind.CALLS`. This file was NOT in the Task 0.1 refactor list, so it is a scope-gap / follow-up item.
2. **Duplicate backup files** — `enrich 2.py`, `enrich 3.py`, `jedi_resolver 2.py` exist in the repo and contain bare strings. These appear to be accidental backup copies, not source files.
3. **Pre-existing test failures** — 62 tests fail in the full suite, but all are pre-existing (GDScript, Julia, shebang, Java parsing, and test_main errors). Zero new failures introduced by this plan.

## VERDICT

**APPROVE**

All 12 QA scenarios pass. Integration pipeline verified end-to-end. Targeted unit tests all pass. Pre-existing test failures are unrelated to this plan's scope. The one code-quality gap (communities.py bare strings) is minor and was outside the explicit refactor scope.
