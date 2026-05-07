#!/usr/bin/env bash
# Release script — CANNOT be done out of order.
# Usage: bash scripts/release.sh X.Y.Z
# Example: bash scripts/release.sh 1.0.4
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

NEW_VERSION="${1:-}"
if [ -z "$NEW_VERSION" ]; then
    echo "Usage: bash scripts/release.sh X.Y.Z"
    exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "=== Releasing v${NEW_VERSION} ==="
echo ""

# ── Step 1: Update all version references BEFORE anything else ──────
echo "[1/6] Updating version references..."

# pyproject.toml
sed -i '' "s/^version = \"[^\"]*\"/version = \"${NEW_VERSION}\"/" pyproject.toml
echo "  pyproject.toml → ${NEW_VERSION}"

# README.md
sed -i '' "s/agent-ci-verify v[0-9.]*/agent-ci-verify v${NEW_VERSION}/" README.md
echo "  README.md → ${NEW_VERSION}"

# README_CN.md
sed -i '' "s/agent-ci-verify v[0-9.]*/agent-ci-verify v${NEW_VERSION}/" README_CN.md
echo "  README_CN.md → ${NEW_VERSION}"

echo ""

# ── Step 2: Run pre-release gate ────────────────────────────────────
echo "[2/6] Pre-release gate..."

# README version check (sanity — sed should have done it)
PYPROJ_VER=$(grep '^version = ' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
README_EN_VER=$(grep -o 'agent-ci-verify v[0-9.]*' README.md | head -1 | sed 's/.*v//')
README_CN_VER=$(grep -o 'agent-ci-verify v[0-9.]*' README_CN.md | head -1 | sed 's/.*v//')

if [ "$PYPROJ_VER" != "$NEW_VERSION" ] || [ "$README_EN_VER" != "$NEW_VERSION" ] || [ "$README_CN_VER" != "$NEW_VERSION" ]; then
    echo -e "  ${RED}❌ Version sync failed: pyproject=${PYPROJ_VER} EN=${README_EN_VER} CN=${README_CN_VER}${NC}"
    exit 1
fi
echo "  ✅ Version sync: $NEW_VERSION"

if ! .venv/bin/ruff check > /dev/null 2>&1; then
    echo -e "  ${RED}❌ ruff check failed${NC}"
    exit 1
fi
echo "  ✅ ruff check"

if ! .venv/bin/python -m pytest tests/ -q -k "not (api_check_success or api_check_timeout)" > /dev/null 2>&1; then
    echo -e "  ${RED}❌ pytest failed${NC}"
    exit 1
fi
echo "  ✅ pytest"

echo ""

# ── Step 3: Build ───────────────────────────────────────────────────
echo "[3/6] Building..."
rm -rf dist/
.venv/bin/python -m build --no-isolation -q
echo "  ✅ dist/agent_ci_verify-${NEW_VERSION}.tar.gz"
echo ""

# ── Step 4: Upload to PyPI ─────────────────────────────────────────
echo "[4/6] Uploading to PyPI..."
.venv/bin/twine upload --non-interactive "dist/agent_ci_verify-${NEW_VERSION}"*
echo -e "  ${GREEN}✅ https://pypi.org/project/agent-ci-verify/${NEW_VERSION}/${NC}"
echo ""

# ── Step 5: Commit + Tag ───────────────────────────────────────────
echo "[5/6] Committing + tagging..."
git add pyproject.toml README.md README_CN.md
git commit -m "release: v${NEW_VERSION}" > /dev/null 2>&1
git tag -a "v${NEW_VERSION}" -m "v${NEW_VERSION}"
echo "  ✅ commit + tag v${NEW_VERSION}"
echo ""

# ── Step 6: Push to GitHub ─────────────────────────────────────────
echo "[6/6] Pushing to GitHub..."
git push origin main --tags
echo -e "  ${GREEN}✅ GitHub synced${NC}"
echo ""

echo -e "${GREEN}=== v${NEW_VERSION} released — PyPI + GitHub ===${NC}"
