# learnings.md

## Task: Update docs/TROUBLESHOOTING.md with "Large Projects / Slow Builds" section

- Existing TROUBLESHOOTING.md had a minimal 3-line "Large repositories" section (lines 129-138) that was overly optimistic ("30-60 seconds" for 10k files).
- Replaced that section with a comprehensive ~170-line section covering 6 optimization strategies.
- Referenced two existing files:
  - `scripts/crg-fast.sh` (129 lines, wraps all optimizations with color output and timed execution)
  - `.code-review-graphignore.example` (161 lines, language/framework-organized ignore patterns)
- Added a quick reference table mapping build modes to typical times, community detection, derived edges, and flow analysis.
- Included a pro tip about two-phase build: minimal first, then full in background.
- All existing content below the replaced section (Missing nodes, Graph stale, Embeddings, MCP, Windows/WSL, Community detection, Wiki, Optional deps) remained untouched.
- File grew from 187 to 345 lines.
