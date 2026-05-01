# Draft: Otimização de Build

## Métricas Atuais
- 11.834 arquivos
- 100.042 nós
- 749.856 arestas
- Build full: ~26+ minutos (ou mais)

## Diagnóstico de Gargalos

1. **Parse paralelo** — já usa `ProcessPoolExecutor` (paralelo por padrão)
2. **FTS rebuild** — 88k linhas indexadas, rápido
3. **Flow detection** — 13.490 flows, pesado em grafo grande
4. **Community detection** — sem igraph, usa fallback baseado em arquivo (mais lento)
5. **_derive_edges** — já desabilitado com `CRG_DERIVED_EDGES=0`
