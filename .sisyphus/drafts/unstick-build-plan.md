# Draft: Build Travado — 11.834 arquivos

## Diagnóstico

Seu projeto tem **11.834 arquivos**, o que gera ~88k linhas no FTS.

Após o FTS rebuild (que completou), o pipeline roda:
1. ✅ Signatures
2. ✅ FTS rebuild (88081 rows)
3. ❌ Flow detection — **travado** (~26 min)
4. ❌ Community detection
5. ❌ Summary computation

Com 49.675 CALLS targets, `trace_flows()` percorre o grafo inteiro e pode ser extremamente lento ou travar.

## Solução

Usar `--postprocess minimal` para pular flows, communities e summaries.

```bash
CRG_DERIVED_EDGES=0 code-review-graph build --postprocess minimal
```

Isso ainda gera signatures + FTS (o necessário para buscas), mas pula as etapas pesadas.

## Se precisar de flows/communities depois

Rodar separadamente:
```bash
code-review-graph serve  # MCP server com suporte a tools
```
E usar o MCP tool `run_postprocess_tool` com parâmetros seletivos.
