#!/usr/bin/env bash
# TaskPlanner release workflow: bump semver in tp/__init__.py, build frontend to static/,
# refresh version.txt, overwrite summary.txt, commit (body = summary), tag, push, GitHub release,
# and optionally build compiled binaries with Nuitka.
#
# Usage:
#   ./scripts/publish-release.sh [--patch|--minor|--major] [--dry-run] [--no-gh] [--build] \
#     [-m "release notes"] [--summary-file PATH]
#
# Omitting both -m and --summary-file uses summary: new version release
# summary.txt is overwritten (current release only). With -m or --summary-file, body is trimmed;
# if empty / whitespace-only after trim, it defaults to the single line: new version release
#
# Options:
#   --patch, --minor, --major   Bump version (default: patch)
#   --dry-run                   Show what would be done without making changes
#   --no-gh                     Skip GitHub release (create tag/push only)
#   --build                     Build compiled binaries with Nuitka locally (not recommended)
#   -m "message"                Custom release notes
#   --summary-file PATH         File containing release notes
#
# Requires: git, npm, gh (unless --no-gh or --dry-run). Does not run pytest — run tests first if needed.
# With --build: requires Python 3.11, C compiler, and Nuitka.
set -euo pipefail

PRODUCT="TaskPlanner"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  sed -n '1,26p' "$0" | tail -n +2
  exit 1
}

BUMP_KIND="patch"
DRY_RUN=0
NO_GH=0
BUILD=0
SUMMARY_MSG=""
SUMMARY_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m)
      if [[ $# -ge 2 ]]; then
        SUMMARY_MSG="${2}"
        shift 2
      else
        SUMMARY_MSG=""
        shift
      fi
      ;;
    --summary-file)
      SUMMARY_FILE="${2:-}"
      if [[ -z "$SUMMARY_FILE" ]]; then echo "ERROR: --summary-file requires a path." >&2; exit 1; fi
      if [[ ! -f "$SUMMARY_FILE" ]]; then echo "ERROR: not a file: $SUMMARY_FILE" >&2; exit 1; fi
      shift 2
      ;;
    --patch) BUMP_KIND="patch"; shift ;;
    --minor) BUMP_KIND="minor"; shift ;;
    --major) BUMP_KIND="major"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-gh) NO_GH=1; shift ;;
    --build) BUILD=1; shift ;;
    -h|--help) usage ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage
      ;;
  esac
done

if [[ "$DRY_RUN" -eq 0 ]]; then
  if [[ -n "$SUMMARY_MSG" && -n "$SUMMARY_FILE" ]]; then
    echo "ERROR: use only one of -m or --summary-file." >&2
    exit 1
  fi
fi

command -v git >/dev/null || { echo "ERROR: git not on PATH." >&2; exit 1; }
command -v npm >/dev/null || { echo "ERROR: npm not on PATH." >&2; exit 1; }
if [[ "$NO_GH" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
  command -v gh >/dev/null || { echo "ERROR: gh not on PATH (use --no-gh to skip GitHub release)." >&2; exit 1; }
fi

NEW_VER="$(
  cd "$ROOT"
  python3 - "$BUMP_KIND" "$DRY_RUN" <<'PY'
import pathlib, re, sys

kind, dry_arg = sys.argv[1], sys.argv[2]
dry = dry_arg == "1"
path = pathlib.Path("tp/__init__.py")
text = path.read_text(encoding="utf-8")
m = re.search(r'(__version__\s*=\s*")(\d+)\.(\d+)\.(\d+)(")', text)
if not m:
    sys.stderr.write("Could not parse __version__ in tp/__init__.py\n")
    sys.exit(1)
prefix, maj, min_, pat, suffix = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
current_v = f"{maj}.{min_}.{pat}"
if kind == "patch":
    pat += 1
elif kind == "minor":
    min_ += 1
    pat = 0
elif kind == "major":
    maj += 1
    min_ = pat = 0
else:
    sys.stderr.write(f"Unknown bump kind: {kind}\n")
    sys.exit(1)
new_v = f"{maj}.{min_}.{pat}"
new_text = text[: m.start()] + prefix + new_v + suffix + text[m.end() :]
if not dry:
    path.write_text(new_text, encoding="utf-8")
    sys.stderr.write(f"✓ Version bumped: {current_v} → {new_v}\n")
else:
    sys.stderr.write(f"  Would bump: {current_v} → {new_v}\n")
print(new_v)
PY
)"

TAG="v${NEW_VER}"
SUMMARY_PATH="$ROOT/summary.txt"
DEFAULT_SUMMARY_LINE="new version release"

write_summary() {
  local tmp
  tmp="$(mktemp)"
  if [[ -n "$SUMMARY_FILE" ]]; then
    cp "$SUMMARY_FILE" "$tmp"
  else
    printf '%s' "$SUMMARY_MSG" >"$tmp"
  fi
  python3 - "$tmp" "$SUMMARY_PATH" <<'PY'
import pathlib, sys
raw = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
dst = pathlib.Path(sys.argv[2])
text = raw.strip()
if not text:
    text = "new version release"
if not text.endswith("\n"):
    text += "\n"
dst.write_text(text, encoding="utf-8")
PY
  rm -f "$tmp"
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  BRANCH="(dry-run)"
else
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
fi

echo "=== ${PRODUCT} publish ${TAG} (${BUMP_KIND} bump on ${BRANCH}) ==="
echo ""

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] Would bump to ${NEW_VER}, build frontend, write version.txt, update summary.txt, commit, tag, push, gh release."
  if [[ "$BUILD" -eq 1 ]]; then
    echo "[dry-run] Would also build Nuitka binaries (not recommended locally; use GitHub Actions instead)."
  fi
  if [[ -n "$SUMMARY_FILE" ]]; then
    echo "[dry-run] Summary source: --summary-file $SUMMARY_FILE"
  elif [[ -n "$SUMMARY_MSG" ]]; then
    echo "[dry-run] Summary source: -m (${#SUMMARY_MSG} chars)"
  else
    echo "[dry-run] Summary: would write default line \"new version release\" (use -m or --summary-file to override)."
  fi
  echo ""
  echo "=== Done (dry-run) ==="
  exit 0
fi

echo "[1/5] Bumping version (${BUMP_KIND})..."
echo "$NEW_VER" >"$ROOT/version.txt"

echo "[2/5] Building frontend (npm ci or install + npm run build)..."
cd "$ROOT/frontend"
if [[ -f package-lock.json ]]; then
  npm ci --silent
else
  npm install --silent
fi
npm run build --silent
cd "$ROOT"
echo "  ✓ Frontend built to static/"

echo "[3/5] Writing version.txt..."
echo "$NEW_VER" >"$ROOT/version.txt"
echo "  ✓ version.txt = $NEW_VER"

echo "[4/5] Updating summary.txt (trimmed; empty -> \"${DEFAULT_SUMMARY_LINE}\")."
write_summary
echo "  ✓ summary.txt updated"

echo "[5/5] Commit and tag..."
git add -A
if git diff --staged --quiet; then
  echo "ERROR: nothing staged to commit (unexpected)." >&2
  exit 1
fi
git commit -F - <<EOF
release: ${TAG}

$(cat "$SUMMARY_PATH")
EOF
git tag "$TAG"

echo "[5/5] Commit and tag..."
git add -A
if git diff --staged --quiet; then
  echo "ERROR: nothing staged to commit (unexpected)." >&2
  exit 1
fi
git commit -F - <<EOF
release: ${TAG}

$(cat "$SUMMARY_PATH")
EOF
git tag "$TAG"
echo "  ✓ Committed and tagged ${TAG}"

echo "[6/6] Push and GitHub release..."
git push origin "$BRANCH" --tags
echo "  ✓ Pushed to origin/${BRANCH}"
if [[ "$NO_GH" -eq 0 ]]; then
  gh release create "$TAG" --title "${PRODUCT} ${TAG}" --generate-notes
  echo "  ✓ GitHub release created"
else
  echo "  ⊘ Skipped gh (--no-gh). Create release manually:"
  echo "    gh release create ${TAG} --title \"${PRODUCT} ${TAG}\" --generate-notes"
fi

if [[ "$BUILD" -eq 1 ]]; then
  echo ""
  echo "[7/7] Building Nuitka binaries..."
  bash "$ROOT/build_release.sh"
fi

echo ""
echo "=== Done (${TAG}) ==="
