#!/usr/bin/env bash
# Release fiscalkit: verify, build, and publish.
#
# Run from the fiscalkit directory on a machine with network access. This
# sandbox cannot reach upload.pypi.org, so the upload step is the one thing that
# has to happen on your side.
#
#   ./release.sh check     run every gate, build nothing
#   ./release.sh build     run every gate, then build wheel + sdist
#   ./release.sh testpypi  build, then upload to TestPyPI (a rehearsal)
#   ./release.sh publish   build, then upload to PyPI (the real thing)
#
# Credentials are read by twine from ~/.pypirc or the TWINE_* environment
# variables. This script never reads, prints, or stores a token.

set -euo pipefail

MODE="${1:-check}"
BASE_PY="${PYTHON:-python3}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
die()  { printf '\033[31mfailed: %s\033[0m\n' "$1" >&2; exit 1; }

[ -f pyproject.toml ] || die "run this from the fiscalkit directory"

# Never install into the system interpreter. On Debian and Ubuntu, pip refuses to
# touch distro-managed packages ("Cannot uninstall X, RECORD file not found"),
# which fails the release for a reason that has nothing to do with this project.
# If the caller has already activated a virtualenv, respect it; otherwise make one.
if [ -n "${VIRTUAL_ENV:-}" ]; then
  PY="$BASE_PY"
  step "Using the active virtualenv at $VIRTUAL_ENV"
else
  VENV="${VENV:-.venv-release}"
  step "Preparing an isolated virtualenv at $VENV"
  [ -d "$VENV" ] || "$BASE_PY" -m venv "$VENV" || die "could not create $VENV"
  PY="$VENV/bin/python"
fi

step "Installing dev and mcp extras"
$PY -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
$PY -m pip install --quiet -e '.[dev,mcp]' build twine || die "install"

step "Tests"
$PY -m pytest || die "tests"

step "Lint"
$PY -m ruff check src tests || die "ruff check"

step "Format"
$PY -m ruff format --check src tests || die "ruff format"

step "Types (strict)"
$PY -m mypy src/fiscalkit || die "mypy"

# The optional extra must not be load-bearing: the library has to import and the
# CLI has to work with only the core dependencies present.
step "Import and CLI smoke test"
$PY -c 'from fiscalkit import *; import fiscalkit; assert len(fiscalkit.__all__) > 30' || die "star import"
$PY -m fiscalkit.cli chave 43240311222333000181550010000001231000000010 >/dev/null || die "cli chave"
$PY -m fiscalkit.cli cnpj 12ABC34501DE35 >/dev/null || die "cli cnpj alfanumerico"

[ "$MODE" = "check" ] && { printf '\n\033[32mAll gates green.\033[0m\n'; exit 0; }

step "Building wheel and sdist"
rm -rf dist build ./*.egg-info
$PY -m build || die "build"
$PY -m twine check dist/* || die "twine check"
ls -lh dist/

case "$MODE" in
  build)    printf '\n\033[32mBuilt. Nothing uploaded.\033[0m\n' ;;
  testpypi) step "Uploading to TestPyPI"
            $PY -m twine upload --repository testpypi dist/* || die "testpypi upload"
            printf '\n\033[32mOn TestPyPI. Verify with:\033[0m\n'
            printf '  pip install -i https://test.pypi.org/simple/ fiscalkit\n' ;;
  publish)  step "Uploading to PyPI"
            printf 'This publishes permanently. A version number can never be reused.\n'
            read -r -p 'Type the version to confirm (0.1.0): ' confirm
            [ "$confirm" = "0.1.0" ] || die "confirmation did not match"
            $PY -m twine upload dist/* || die "pypi upload"
            printf '\n\033[32mLive: https://pypi.org/project/fiscalkit/\033[0m\n'
            printf 'Now tag it:  git tag v0.1.0 && git push --tags\n' ;;
  *)        die "unknown mode '$MODE' (check|build|testpypi|publish)" ;;
esac
