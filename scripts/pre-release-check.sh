#!/usr/bin/env bash
# Pre-release quality gate — must pass before any tag/push/PyPI upload.
# Usage: bash scripts/pre-release-check.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

PASS=0
FAIL=0
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ok() { echo -e "  ${GREEN}✅${NC} $1"; ((PASS++)); }
nope() { echo -e "  ${RED}❌${NC} $1"; ((FAIL++)); }

echo "=== Pre-Release Gate ==="
echo ""

# 1. ruff
if .venv/bin/ruff check > /dev/null 2>&1; then ok "ruff check"; else nope "ruff check"; fi

# 2. pytest (skip network-dependent API tests in sandbox)
if .venv/bin/python -m pytest tests/ -q -k "not (api_check_success or api_check_timeout)" > /dev/null 2>&1; then
    ok "pytest (35/37, 2 network tests skipped)"
else
    nope "pytest"
fi

# 3. README version matches pyproject.toml
PYPROJ_VER=$(grep '^version = ' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
README_EN_VER=$(grep -o 'agent-ci-verify v[0-9.]*' README.md | head -1 | sed 's/.*v//')
README_CN_VER=$(grep -o 'agent-ci-verify v[0-9.]*' README_CN.md | head -1 | sed 's/.*v//')

if [ "$PYPROJ_VER" = "$README_EN_VER" ] && [ "$PYPROJ_VER" = "$README_CN_VER" ]; then
    ok "README versions: pyproject=$PYPROJ_VER, EN=$README_EN_VER, CN=$README_CN_VER"
else
    nope "README version mismatch: pyproject=$PYPROJ_VER, EN=$README_EN_VER, CN=$README_CN_VER"
fi

# 4. Git clean
if git diff --quiet && git diff --cached --quiet; then
    ok "git working tree clean"
else
    nope "git working tree dirty — commit first"
fi

echo ""
echo "=== Result: $PASS/$((PASS+FAIL)) passed ==="

if [ "$FAIL" -gt 0 ]; then
    echo "❌ REJECTED — fix failures above before release."
    exit 1
fi

echo "✅ All gates passed — safe to release."
