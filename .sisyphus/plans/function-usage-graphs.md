# Plano: Grafos de Funções e Uso para Refactoring

## TL;DR

> **Resumo**: Implementar grafos de funções e uso (usage graphs) no code-review-graph, incluindo resolução cross-file de chamadas, novas arestas (DECORATED_BY, USES_TYPE, CLASS_USES, MODULE_DEPENDS_ON) e ferramentas MCP para consulta agregada. Foco em suporte a refactoring: "se eu mudar a classe X, quem é afetado?"
>
> **Deliverables**:
> - Código morto ressuscitado: `resolve_bare_call_targets()` e `enrich_jedi_calls()` no pipeline
> - Módulo `EdgeKind` com constantes para todos os tipos de aresta
> - Parser extraindo DECORATED_BY e USES_TYPE
> - Pós-processamento derivando CLASS_USES e MODULE_DEPENDS_ON on-the-fly
> - Novos padrões de query: `class_callers_of`, `class_callees_of`, `dependency_matrix`
> - Pipeline de pós-processamento consolidado (eliminar duplicação)
> - Framework de enriquecimento genérico (lang→enricher)
>
> **Estimated Effort**: Large (5 fases, ~25 tarefas)
> **Parallel Execution**: YES — 4 waves principais + wave final
> **Critical Path**: Phase 0 → Phase 1 (parser) → Phase 2 (derived) → Phase 3 (tools) → Phase 4 (enrichment)

### Fase 2: Derived Edges (on-the-fly)

- [x] 2.1. **Derivação on-the-fly de CLASS_USES**

  **What to do**:
  - Criar função `derive_class_uses()` em `code_review_graph/postprocessing.py`:
    - Query SQL: para cada aresta CALLS, subir para o container classe via CONTAINS edges
    - Se CALLS.source está contido em ClassA e CALLS.target está contido em ClassB → CLASS_USES: ClassA → ClassB
    - Se CALLS.source é classe (método estático) → classe é o source direto
    - Se CALLS.target não tem classe container → pular
  - Resultado não armazenado em tabela — computado on-the-fly via query helper
  - Adicionar método `get_class_uses(qn)` em `GraphStore`:
    - Dado qualified name de uma classe, retorna classes que ela usa
    - JOIN entre CALLS edges e CONTAINS hierarchy

  **Must NOT do**:
  - ❌ Não armazenar em tabela separada (on-the-fly)
  - ❌ Não incluir self-references
  - ❌ Não incluir IMPLEMENTS/INHERITS como CLASS_USES

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 3 (paralelo com 2.2)
  - **Parallel Group**: Wave 3
  - **Blocks**: 2.3, 3.1, 3.2
  - **Blocked By**: 0.1, 0.5

  **References**:
  - `code_review_graph/graph.py:1149-1181` — `get_outgoing_targets()`/`get_incoming_sources()`
  - `code_review_graph/postprocessing.py`
  - `docs/schema.md:119-134` — qualified name format

  **Acceptance Criteria**:
  - [ ] Classe A com método que chama método da Classe B → CLASS_USES: A → B
  - [ ] Função top-level não gera CLASS_USES
  - [ ] `store.get_class_uses("file.py::ClassA")` retorna classes usadas
  - [ ] Performance: < 100ms para 50K edges

  **QA Scenarios**:
  ```
  Scenario: CLASS_USES derived from CALLS + CONTAINS
    Tool: Bash
    Preconditions: Build com classes que chamam umas às outras
    Steps:
      1. Build graph
      2. python -c "from code_review_graph.graph import GraphStore; s=GraphStore('path/to/db'); r=s.get_class_uses('file.py::AuthService'); print(r)"
    Expected Result: Retorna classes cujos métodos são chamados por AuthService
    Evidence: .sisyphus/evidence/task-2.1-class-uses.txt
  ```

  **Commit**: YES (groups with 2.2, 2.3)
  - Message: `feat(postprocessing): on-the-fly CLASS_USES derivation from CALLS+CONTAINS`
  - Files: `code_review_graph/postprocessing.py`, `code_review_graph/graph.py`
  - Pre-commit: `pytest tests/`

- [x] 2.2. **Derivação on-the-fly de MODULE_DEPENDS_ON**

  **What to do**:
  - Criar função `derive_module_depends()` em `code_review_graph/postprocessing.py`:
    - Duas fontes de dependência entre módulos:
      1. **IMPORTS_FROM**: FileA →IMPORTS_FROM→ moduleB → FileB depende de ModuleB
      2. **CALLS cross-file**: FileA contém função que CALLS função em FileB
    - Agregar: se FileA depende de FileB por QUALQUER via, emitir MODULE_DEPENDS_ON
  - Adicionar método `get_module_dependencies(file_path)` em `GraphStore`

  **Must NOT do**:
  - ❌ Não armazenar em tabela
  - ❌ Não incluir dependências de stdlib

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 3
  - **Parallel Group**: Wave 3
  - **Blocks**: 2.3, 3.3
  - **Blocked By**: 0.1, 0.5

  **References**:
  - `code_review_graph/graph.py:1190-1212` — `get_edges_among()`

  **Commit**: YES (groups with 2.1, 2.3)
  - Message: `feat(postprocessing): on-the-fly MODULE_DEPENDS_ON derivation`
  - Files: `code_review_graph/postprocessing.py`, `code_review_graph/graph.py`

- [x] 2.3. **Testes: Derived Edges**

  **What to do**:
  - Criar fixture multi-arquivo com hierarquia:
    - `base.py`: `class BaseService`
    - `auth.py`: `class AuthService(BaseService)` com método que chama `Database.query()`
    - `database.py`: `class Database` com `query()`
  - Criar testes:
    - `test_class_uses_derivation`
    - `test_module_depends_derivation`
    - `test_class_uses_self_reference_omitted`
    - `test_module_depends_both_paths`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 3 (após 2.1, 2.2)
  - **Parallel Group**: Wave 3
  - **Blocks**: N/A
  - **Blocked By**: 2.1, 2.2

  **Commit**: YES (groups with 2.1, 2.2)
  - Message: `test(postprocessing): add derived edges test scenarios`
  - Files: `tests/test_postprocessing.py`, `tests/fixtures/`

- [x] 2.4. **Integração: ambos pipelines usam lógica consolidada**

  **What to do**:
  - Garantir que `postprocessing.py:run_post_processing()` e `tools/build.py:_run_postprocess()` chamam a mesma função de derivação
  - Adicionar chamada para `derive_class_uses()` e `derive_module_depends()` em ambos
  - Verificar se `incremental.py` chama o pipeline correto

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: NO (sequencial)
  - **Blocks**: N/A
  - **Blocked By**: 0.5, 2.1, 2.2

  **Commit**: YES
  - Message: `feat(integration): wire derived edge computation into both post-pipelines`
  - Files: `code_review_graph/postprocessing.py`, `code_review_graph/tools/build.py`, `code_review_graph/incremental.py`

- [x] 2.5. **Edge budget config toggle**

  **What to do**:
  - Adicionar env var `CRG_USES_TYPE` (default `1`): se `0`, parser não extrai USES_TYPE
  - Adicionar env var `CRG_DERIVED_EDGES` (default `1`): se `0`, post-processing não deriva
  - Documentar em `README.md`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 3
  - **Parallel Group**: Wave 3
  - **Blocks**: N/A
  - **Blocked By**: 1.2, 2.1, 2.2

  **References**:
  - `code_review_graph/constants.py`, `README.md`

  **Commit**: YES
  - Message: `feat(config): add CRG_USES_TYPE and CRG_DERIVED_EDGES toggles`
  - Files: `code_review_graph/constants.py`, `code_review_graph/parser.py`, `code_review_graph/postprocessing.py`, `README.md`

---

### Fase 3: MCP Tools + Visualization

- [x] 3.1. **query_graph: pattern `class_callers_of`**

  **What to do**:
  - Em `code_review_graph/tools/query.py:query_graph()`:
    - Adicionar pattern `class_callers_of`:
      1. Encontrar todos os métodos da classe alvo (via CONTAINS)
      2. Para cada método, encontrar CALLERS (via `get_edges_by_target`)
      3. Para cada caller, subir para classe container (via CONTAINS reverse)
      4. Retornar lista única de classes
    - Adicionar descrição em `_QUERY_PATTERNS`

  **Must NOT do**:
  - ❌ Não incluir self-calls

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4 (paralelo com 3.2)
  - **Parallel Group**: Wave 4
  - **Blocks**: N/A
  - **Blocked By**: 0.1, 2.1

  **References**:
  - `code_review_graph/tools/query.py:139-345` — `query_graph()`
  - `code_review_graph/tools/query.py:22-31` — `_QUERY_PATTERNS`

  **Acceptance Criteria**:
  - [ ] `query_graph(pattern="class_callers_of", target="file.py::AuthService")` retorna classes que chamam AuthService
  - [ ] Exclui self-calls
  - [ ] Retorna `via_method` para cada caller

  **QA Scenarios**:
  ```
  Scenario: class_callers_of returns correct callers
    Tool: Bash
    Steps:
      1. Build with class hierarchy
      2. Call query_graph with class_callers_of
      3. Verify all calling classes returned
    Expected Result: All calling classes returned with via_method info
    Evidence: .sisyphus/evidence/task-3.1-class-callers.txt
  ```

  **Commit**: YES (groups with 3.2)
  - Message: `feat(tools): add class_callers_of query_graph pattern`
  - Files: `code_review_graph/tools/query.py`

- [x] 3.2. **query_graph: pattern `class_callees_of`**

  **What to do**:
  - Simétrico a 3.1: encontrar classes chamadas pelos métodos da classe alvo
  - Adicionar descrição em `_QUERY_PATTERNS`

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4
  - **Parallel Group**: Wave 4
  - **Blocks**: N/A
  - **Blocked By**: 0.1, 2.1

  **Commit**: YES (groups with 3.1)
  - Message: `feat(tools): add class_callees_of query_graph pattern`
  - Files: `code_review_graph/tools/query.py`

- [x] 3.3. **dependency_matrix tool**

  **What to do**:
  - Criar ferramenta MCP `dependency_matrix` em `code_review_graph/tools/analysis_tools.py`:
    - **Input**: `scope` (file_path, module prefix, class name) e `depth` (1-3)
    - **Output**: Matriz de dependências:
      - Para cada entidade: quais ela usa e quais a usam
      - Nível de acoplamento, direção (uni/bidirecional)
    - **Modos**:
      1. `class_level`: usa CLASS_USES on-the-fly
      2. `module_level`: usa MODULE_DEPENDS_ON + IMPORTS_FROM
    - Métricas: `coupling_score`, `hub_classes`, `leaf_classes`

  **Must NOT do**:
  - ❌ Não exceder 500 nós

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4
  - **Parallel Group**: Wave 4
  - **Blocks**: N/A
  - **Blocked By**: 0.1, 2.1, 2.2

  **References**:
  - `code_review_graph/tools/analysis_tools.py`
  - `code_review_graph/tools/_common.py`

  **Acceptance Criteria**:
  - [ ] `dependency_matrix(scope="auth/", mode="class_level")` retorna matriz
  - [ ] `dependency_matrix(scope="auth/", mode="module_level")` retorna matriz
  - [ ] Inclui `coupling_score`, `hub_classes`, `leaf_classes`

  **QA Scenarios**:
  ```
  Scenario: dependency_matrix returns correct matrix
    Tool: Bash
    Steps:
      1. Build multi-module project
      2. Call dependency_matrix tool
    Expected Result: Valid dependency matrix with scores
    Evidence: .sisyphus/evidence/task-3.3-dep-matrix.txt
  ```

  **Commit**: YES (groups with 3.4)
  - Message: `feat(tools): add dependency_matrix MCP tool`
  - Files: `code_review_graph/tools/analysis_tools.py`, `code_review_graph/tools/__init__.py`, `code_review_graph/main.py`
  - Pre-commit: `pytest tests/`

- [x] 3.4. **Atualizar visualization para novos edge types**

  **What to do**:
  - Em `code_review_graph/visualization.py`:
    - Adicionar `DECORATED_BY`, `USES_TYPE`, `CLASS_USES`, `MODULE_DEPENDS_ON` ao mapa de cores
    - D3.js: adicionar toggle de visibilidade para novos edge types
  - Em `code_review_graph/exports.py`:
    - GraphML/Cypher/Obsidian exports incluem novos edge types

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4
  - **Parallel Group**: Wave 4
  - **Blocks**: N/A
  - **Blocked By**: 0.1, 1.1, 1.2, 2.1, 2.2

  **References**:
  - `code_review_graph/visualization.py:600-650` — edge kind handling
  - `code_review_graph/exports.py`

  **Commit**: YES (groups with 3.3)
  - Message: `feat(visualization): add new edge types to color map and legend`
  - Files: `code_review_graph/visualization.py`, `code_review_graph/exports.py`

---

### Fase 4: Enrichment Framework

- [x] 4.1. **Generic `_run_enricher` pattern**

  **What to do**:
  - Em `code_review_graph/incremental.py`:
    - Extrair padrão `_run_rescript_resolver` (linhas ~28-37) para função genérica `_run_enricher(language, store, repo_root)`
    - Dicionário: `_ENRICHERS: dict[str, Callable] = {"rescript": ..., "python": enrich_jedi_calls}`
    - Try/except silencioso, logging

  **Must NOT do**:
  - ❌ Não criar plugin system abstrato — simples dict

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4
  - **Parallel Group**: Wave 4
  - **Blocks**: 4.2, 4.3
  - **Blocked By**: 0.3

  **References**:
  - `code_review_graph/incremental.py:28-37` — padrão `_run_rescript_resolver`

  **Commit**: YES (groups with 4.2, 4.3)
  - Message: `refactor(enrichment): extract generic _run_enricher pattern`
  - Files: `code_review_graph/incremental.py`

- [x] 4.2. **Registrar Jedi enricher no pipeline de build**

  **What to do**:
  - Usar `_run_enricher` genérico para chamar Jedi
  - Em `full_build()`: após `resolve_bare_call_targets()`, `_run_enricher("python", store, repo_root)`
  - Em `incremental_update()`: apenas para arquivos Python alterados

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4 (após 4.1)
  - **Blocks**: N/A
  - **Blocked By**: 4.1, 0.3

  **Commit**: YES (groups with 4.1, 4.3)
  - Message: `feat(enrichment): register Jedi enricher in build pipeline`
  - Files: `code_review_graph/incremental.py`

- [x] 4.3. **Language→enricher mapping config**

  **What to do**:
  - Em `code_review_graph/constants.py`, adicionar `ENRICHER_MAP`
  - CLI command `code-review-graph enrich <language>` para executar manualmente
  - Documentar como adicionar novos enrichers

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4
  - **Blocks**: N/A
  - **Blocked By**: 4.1

  **References**:
  - `code_review_graph/cli.py`
  - `code_review_graph/constants.py`

  **Commit**: YES (groups with 4.1, 4.2)
  - Message: `feat(enrichment): add language→enricher mapping and CLI enrich command`
  - Files: `code_review_graph/constants.py`, `code_review_graph/incremental.py`, `code_review_graph/cli.py`

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each Must Have: verify implementation exists. For each Must NOT Have: search for forbidden patterns. Check evidence files.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality + Tests Review** — `unspecified-high`
  Run `pytest tests/` + lint. Check: no `# type: ignore` without justification, no `except: pass`, edge kind constants used everywhere (no bare strings).
  Output: `Tests [N pass/N fail] | Lint [PASS/FAIL] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` for visualization)
  Start from clean state. Execute EVERY QA scenario from EVERY task. Test cross-task integration (e.g., parser + derived edges + query tool). Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything built, nothing beyond scope. Check Must NOT do compliance.
  Output: `Tasks [N/N compliant] | Scope Creep [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| Commit | Files | Message |
|--------|-------|---------|
| 0.1 | constants.py + 10 files | `refactor(constants): add EdgeKind enum, refactor all string literals` |
| 0.2+0.4 | incremental.py, tests/ | `fix(pipeline): wire resolve_bare_call_targets into build pipeline` |
| 0.3+0.4 | incremental.py, tests/ | `feat(pipeline): wire enrich_jedi_calls into full build pipeline` |
| 0.5 | postprocessing.py, tools/build.py | `refactor(postprocessing): consolidate duplicated post-pipeline` |
| 0.6 | migrations.py, graph.py | `feat(migrations): add v10 — new composite indexes for edges` |
| 1.1+1.4 | parser.py, tests/ | `feat(parser): extract DECORATED_BY edges for functions and classes` |
| 1.2+1.5 | parser.py, tests/ | `feat(parser): extract USES_TYPE edges for explicit type annotations` |
| 1.3+1.6 | parser.py, graph.py, tests/ | `feat(parser): improve cross-file CALLS resolution` |
| 2.1+2.2+2.3 | postprocessing.py, graph.py, tests/ | `feat(postprocessing): on-the-fly CLASS_USES + MODULE_DEPENDS_ON` |
| 2.4 | postprocessing.py, tools/build.py, incremental.py | `feat(integration): wire derived edges into both post-pipelines` |
| 2.5 | constants.py, parser.py, postprocessing.py, README.md | `feat(config): add CRG_USES_TYPE and CRG_DERIVED_EDGES toggles` |
| 3.1+3.2 | tools/query.py | `feat(tools): add class_callers_of and class_callees_of query patterns` |
| 3.3+3.4 | analysis_tools.py, visualization.py, exports.py, main.py | `feat(tools): add dependency_matrix tool + visualization update` |
| 4.1+4.2+4.3 | incremental.py, constants.py, cli.py | `feat(enrichment): generic _run_enricher + Jedi registration + CLI` |

---

## Success Criteria

### Verification Commands
```bash
pytest tests/ -v                                    # All tests pass
pytest tests/ -k "decorator or type or class_uses"   # New tests pass
ruff check code_review_graph/                        # No lint errors
python -c "from code_review_graph.constants import EdgeKind; print(EdgeKind.CALLS.value)"  # Constants work
```

### Final Checklist
- [ ] `resolve_bare_call_targets()` e `enrich_jedi_calls()` no pipeline
- [ ] EdgeKind constants module — zero raw strings (exceto schema SQL)
- [ ] DECORATED_BY edges para funções e classes
- [ ] USES_TYPE edges para anotações explícitas
- [ ] CLASS_USES e MODULE_DEPENDS_ON on-the-fly
- [ ] query_graph patterns: class_callers_of, class_callees_of
- [ ] dependency_matrix tool
- [ ] Visualization + exports para novos edge types
- [ ] _run_enricher genérico + Jedi registrado
- [ ] Config toggles: CRG_USES_TYPE, CRG_DERIVED_EDGES
- [ ] Post-processing pipeline consolidado
- [ ] Migration v10 com novos índices
- [ ] Todos os testes passando
- [ ] Bare CALLS ratio reduzido >=30%
- [ ] Edge count increase <50%

### Original Request
Análise completa para implementação de grafos de funções e uso (usage graphs) no code-review-graph. Atualmente a biblioteca só tem grafos básicos de classes com resolução cross-file fraca. O usuário quer suporte a refactoring: "função da classe X é chamada em classe Y", "classe Y estende de Z", "quem usa o tipo Request?".

### Interview Summary
**Decisões do usuário**:
- **Resolução cross-file**: Parse básico + enriquecimento pós-parse (ambos)
- **Usage edges**: Ambos — parser cria arestas diretas (DECORATED_BY, USES_TYPE) + pós-processamento deriva agregadas (CLASS_USES, MODULE_DEPENDS_ON)
- **Type usage tracking**: SIM, fundamental para refactoring

### Metis Review
**Descobertas críticas**:
- `resolve_bare_call_targets()` e `enrich_jedi_calls()` são código morto (nunca chamados) — PRIORIDADE MÁXIMA consertar antes de qualquer melhoria
- Pipeline de pós-processamento duplicado em `postprocessing.py` e `tools/build.py`
- Edge kinds são strings literais em 10+ arquivos — precisa de constantes
- DECORATED_BY e USES_TYPE NÃO precisam de migration (só novos valores na coluna `kind` da tabela `edges`)
- USES_TYPE pode dobrar contagem de arestas — precisa de controle de budget

---

## Work Objectives

### Core Objective
Implementar function-level e usage graphs completos para análise de impacto em refactoring, com resolução cross-file de chamadas, arestas de tipo/decorator, e dependências agregadas entre classes/módulos.

### Concrete Deliverables
- Phase 0: Código morto no pipeline + testes + baseline metric
- Phase 1: EdgeKind constants + DECORATED_BY + USES_TYPE + parser cross-file
- Phase 2: Post-processing consolidado + CLASS_USES + MODULE_DEPENDS_ON on-the-fly
- Phase 3: MCP tools (class_callers_of, class_callees_of, dependency_matrix) + visualization
- Phase 4: Enrichment framework genérico (lang→enricher) + Jedi no pipeline

### Must Have
- [ ] `resolve_bare_call_targets()` chamado no build pipeline
- [ ] `enrich_jedi_calls()` chamado no build pipeline (se Jedi instalado)
- [ ] EdgeKind constants module em `constants.py`
- [ ] DECORATED_BY edges para funções e classes em Python + TypeScript
- [ ] USES_TYPE edges para anotações explícitas de tipo (params, return type, var type)
- [ ] Post-processing pipeline único (não duplicado)
- [ ] CLASS_USES derivado on-the-fly de CALLS + CONTAINS
- [ ] MODULE_DEPENDS_ON derivado on-the-fly de IMPORTS_FROM + CALLS
- [ ] query_graph pattern `class_callers_of` e `class_callees_of`
- [ ] dependency_matrix tool
- [ ] Migration v10 para novos índices

### Must NOT Have (Guardrails)
- ❌ NÃO armazenar derived edges em tabela própria (computed on-the-fly)
- ❌ NÃO fazer plugin system abstrato para enrichment (simples dict)
- ❌ NÃO incluir TypeScript enrichment neste escopo (documentar como follow-up)
- ❌ NÃO adicionar data-flow analysis ou type inference
- ❌ NÃO resolver decorator/type names para qualified nodes em Phase 1 (bare strings)
- ❌ NÃO aumentar edge count em mais de 50% (config toggle se necessário)
- ❌ NÃO quebrar queries existentes (backward compatibilidade)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — TODA verificação é executada por agente.
> Critérios de aceite que requerem "usuário testa manualmente" são PROIBIDOS.

### Test Decision
- **Infrastructure exists**: YES (pytest, pytest-asyncio)
- **Automated tests**: TDD — cada tarefa segue RED (teste falha) → GREEN (impl) → REFACTOR
- **Framework**: pytest + pytest-cov

### QA Policy
Cada tarefa inclui cenários de QA executados por agente. Evidências em `.sisyphus/evidence/task-{N}-{slug}.{ext}`.

- **Parser tests**: Bash (pytest em fixtures específicas) — executar teste + verificar saída
- **Graph queries**: Bash (scripts Python que usam GraphStore diretamente) — verificar resultados
- **MCP tools**: Bash (curl para endpoint stdio ou chamada direta) — verificar JSON response
- **Migration**: Bash (SQLite queries) — verificar schema version + índices

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation + Dead Code Revival):
├── Task 0.1: EdgeKind constants module + refactor [quick]
├── Task 0.2: Wire resolve_bare_call_targets into pipeline [quick]
├── Task 0.3: Wire enrich_jedi_calls into pipeline [quick]
├── Task 0.4: Tests + baseline metric for bare CALLS [quick]
├── Task 0.5: Refactor duplicated post-processing [quick]
└── Task 0.6: Migration v10 (new indexes) [quick]

Wave 2 (Parser — DECORATED_BY + USES_TYPE + cross-file):
├── Task 1.1: Parser — DECORATED_BY for functions/classes [deep]
├── Task 1.2: Parser — USES_TYPE for type annotations [deep]
├── Task 1.3: Parser — improved cross-file CALLS resolution [deep]
├── Task 1.4: Tests — DECORATED_BY scenarios [quick]
├── Task 1.5: Tests — USES_TYPE scenarios [quick]
└── Task 1.6: Tests — cross-file CALLS resolution [deep]

Wave 3 (Derived Edges):
├── Task 2.1: CLASS_USES derivation on-the-fly [unspecified-high]
├── Task 2.2: MODULE_DEPENDS_ON derivation on-the-fly [unspecified-high]
├── Task 2.3: Tests — derived edges [quick]
├── Task 2.4: Integration — both post-pipelines use consolidated logic [unspecified-high]
└── Task 2.5: Edge budget config toggle [quick]

Wave 4 (MCP Tools + Visualization + Enrichment):
├── Task 3.1: query_graph — class_callers_of pattern [unspecified-high]
├── Task 3.2: query_graph — class_callees_of pattern [unspecified-high]
├── Task 3.3: dependency_matrix tool [deep]
├── Task 3.4: Update visualization for new edge types [visual-engineering]
├── Task 4.1: Generic _run_enricher pattern [unspecified-high]
├── Task 4.2: Register Jedi enricher in build pipeline [quick]
└── Task 4.3: Language→enricher mapping config [quick]

Wave FINAL (Verification):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality + tests review (unspecified-high)
├── Task F3: Real manual QA (playwright/bash) (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

---

## TODOs

### Fase 0: Fundação + Código Morto

*(Tasks 0.1-0.4 above)*

- [x] 0.5. **Refatorar pipeline de pós-processamento duplicado**

  **What to do**:
  - Identificar lógica duplicada entre `code_review_graph/postprocessing.py` (`run_post_processing()`) e `code_review_graph/tools/build.py` (`_run_postprocess()`)
  - Extrair lógica comum para uma função compartilhada em `code_review_graph/postprocessing.py` (ex: `_compute_signatures()`, `_rebuild_fts()`, `_detect_communities()`)
  - `tools/build.py:_run_postprocess()` deve chamar a mesma função compartilhada
  - Garantir que CLI (`code-review-graph build`) e MCP (`build_or_update_graph_tool`) usem o mesmo código

  **Must NOT do**:
  - ❌ Não mudar comportamento ou ordem das operações
  - ❌ Não renomear funções públicas sem aliases de backward compat

  **Recommended Agent Profile**:
  - **Category**: `quick` — refatoração mecânica, lógica existente
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1 (pode rodar paralelo com 0.1)
  - **Parallel Group**: Wave 1
  - **Blocks**: 2.1, 2.2, 2.4
  - **Blocked By**: None

  **References**:
  - `code_review_graph/postprocessing.py` — `run_post_processing()`
  - `code_review_graph/tools/build.py` — `_run_postprocess()`
  - `code_review_graph/incremental.py` — como chama `run_post_processing`

  **Commit**: YES
  - Message: `refactor(postprocessing): consolidate duplicated post-pipeline logic`
  - Files: `code_review_graph/postprocessing.py`, `code_review_graph/tools/build.py`
  - Pre-commit: `pytest tests/`

- [x] 0.6. **Migration v10: novos índices para edges**

  **What to do**:
  - Criar migration v10 em `code_review_graph/migrations.py`
  - Novos índices compostos para queries de novos edge types:
    ```sql
    CREATE INDEX IF NOT EXISTS idx_edges_kind_target ON edges(kind, target_qualified);
    CREATE INDEX IF NOT EXISTS idx_edges_kind_source ON edges(kind, source_qualified);
    ```
  - Atualizar `_SCHEMA_SQL` em `graph.py` com os novos índices
  - Atualizar `get_schema_version` para reconhecer v10

  **Must NOT do**:
  - ❌ Não alterar colunas existentes
  - ❌ Não remover índices existentes
  - ❌ Não adicionar tabelas novas (só índices)

  **Recommended Agent Profile**:
  - **Category**: `quick` — migration simples
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1
  - **Parallel Group**: Wave 1 (pode ser feito em paralelo com tudo)
  - **Blocks**: N/A
  - **Blocked By**: None

  **References**:
  - `code_review_graph/migrations.py` — migrations existentes (v1-v9)
  - `code_review_graph/graph.py:31-78` — `_SCHEMA_SQL` com índices existentes
  - `code_review_graph/graph.py:157-163` — `get_schema_version`

  **Commit**: YES
  - Message: `feat(migrations): add v10 — new composite indexes for edges`
  - Files: `code_review_graph/migrations.py`, `code_review_graph/graph.py`

---

### Fase 1: Parser — DECORATED_BY + USES_TYPE + Cross-file CALLS

- [x] 1.1. **Parser: extrair arestas DECORATED_BY para funções e classes**

  **What to do**:
  - Em `code_review_graph/parser.py:_extract_functions()`:
    - Decorators já são extraídos para detecção de teste (linhas ~2833-2849)
    - Para cada decorator encontrado, emitir aresta `EdgeKind.DECORATED_BY`:
      - `source`: qualified name da função/classe decorada
      - `target`: nome do decorator (bare string — sem resolução)
      - `file_path`: arquivo atual
      - `line`: linha do decorator
  - Em `code_review_graph/parser.py:_extract_classes()`:
    - Também extrair decorators de classe (Python `@dataclass`, TypeScript decorators)
    - Verificar AST child types para decorators em Python (parent `decorated_definition`) e TypeScript (child de class_declaration)
  - Decorator factories (`@decorator(arg)`) devem extrair apenas o nome base do decorator (antes dos parênteses)
  - Usar `EdgeKind.DECORATED_BY` do módulo de constantes

  **Must NOT do**:
  - ❌ Não tentar resolver nome do decorator para qualified name
  - ❌ Não pular decoradores de classe (ex: `@dataclass`)
  - ❌ Não incluir argumentos do decorator no target

  **Recommended Agent Profile**:
  - **Category**: `deep` — precisa entender AST patterns de várias linguagens
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 2 (paralelo com 1.2, 1.3)
  - **Parallel Group**: Wave 2
  - **Blocks**: 1.4
  - **Blocked By**: 0.1

  **References**:
  - `code_review_graph/parser.py:2723-2801` — `_extract_classes()`
  - `code_review_graph/parser.py:2803-2909` — `_extract_functions()` (linhas ~2833-2849 decorator extraction)
  - `code_review_graph/parser.py:305-340` — `_TEST_ANNOTATIONS` (exemplo de uso de decorators)
  - `code_review_graph/parser.py:EdgeInfo` — como criar aresta (linhas ~58-67)
  - tests/fixtures/sample_python.py — decorator `@_log_action` (linha ~40)
  - tests/fixtures/sample_typescript.ts — classe com decorator (se houver)

  **Acceptance Criteria**:
  - [ ] Função Python com `@log_action` → aresta DECORATED_BY: `guarded_process` → `log_action`
  - [ ] Classe Python com `@dataclass` → aresta DECORATED_BY: `MyClass` → `dataclass`
  - [ ] Função TypeScript com `@Route("/api")` → aresta DECORATED_BY: `handler` → `Route`
  - [ ] Decorator factory `@cache(ttl=60)` → target é `cache`, não `cache(ttl=60)`
  - [ ] Múltiplos decorators: 3 arestas DECORATED_BY para 3 decorators

  **QA Scenarios**:
  ```
  Scenario: Python function with decorator produces DECORATED_BY edge
    Tool: Bash
    Preconditions: Fixture with @log_action def guarded_process()
    Steps:
      1. Run parser on fixture: python -c "from code_review_graph.parser import CodeParser; p=CodeParser(); n,e=p.parse_file(Path('tests/fixtures/sample_python.py')); print([x for x in e if x.kind=='DECORATED_BY'])"
      2. Check output for edge: source="...guarded_process", target="log_action"
    Expected Result: DECORATED_BY edge present with correct source/target
    Evidence: .sisyphus/evidence/task-1.1-decorated-by-py.txt

  Scenario: Python class with @dataclass produces DECORATED_BY
    Tool: Bash
    Preconditions: Fixture with @dataclass class MyClass
    Steps:
      1. Same parser command with appropriate fixture
    Expected Result: DECORATED_BY edge: source="...MyClass", target="dataclass"
    Evidence: .sisyphus/evidence/task-1.1-decorated-by-class.txt
  ```

  **Commit**: YES (groups with 1.4, 1.5, 1.6)
  - Message: `feat(parser): extract DECORATED_BY edges for functions and classes`
  - Files: `code_review_graph/parser.py`
  - Pre-commit: `pytest tests/ -k "decorator"`

- [x] 1.2. **Parser: extrair arestas USES_TYPE para anotações de tipo explícitas**

  **What to do**:
  - Em `code_review_graph/parser.py:_extract_functions()`:
    - Após extrair `params` e `return_type`, analisar o texto para encontrar referências a tipos
    - Para cada tipo identificado em parâmetros E return_type, emitir aresta `EdgeKind.USES_TYPE`:
      - `source`: qualified name da função
      - `target`: nome do tipo (bare string — sem resolução)
      - `file_path`: arquivo atual
      - `line`: linha da definição da função
      - `extra`: `{"role": "param"}` ou `{"role": "return"}`
  - **Parser-level apenas** (não type inference):
    - Python: extrair de `param: TypeName` e `-> ReturnType` no source text
    - TypeScript: extrair de type annotations no AST
    - Union types (`int | None`): extrair cada componente separadamente
    - Tipos genéricos (`List[User]`): extrair `List` e `User` como arestas separadas
  - Pular tipos primitivos/built-in (`int`, `str`, `bool`, `float`, `None`, `void`, `string`, `number`, etc.)
  - Usar `EdgeKind.USES_TYPE` do módulo de constantes

  **Edge Budget**: Se o número de arestas aumentar >50% no repositório de teste, adicionar config toggle `CRG_USES_TYPE=0` para desabilitar.

  **Must NOT do**:
  - ❌ Não fazer type inference/resolution
  - ❌ Não resolver tipo para qualified name
  - ❌ Não incluir tipos genéricos/genéric parameters (ex: `T` em `def fn[T](x: T)`)
  - ❌ Não incluir tipos built-in/primitivos
  - ❌ Não rastrear tipos em variáveis locais (só params + return + class fields)

  **Recommended Agent Profile**:
  - **Category**: `deep` — parsing de type annotations em múltiplas linguagens
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 2
  - **Parallel Group**: Wave 2
  - **Blocks**: 1.5
  - **Blocked By**: 0.1

  **References**:
  - `code_review_graph/parser.py:4057-4075` — `_get_params()`
  - `code_review_graph/parser.py:4077-4087` — `_get_return_type()`
  - `tests/fixtures/sample_python.py — `def process_request(url: str, timeout: int = 30) -> dict`
  - `tests/fixtures/sample_typescript.ts` — type annotations TS
  - `docs/schema.md:30-58` — Function node schema (params, return_type)

  **Acceptance Criteria**:
  - [ ] Função `def find(id: int) -> User` → USES_TYPE edges: `find` → `User` (pula `int` por ser built-in)
  - [ ] Função `def process(request: Request) -> Response` → USES_TYPE: `process` → `Request`, `process` → `Response`
  - [ ] Union type `def find(id: int | None) -> User | None` → USES_TYPE: `find` → `User` (pula built-ins)
  - [ ] TypeScript `function greet(name: string): Greeting` → USES_TYPE: `greet` → `Greeting`
  - [ ] Config toggle `CRG_USES_TYPE=0` desabilita extração
  - [ ] Arestas USES_TYPE têm `extra={"role": "param"}` ou `"return"`

  **QA Scenarios**:
  ```
  Scenario: Python function with typed params produces USES_TYPE edges
    Tool: Bash
    Preconditions: Fixture with typed function
    Steps:
      1. Parse sample_python.py, filter USES_TYPE edges
      2. Check edges exist for non-builtin types
      3. Verify extra field has role="param" or "return"
    Expected Result: USES_TYPE edges present with correct role
    Evidence: .sisyphus/evidence/task-1.2-uses-type-py.txt

  Scenario: Edge count budget check
    Tool: Bash
    Preconditions: Full build on test repo
    Steps:
      1. Build: code-review-graph build
      2. Query: SELECT COUNT(*) FROM edges
      3. Compare with pre-change baseline
    Expected Result: Edge count increase < 50%
    Evidence: .sisyphus/evidence/task-1.2-edge-budget.txt
  ```

  **Commit**: YES (groups with 1.5)
  - Message: `feat(parser): extract USES_TYPE edges for explicit type annotations`
  - Files: `code_review_graph/parser.py`
  - Pre-commit: `pytest tests/ -k "type"`

- [x] 1.3. **Parser: melhorar resolução cross-file de CALLS**

  **What to do**:
  - Em `code_review_graph/parser.py:_resolve_call_target()`:
    - Atualmente só verifica `defined_names` (mesmo arquivo) e `import_map`
    - Melhorar para também verificar:
      - Se o target é um atributo importado via `from X import Y`, resolver para `X.Y`
      - Se o target é um alias (ex: `from X import Y as Z`), usar o nome original na resolução
  - Em `code_review_graph/parser.py:_collect_file_scope()`:
    - Também coletar imports de módulos completos (`import X.Y.Z`) onde `X.Y.Z.func()` é chamado
  - Em `code_review_graph/graph.py:resolve_bare_call_targets()`:
    - Melhorar desambiguação: usar CONTAINS edges para encontrar métodos de classes
    - Se um bare name corresponde a um método de classe que está no mesmo arquivo de um import da fonte, resolver

  **Must NOT do**:
  - ❌ Não adicionar resolução baseada em type inference (ex: Jedi — isso é enrichment)
  - ❌ Não quebrar resolução existente para intra-file

  **Recommended Agent Profile**:
  - **Category**: `deep` — lógica de resolução com múltiplos critérios
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 2
  - **Parallel Group**: Wave 2
  - **Blocks**: 1.6
  - **Blocked By**: 0.1, 0.2

  **References**:
  - `code_review_graph/parser.py:3789-3806` — `_resolve_call_target()`
  - `code_review_graph/parser.py:3497-3568` — `_collect_file_scope()`
  - `code_review_graph/parser.py:3585-3649` — `_collect_import_names()`
  - `code_review_graph/graph.py:466-542` — `resolve_bare_call_targets()`
  - `tests/fixtures/caller_example.py` — teste de resolução cross-file
  - `tests/fixtures/sample_python.py` — definições alvo

  **Acceptance Criteria**:
  - [ ] `from auth import AuthService; svc = AuthService()` → `AuthService` resolvido no target
  - [ ] `import os.path; os.path.join(...)` → `join` resolvido se `os.path` está no import_map
  - [ ] `from X import Y as Z; Z.func()` → target `Y.func` (alias resolvido)
  - [ ] Bare CALLS ratio reduzido em pelo menos 30% vs baseline
  - [ ] `pytest tests/` passa

  **QA Scenarios**:
  ```
  Scenario: Import alias resolution
    Tool: Bash
    Preconditions: Fixture with "from X import Y as Z; Z.func()"
    Steps:
      1. Parse fixture, inspect CALLS edges
      2. Verify target is qualified to Y's definition location
    Expected Result: CALLS target is qualified name, not bare "func"
    Evidence: .sisyphus/evidence/task-1.3-crossfile-resolution.txt
  ```

  **Commit**: YES (groups with 1.6)
  - Message: `feat(parser): improve cross-file CALLS resolution for imported symbols`
  - Files: `code_review_graph/parser.py`, `code_review_graph/graph.py`
  - Pre-commit: `pytest tests/`

---



- [x] 0.1. **Criar módulo `EdgeKind` de constantes e refatorar código existente**

  **What to do**:
  - Criar `EdgeKind` enum (ou classe com constantes) em `code_review_graph/constants.py`
  - Incluir todos os kinds existentes: `CALLS`, `IMPORTS_FROM`, `INHERITS`, `IMPLEMENTS`, `CONTAINS`, `TESTED_BY`, `DEPENDS_ON`, `REFERENCES`
  - Incluir os novos (já definidos): `DECORATED_BY`, `USES_TYPE`, `CLASS_USES`, `MODULE_DEPENDS_ON`
  - Refatorar `parser.py`, `graph.py`, `tools/query.py`, `enrich.py`, `jedi_resolver.py`, `exports.py`, `visualization.py`, `changes.py`, `postprocessing.py`, `tools/build.py` para usar as constantes em vez de strings literais
  - **Não** quebrar serialização (JSON/store usa strings, então `EdgeKind.CALLS.value`)

  **Must NOT do**:
  - ❌ Não mudar o schema SQL (coluna `kind` continua TEXT)
  - ❌ Não renomear valores existentes (backward compat)

  **Recommended Agent Profile**:
  - **Category**: `quick` (mecânico, bem definido, muitos arquivos mas mesma mudança)
  - **Skills**: N/A — refatoração mecânica

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1 (pode rodar paralelo com 0.5)
  - **Parallel Group**: Wave 1 (com Tasks 0.5)
  - **Blocks**: Tasks 1.1, 1.2, 1.3, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1
  - **Blocked By**: None

  **References**:
  - `code_review_graph/constants.py` — destino das constantes (criar se não existir)
  - `code_review_graph/parser.py:60-61` — EdgeInfo.kind aceita string
  - `code_review_graph/graph.py:50-77` — schema SQL com edge kind strings
  - `code_review_graph/graph.py:101-109` — GraphEdge dataclass
  - `code_review_graph/tools/query.py:218-303` — query_graph com strings hardcoded
  - `code_review_graph/exports.py` — export com filtros de edge kind
  - `code_review_graph/visualization.py:606+` — edge kind handling no HTML

  **Acceptance Criteria**:
  - [ ] `from code_review_graph.constants import EdgeKind` funciona
  - [ ] `EdgeKind.CALLS.value == "CALLS"`
  - [ ] Nenhum arquivo em `code_review_graph/` usa string literal `"CALLS"` (exceto schema SQL na tabela edges)
  - [ ] `pytest tests/` passa sem falhas
  - [ ] Nenhuma mudança no schema SQL (coluna `kind` continua TEXT)

  **QA Scenarios**:
  ```
  Scenario: EdgeKind constants are accessible and correct
    Tool: Bash
    Preconditions: EdgeKind module exists
    Steps:
      1. Run: python -c "from code_review_graph.constants import EdgeKind; print(EdgeKind.CALLS.value)"
      2. Assert output is "CALLS"
    Expected Result: "CALLS" printed
    Evidence: .sisyphus/evidence/task-0.1-edgekind-constants.txt

  Scenario: All edge kind strings are now from constants
    Tool: Bash
    Preconditions: Refactoring complete
    Steps:
      1. Run: grep -rn '"CALLS"' code_review_graph/ --include='*.py' | grep -v test | grep -v '__pycache__' | grep -v 'schema\|CREATE TABLE\|edges.kind'
      2. Count matches — should be 0 (schema SQL is allowed)
    Expected Result: 0 matches (or only schema/DB engine references)
    Evidence: .sisyphus/evidence/task-0.1-edgekind-no-literals.txt
  ```

  **Commit**: YES
  - Message: `refactor(constants): add EdgeKind enum, refactor all string literals`
  - Files: `code_review_graph/constants.py`, `code_review_graph/parser.py`, `code_review_graph/graph.py`, `code_review_graph/tools/query.py`, `code_review_graph/enrich.py`, `code_review_graph/jedi_resolver.py`, `code_review_graph/exports.py`, `code_review_graph/visualization.py`, `code_review_graph/changes.py`, `code_review_graph/postprocessing.py`, `code_review_graph/tools/build.py`
  - Pre-commit: `pytest tests/`

- [x] 0.2. **Wire `resolve_bare_call_targets()` no pipeline de build**

  **What to do**:
  - Em `code_review_graph/incremental.py`:
    - Na função `full_build()`: após `store.store_file_batch(batch)`, chamar `store.resolve_bare_call_targets()`
    - Na função `incremental_update()`: após processar arquivos alterados, chamar `store.resolve_bare_call_targets()` se houver edges novos
  - Seguir o padrão de `_run_rescript_resolver()` (linhas ~28-37): chamar dentro do escopo do `GraphStore`, sem bloqueio, logging do número de resoluções
  - Adicionar log: `logger.info("resolve_bare_call_targets: resolved %d edges", count)`

  **Must NOT do**:
  - ❌ Não mudar a lógica interna de `resolve_bare_call_targets` (só conectar)
  - ❌ Não tornar obrigatório para o build (deve ser seguro chamar mesmo sem edges bare)

  **Recommended Agent Profile**:
  - **Category**: `quick` — mudança localizada, seguir padrão existente
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1
  - **Parallel Group**: Wave 1
  - **Blocks**: 0.4, 1.3
  - **Blocked By**: None

  **References**:
  - `code_review_graph/incremental.py:28-37` — padrão `_run_rescript_resolver`
  - `code_review_graph/incremental.py:full_build()` — ~linha 800
  - `code_review_graph/incremental.py:incremental_update()` — ~linha 930
  - `code_review_graph/graph.py:466-542` — `resolve_bare_call_targets()` (código morto)
  - `code_review_graph/parser.py:1678-1715` — `_resolve_call_targets` (per-file)

  **Acceptance Criteria**:
  - [ ] `resolve_bare_call_targets()` é chamada durante `full_build`
  - [ ] `resolve_bare_call_targets()` é chamada durante `incremental_update`
  - [ ] Log mostra `"Resolved N bare-name CALLS targets"` após build
  - [ ] `pytest tests/` passa

  **QA Scenarios**:
  ```
  Scenario: Bare CALLS targets are resolved after build
    Tool: Bash
    Preconditions: Graph with a Python file that calls an external function
    Steps:
      1. Build graph: python -m code_review_graph.cli build
      2. Query bare CALLS count:
         sqlite3 .code-review-graph/graph.db "SELECT COUNT(*) FROM edges WHERE kind='CALLS' AND target_qualified NOT LIKE '%::%'"
    Expected Result: Bare count is lower than before wiring (baseline taken before)
    Evidence: .sisyphus/evidence/task-0.2-bare-calls-reduction.txt
  ```

  **Commit**: YES (groups with 0.4)
  - Message: `fix(pipeline): wire resolve_bare_call_targets into build pipeline`
  - Files: `code_review_graph/incremental.py`
  - Pre-commit: `pytest tests/`

- [x] 0.3. **Wire `enrich_jedi_calls()` no pipeline de build (opcional)**

  **What to do**:
  - Em `code_review_graph/incremental.py`:
    - Na função `full_build()`: após `resolve_bare_call_targets()`, chamar `enrich_jedi_calls(store, repo_root)` se `jedi` estiver disponível (import opcional)
    - Seguir o padrão de erro do `_run_rescript_resolver`: try/except silencioso
    - Adicionar config para pular enrichment: `CRG_SKIP_ENRICHMENT=1` ou verificar se o módulo enrichment está instalado
  - Em `code_review_graph/incremental.py`: importar `enrich_jedi_calls` com fallback (opcional)

  **Must NOT do**:
  - ❌ Não tornar Jedi obrigatório
  - ❌ Não chamar em `incremental_update` por enquanto (pode ser caro)
  - ❌ Não mudar a lógica de `enrich_jedi_calls`

  **Recommended Agent Profile**:
  - **Category**: `quick` — seguir padrão estabelecido
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1
  - **Parallel Group**: Wave 1
  - **Blocks**: 0.4, 4.2
  - **Blocked By**: None

  **References**:
  - `code_review_graph/jedi_resolver.py:27-198` — `enrich_jedi_calls()` (código morto)
  - `code_review_graph/incremental.py:28-37` — padrão `_run_rescript_resolver`
  - `code_review_graph/incremental.py:full_build()` — ~linha 800
  - `code_review_graph/pyproject.toml:77` — Jedi como dependência opcional (`enrichment` extra)

  **Acceptance Criteria**:
  - [ ] `enrich_jedi_calls()` é chamada durante `full_build` quando Jedi instalado
  - [ ] Build não falha quando Jedi NÃO está instalado
  - [ ] Log mostra `"Jedi enrichment: resolved N calls"` após build com Jedi
  - [ ] `CRG_SKIP_ENRICHMENT=1` pula enrichment
  - [ ] `pytest tests/` passa

  **QA Scenarios**:
  ```
  Scenario: Jedi enrichment runs when Jedi is available
    Tool: Bash
    Preconditions: code-review-graph[enrichment] installed, Python project with svc.method() pattern
    Steps:
      1. Build graph: python -m code_review_graph.cli build
      2. Check log for "Jedi enrichment: resolved"
    Expected Result: Jedi enrichment ran and resolved calls
    Evidence: .sisyphus/evidence/task-0.3-jedi-enrichment.txt

  Scenario: Build succeeds without Jedi
    Tool: Bash
    Preconditions: Without jedi package installed
    Steps:
      1. Build graph: python -m code_review_graph.cli build
    Expected Result: Build completes without error (Jedi silently skipped)
    Evidence: .sisyphus/evidence/task-0.3-jedi-skip.txt
  ```

  **Commit**: YES (groups with 0.4)
  - Message: `feat(pipeline): wire enrich_jedi_calls into full build pipeline`
  - Files: `code_review_graph/incremental.py`
  - Pre-commit: `pytest tests/`

- [x] 0.4. **Tests + Baseline Metric para bare CALLS**

  **What to do**:
  - Criar teste para `resolve_bare_call_targets()`:
    - Fixture com 2 arquivos Python: um define função, outro importa e chama
    - Verificar se CALLS edge é resolvido para qualified name após `resolve_bare_call_targets()`
  - Criar teste para `enrich_jedi_calls()`:
    - Fixture com padrão `svc.authenticate()` onde `svc = SomeFactory()`
    - Verificar se Jedi enrichment adiciona CALLS edge qualificado
  - Estabelecer baseline metric: query SQL que conta bare CALLS ratio
    - Adicionar como `test_bare_calls_baseline` que registra o count
    - Pode usar fixture com `code-review-graph build` em repo de teste

  **Must NOT do**:
  - ❌ Não pular se Jedi não estiver instalado (teste com skip condicional)
  - ❌ Não adicionar fixtures de terceiros (usar só arquivos no diretório tests/fixtures/)

  **Recommended Agent Profile**:
  - **Category**: `quick` — testes bem definidos
  - **Skills**: N/A

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1 (após 0.2 e 0.3)
  - **Parallel Group**: Wave 1 (after 0.2, 0.3)
  - **Blocks**: N/A
  - **Blocked By**: 0.2, 0.3

  **References**:
  - `tests/test_parser.py` — padrão de teste de parser
  - `tests/fixtures/caller_example.py` — fixture de chamada cross-file
  - `tests/fixtures/multi_call_example.py` — fixture de múltiplas chamadas
  - `tests/fixtures/sample_python.py` — fixture Python principal
  - `code_review_graph/graph.py:466-542` — `resolve_bare_call_targets`

  **Acceptance Criteria**:
  - [ ] Teste `test_resolve_bare_call_targets` criado em `tests/test_enrich.py`
  - [ ] Teste `test_enrich_jedi_calls` criado em `tests/test_enrich.py`
  - [ ] Ambos passam: `pytest tests/test_enrich.py -v`
  - [ ] Baseline metric documentada: ratio bare/total CALLS

  **QA Scenarios**:
  ```
  Scenario: resolve_bare_call_targets test passes
    Tool: Bash
    Preconditions: Test fixtures in place
    Steps:
      1. Run: pytest tests/test_enrich.py::test_resolve_bare_call_targets -v
    Expected Result: "PASSED" — cross-file CALLS resolved correctly
    Evidence: .sisyphus/evidence/task-0.4-bare-calls-test.txt

  Scenario: Full test suite passes
    Tool: Bash
    Preconditions: All changes from 0.1-0.3
    Steps:
      1. Run: pytest tests/ -v
    Expected Result: All tests pass (any failures are pre-existing)
    Evidence: .sisyphus/evidence/task-0.4-full-suite.txt
  ```

  **Commit**: YES (groups with 0.2, 0.3)
  - Message: `test(pipeline): add tests for resolve_bare_call_targets and Jedi enrichment`
  - Files: `tests/test_enrich.py`, `tests/fixtures/` (new fixtures)
  - Pre-commit: `pytest tests/`

---


