#!/usr/bin/env bash
# =============================================================================
# Scout — Lambda build script
# =============================================================================
# Produces deployment zips whose internal paths match the Terraform handlers:
#
#   crawlers.zip      → handler: crawlers.<module>.handler
#   enrichment.zip    → handler: enrichment.handler.handler
#   api.zip           → handler: api.<module>.handler
#   reports.zip       → handler: reports.<module>.handler
#
# Each zip contains its own package dir + the shared/ package.
# The dependency layer is built separately and published via CI/CD.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDAS_DIR="$SCRIPT_DIR/lambdas"
BUILD_DIR="$SCRIPT_DIR/build"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${YELLOW}→${NC} $*"; }

echo ""
echo "Scout Lambda Build"
echo "══════════════════"

# ── Clean ─────────────────────────────────────────────────────────────────────
info "Cleaning previous build..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# ── Verify Python source syntax ───────────────────────────────────────────────
info "Checking Python syntax..."
python3 - <<'PYCHECK'
import pathlib, ast, sys
errors = []
for f in pathlib.Path(".").rglob("lambdas/**/*.py"):
    try:
        ast.parse(f.read_text())
    except SyntaxError as e:
        errors.append(f"{f}: {e}")
if errors:
    print("\n".join(errors))
    sys.exit(1)
PYCHECK
ok "All Python files pass syntax check"

# ── Helper: build one zip ─────────────────────────────────────────────────────
# Usage: build_zip <group>
# Creates $BUILD_DIR/<group>.zip containing lambdas/<group>/ + lambdas/shared/
# Paths inside the zip are relative (no leading lambdas/), so handlers resolve as:
#   <group>.<module>.handler  →  <group>/<module>.py::handler
build_zip() {
  local group="$1"
  local zip_path="$BUILD_DIR/${group}.zip"

  info "Building ${group}.zip..."

  # cd into lambdas/ so the zip root starts at group/ and shared/
  (
    cd "$LAMBDAS_DIR"
    zip -r "$zip_path" \
      "${group}/" \
      shared/ \
      -x "*/__pycache__/*" \
      -x "*/*.pyc" \
      -x "*/.DS_Store" \
      > /dev/null
  )

  local size
  size=$(du -sh "$zip_path" | cut -f1)
  ok "${group}.zip  (${size})"
}

# ── Build each Lambda group ────────────────────────────────────────────────────
build_zip crawlers
build_zip enrichment
build_zip api
build_zip reports
build_zip scoring

# ── Dependency layer ──────────────────────────────────────────────────────────
info "Building dependency layer..."
LAYER_PYTHON="$BUILD_DIR/layer/python"
mkdir -p "$LAYER_PYTHON"

# Install without --quiet so failures are immediately visible
pip install \
  -r "$SCRIPT_DIR/requirements.txt" \
  -t "$LAYER_PYTHON" \
  --no-cache-dir

# Strip test dirs, __pycache__, and dist-info metadata to keep the zip lean
find "$LAYER_PYTHON" -type d -name "tests"       -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_PYTHON" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$LAYER_PYTHON" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

# Verify critical packages are importable before zipping (fail loudly if missing)
python3 - "$LAYER_PYTHON" <<'PYVERIFY'
import sys
sys.path.insert(0, sys.argv[1])
packages = {"jobspy": "jobspy", "pdfminer": "pdfminer"}
failed = []
for label, mod in packages.items():
    try:
        __import__(mod)
        print(f"✓ {label} importable from {sys.argv[1]}")
    except ImportError as e:
        print(f"✗ {label} import failed: {e}", file=sys.stderr)
        failed.append(label)
if failed:
    sys.exit(1)
PYVERIFY

(
  cd "$BUILD_DIR/layer"
  zip -r "$BUILD_DIR/dependencies-layer.zip" python/ \
    -x "*/__pycache__/*" \
    -x "*/*.pyc" \
    > /dev/null
)
LAYER_SIZE=$(du -sh "$BUILD_DIR/dependencies-layer.zip" | cut -f1)
ok "dependencies-layer.zip  (${LAYER_SIZE})"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Build artifacts in $BUILD_DIR/"
ls -lh "$BUILD_DIR/"*.zip

echo ""
echo "Handler reference:"
echo "  crawlers.zip"
echo "    crawlers.linkedin.handler       → crawlers/linkedin.py::handler"
echo "    crawlers.indeed.handler         → crawlers/indeed.py::handler"
echo "    crawlers.glassdoor.handler      → crawlers/glassdoor.py::handler"
echo "    crawlers.ziprecruiter.handler   → crawlers/ziprecruiter.py::handler"
echo "    crawlers.dice.handler           → crawlers/dice.py::handler"
echo "    crawlers.diagnose.handler       → crawlers/diagnose.py::handler"
echo "    crawlers.purge.handler          → crawlers/purge.py::handler"
echo ""
echo "  enrichment.zip"
echo "    enrichment.handler.handler      → enrichment/handler.py::handler"
echo ""
echo "  api.zip"
echo "    api.get_jobs.handler            → api/get_jobs.py::handler"
echo "    api.update_status.handler       → api/update_status.py::handler"
echo "    api.user_settings.handler       → api/user_settings.py::handler"
echo ""
echo "  reports.zip"
echo "    reports.daily_report.handler    → reports/daily_report.py::handler"
echo "    reports.weekly_report.handler   → reports/weekly_report.py::handler"
echo ""
echo "  scoring.zip"
echo "    scoring.resume_parser.handler   → scoring/resume_parser.py::handler"
echo ""
