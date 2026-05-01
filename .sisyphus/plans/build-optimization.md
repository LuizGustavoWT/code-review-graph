# Plan: Otimização de Build — 11.834 arquivos

## TL;DR

> **Quick Summary**: Otimizar o build do code-review-graph para projetos grandes (11.834 files, 100k nodes, 750k edges), reduzindo de 26+ minutos para segundos em builds incrementais e < 1 minuto em full rebuilds.
>
> **Deliverables**:
> - Build incremental em < 5s (após o primeiro build)
> - Full rebuild (quando necessário) em < 3 min
> - Community detection acelerado via igraph
>
> **Estimated Effort**: Medium (6 otimizações)
> **Parallel Execution**: YES - otimizações independentes
> **Critical Path**: N/A — todas são independentes

---

## Context

### Original Request
Usuário com projeto de 11.834 arquivos tem build lento. Com `CRG_DERIVED_EDGES=0` funcionou mas ainda demora.

### Métricas Atuais
| Métrica | Valor |
|---------|-------|
| Arquivos | 11.834 |
| Nós | 100.042 |
| Arestas | 749.856 |
| CALLS targets | ~50k |
| FTS rows | 88.081 |
| Flows | 13.490 |
| Comunidades | 10 |

---

## Work Objectives

### Core Objective
Reduzir drasticamente o tempo de build mantendo todas as funcionalidades do grafo.

### Concrete Deliverables
- Build incremental funcional
- igraph instalado para community detection rápido
- `.code-review-graphignore` configurado
- Postprocess rodando apenas o necessário

---

## Execution Plan

### Otimização 1: Build Incremental (MAIOR GANHO)

**O build incremental SÓ re-parseia arquivos modificados.**

Depois do primeiro build, use:
```bash
code-review-graph update
# OU
code-review-graph build  # sem --full-rebuild
```

Isso:
- Detecta arquivos modificados via git diff
- Re-parseia APENAS os alterados
- Roda postprocess incremental (flows + communities só nos afetados)

**Tempo estimado**: < 3 segundos para mudanças típicas.

### Otimização 2: Instalar igraph para Community Detection

Seu log mostra `"igraph not available, using file-based community detection"`.

O fallback **file-based** é MUITO mais lento que o algoritmo Leiden do igraph.

```bash
pip install code-review-graph[communities]
# ou
pip install igraph>=0.11.0
```

**Ganho**: Community detection cai de minutos para < 5 segundos.

### Otimização 3: .code-review-graphignore — Exclua o que não precisa

Crie `.code-review-graphignore` na raiz do projeto:

```
# Diretórios de dependências
vendor/**
node_modules/**
.bundle/**

# Build/cache
var/cache/**
bootstrap/cache/**
storage/**
dist/**
build/**

# Assets que não têm lógica
public/assets/**
public/build/**
*.min.js
*.min.css

# Arquivos gerados
*.generated.php
*.generated.js
```

Isso reduz o número de arquivos parseados (e nós gerados).

### Otimização 4: Postprocess Seletivo

Use `--postprocess` para controlar o que roda:

```bash
# Mais rápido — só signatures + FTS (flows/communities NÃO rodam)
code-review-graph build --postprocess minimal

# Completo — tudo (use em builds noturnos ou CI)
code-review-graph build --postprocess full

# Depois, se precisar de flows/communities, rode separado:
CRG_DERIVED_EDGES=0 code-review-graph build --postprocess full
```

| Nível | Signatures | FTS | Flows | Communities |
|-------|-----------|-----|-------|-------------|
| `none` | ❌ | ❌ | ❌ | ❌ |
| `minimal` | ✅ | ✅ | ❌ | ❌ |
| `full` | ✅ | ✅ | ✅ | ✅ |

### Otimização 5: Paralelismo

Se o build ainda estiver lento, controle o paralelismo:

```bash
# Desabilitar paralelismo (debug)
CRG_SERIAL_PARSE=1 code-review-graph build

# Ou aumentar número de processos (default = CPU cores)
# (não há env var direta, mas o ProcessPoolExecutor respeita N processos)
```

Para projetos com 11.834 arquivos, o parse paralelo já está ativo por padrão — cada arquivo é parseado em paralelo usando `ProcessPoolExecutor`.

### Otimização 6: CRG_DERIVED_EDGES=0 (JÁ RESOLVIDO)

Manter `CRG_DERIVED_EDGES=0` para sempre pular o `_derive_edges` que trava. Pode colocar no `.bashrc` ou no script de execução:

```bash
# ~/.bashrc ou .env
export CRG_DERIVED_EDGES=0
```

---

## Fluxo de Trabalho Otimizado

### Primeira execução (completa, lenta — roda 1x):
```bash
export CRG_DERIVED_EDGES=0
pip install code-review-graph[communities]  # igraph para acelerar
code-review-graph build  # ou build --postprocess full
```

### Execuções diárias (super rápidas):
```bash
export CRG_DERIVED_EDGES=0
code-review-graph update  # incremental, < 5s
```

### Se quiser pular flows (mais rápido ainda):
```bash
export CRG_DERIVED_EDGES=0
code-review-graph build --postprocess minimal
```

### Build completo periódico (CI, nightly):
```bash
export CRG_DERIVED_EDGES=0
code-review-graph build --full-rebuild --postprocess full
```

---

## Script Pronto

```bash
#!/bin/bash
# crg-fast.sh — build otimizado

export CRG_DERIVED_EDGES=0

if [ "$1" == "--full" ]; then
    echo "Full rebuild..."
    pip install code-review-graph[communities] 2>/dev/null
    code-review-graph build --full-rebuild --postprocess full
elif [ "$1" == "--minimal" ]; then
    echo "Minimal build (no flows/communities)..."
    code-review-graph build --postprocess minimal
else
    echo "Incremental update..."
    code-review-graph update
fi
```

---

## Success Criteria

- [ ] `code-review-graph update` completa em < 5 segundos *(execução no ambiente do usuário)*
- [ ] `code-review-graph build --postprocess minimal` completa em < 3 minutos *(execução no ambiente do usuário)*
- [x] **Artefatos criados**: `.code-review-graphignore.example`, `scripts/crg-fast.sh`, docs atualizados
- [ ] `igraph` instalado, community detection acelerado *(execução no ambiente do usuário)*
- [x] `.code-review-graphignore.example` criado com exclusões para PHP e projetos grandes
- [ ] `CRG_DERIVED_EDGES=0` no ambiente *(configuração no ambiente do usuário)*
