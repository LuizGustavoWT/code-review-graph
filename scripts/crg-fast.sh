#!/bin/bash
# crg-fast.sh - Optimized code-review-graph builder for large projects
#
# Reduces build time for projects with many files by offering targeted build
# modes. Derived edges are enabled by default (optimized with bulk SQL queries).
#
# Usage:
#   ./crg-fast.sh            # Incremental update (default, fastest)
#   ./crg-fast.sh --minimal  # Minimal postprocessing
#   ./crg-fast.sh --full     # Full rebuild with full postprocessing
#   ./crg-fast.sh --help     # Show this help text

set -euo pipefail

# --- Derived edges enabled (optimized with bulk SQL queries) ---
export CRG_DERIVED_EDGES=1

# ------------------------------------------------------------------
# Color support (respects NO_COLOR standard)
# ------------------------------------------------------------------
if [[ -n "${NO_COLOR:-}" ]]; then
  GREEN=""
  YELLOW=""
  RED=""
  CYAN=""
  BOLD=""
  RESET=""
else
  GREEN="\033[0;32m"
  YELLOW="\033[0;33m"
  RED="\033[0;31m"
  CYAN="\033[0;36m"
  BOLD="\033[1m"
  RESET="\033[0m"
fi

# ------------------------------------------------------------------
# Help text
# ------------------------------------------------------------------
show_help() {
  echo -e "${BOLD}crg-fast.sh${RESET} - Optimized code-review-graph builder for large projects"
  echo ""
  echo "Usage:"
  echo "  $(basename "$0")            ${CYAN}Incremental update (default, fastest)${RESET}"
  echo "  $(basename "$0") --minimal  ${CYAN}Build with minimal postprocessing${RESET}"
  echo "  $(basename "$0") --full     ${CYAN}Full rebuild with full postprocessing${RESET}"
  echo "  $(basename "$0") --help     ${CYAN}Show this help text${RESET}"
  echo ""
  echo "Environment:"
  echo "  NO_COLOR=1   Disable colored output"
  echo "  CRG_DERIVED_EDGES  Derived edges enabled by default for full blast-radius analysis"
  echo ""
  echo "Notes:"
  echo "  - igraph is recommended for full mode. If missing, --full will"
  echo "    still work but some community-detection features may be unavailable."
}

# ------------------------------------------------------------------
# Check for igraph availability (needed for community detection in full mode)
# ------------------------------------------------------------------
check_igraph() {
  if python -c "import igraph" 2>/dev/null; then
    return 0
  else
    echo -e "${YELLOW}[warn] igraph Python package not found.${RESET}"
    echo -e "${YELLOW}       Some community-detection features in --full mode may be unavailable.${RESET}"
    echo -e "${YELLOW}       Install with: pip install igraph${RESET}"
    return 1
  fi
}

# ------------------------------------------------------------------
# Timed execution helper
# ------------------------------------------------------------------ 
run_timed() {
  local label="$1"
  shift
  local start
  start=$(date +%s)

  echo -e "${CYAN}[crg-fast]${RESET} ${label}..."
  
  if "$@"; then
    local end
    end=$(date +%s)
    local elapsed=$((end - start))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))
    echo -e "${GREEN}[done]${RESET} ${label} completed in ${minutes}m${seconds}s"
  else
    local end
    end=$(date +%s)
    local elapsed=$((end - start))
    echo -e "${RED}[fail]${RESET} ${label} failed after ${elapsed}s"
    return 1
  fi
}

# ------------------------------------------------------------------
# Main dispatch
# ------------------------------------------------------------------
main() {
  local mode="${1:-update}"

  case "${mode}" in
    --help|-h)
      show_help
      exit 0
      ;;
    --full)
      check_igraph || true  # warn-only, don't block
      run_timed "Full rebuild" code-review-graph build --full-rebuild --postprocess full
      ;;
    --minimal)
      run_timed "Build with minimal postprocessing" code-review-graph build --postprocess minimal
      ;;
    --update|"")
      run_timed "Incremental update" code-review-graph update
      ;;
    *)
      echo -e "${RED}[error]${RESET} Unknown option: ${mode}"
      echo ""
      show_help
      exit 1
      ;;
  esac
}

main "$@"
