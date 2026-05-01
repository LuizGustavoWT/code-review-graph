# Draft: PHP Graph + Loop Hang Analysis

## Diagnóstico Completo

### 1. Causa Raiz do Loop Infinito

O stack trace mostra:
```
build.py:44 → _run_postprocess → _derive_edges
                                     ↓
                         store.get_class_uses(qn)  → SQL lento
                         store.get_module_dependencies(fp)  → SQL lento
```

O `_derive_edges` percorre **TODAS as classes** e **TODOS os arquivos** do projeto:
- Para cada classe: busca CONTAINS → CALLS → resolve container
- Para cada arquivo: busca IMPORTS_FROM + CALLS cross-file

Em projetos grandes com PHP (centenas/milhares de classes), isso pode ser **extremamente lento** ou **travar** se houver referências circulares ou banco corrompido.

**Solução imediata**: `CRG_DERIVED_EDGES=0` desabilita esse passo.

### 2. Versão do Código

O stack trace do usuário mostra `build.py:44 → _derive_edges` (versão antiga). Nossa PR removeu `_derive_edges` mas o merge parece não ter atualizado corretamente — ou o usuário está rodando um binário instalado via `pip install -e .` que não foi reinstalado.

### 3. PHP Functions

O `_get_name()` em `parser.py` **já tem suporte** para PHP via generic loop (linha 4364-4369 `"name"` child type). Mas o build nunca completa por causa do `_derive_edges`, então nenhum nó é salvo.

## Ações Necessárias

1. Matar banco corrompido + rebuild
2. Desabilitar `CRG_DERIVED_EDGES=0`
3. Reinstalar pacote após merge
4. Verificar PHP parsing
