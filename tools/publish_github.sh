#!/usr/bin/env bash
# Veröffentlichung des öffentlichen GitHub-Snapshots aus dem privaten
# Entwicklungsrepo (Spec: openspec/specs/release/github-publishing).
#
# Erzeugt pro Release einen Squash-Snapshot: git archive eines Referenz-
# stands, Entnahme privater/interner Inhalte, Pflicht-Prüfschritt, ein
# Commit auf der öffentlichen Historie (Fast-Forward, kein Force-Push),
# Tag und Push auf den übergebenen GitHub-Remote.
#
# Zugriff nur via SSH-Remote oder Git-Credential-Helper — niemals Token in
# Remote-URL oder Dateien. Autorenidentität: BRS_GIT_AUTHOR_NAME /
# BRS_GIT_AUTHOR_EMAIL (Default: GitHub-noreply).
#
# Aufruf:
#   tools/publish_github.sh --remote <url-oder-remote> [--ref <rev>]
#       [--branch <zweig>] [--tag <tag>] [--from <verzeichnis>]
#       [--scan <verzeichnis>] [--dry-run]
#
# --from  Snapshot-Quelle statt `git archive <ref>` (Verzeichnis; für
#         Tests/Manuelle Vorabinhalte).
# --scan  nur den Prüfschritt gegen ein Verzeichnis ausführen und enden
#         (Exit 0 = sauber, Exit 1 = Treffer).
set -euo pipefail

REMOTE=""
REF="main"
BRANCH="main"
TAG=""
SOURCE_DIR=""
SCAN_DIR=""
DRY_RUN=0

die() { echo "FEHLER: $*" >&2; exit 1; }
log() { echo "==> $*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --remote) REMOTE="${2:?--remote benötigt einen Wert}"; shift 2 ;;
        --ref)    REF="${2:?}"; shift 2 ;;
        --branch) BRANCH="${2:?}"; shift 2 ;;
        --tag)    TAG="${2:?}"; shift 2 ;;
        --from)   SOURCE_DIR="${2:?}"; shift 2 ;;
        --scan)   SCAN_DIR="${2:?}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) die "unbekannte Option: $1" ;;
    esac
done

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

# --- Prüfschritt -----------------------------------------------------------
# Pflicht vor jedem Push: findet er etwas, wird NICHTS gepusht.
scan_dir() {
    local dir="$1" fail=0 hit
    echo "--- Prüfschritt: $dir ---"

    # (a) datasets/: außer der Platzhalter-README nichts erlauben
    if [ -d "$dir/datasets" ]; then
        hit="$(find "$dir/datasets" -type f ! -name README.md | head -5)"
        if [ -n "$hit" ]; then
            echo "  [datasets] nicht erlaubte Dateien:"; echo "$hit"; fail=1
        fi
    fi

    # (b) interne Verzeichnisse/Dateien
    for p in .opencode openspec/changes AGENTS.md; do
        if [ -e "$dir/$p" ]; then echo "  [intern] enthalten: $p"; fail=1; fi
    done

    # (c) Inhalts-Muster: Heimpfad/Username/Kontakt, Anbieter/Modelle, Tokens
    local -a pats=(
        '/home/[a-z0-9._-]+'
        'hlampesberger'
        '@lampesberger\.at'
        'kompilomat'
        'ki-lab'
        'gemma-4'
        '[Qq]wen'
        'glpat-[A-Za-z0-9_-]{6,}'
        'gh[pousr]_[A-Za-z0-9]{16,}'
        'github_pat_'
    )
    # tools/publish_github.sh ist vom Inhalts-Scan ausgenommen: es enthält
    # die Suchmuster (inkl. Token-Regexe) selbst zwangsläufig; strukturelle
    # Checks (datasets, .opencode, openspec/changes, AGENTS.md) wirken
    # weiterhin auf alle Dateien.
    local pat
    for pat in "${pats[@]}"; do
        hit="$(grep -rIlE --exclude=publish_github.sh -e "$pat" "$dir" 2>/dev/null \
              | sed "s|^$dir/||" | head -5 || true)"
        if [ -n "$hit" ]; then
            echo "  [muster /$pat/] in:"; echo "$hit"; fail=1
        fi
    done

    if [ "$fail" -ne 0 ]; then
        echo "PRÜFSCHRITT FEHLGESCHLAGEN — kein Push." >&2
        return 1
    fi
    echo "Prüfschritt sauber."
}

if [ -n "$SCAN_DIR" ]; then
    scan_dir "$SCAN_DIR"
    exit $?
fi

[ -n "$REMOTE" ] || die "--remote fehlt (URL oder konfigurierter Remote-Name)"

TMP="$(mktemp -d /tmp/brs-publish.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
SNAP="$TMP/snapshot"
PUB="$TMP/public"

# --- Snapshot erzeugen -------------------------------------------------------
if [ -n "$SOURCE_DIR" ]; then
    log "Snapshot aus Verzeichnis: $SOURCE_DIR"
    mkdir -p "$SNAP"
    ( cd "$SOURCE_DIR" && tar --exclude=.git --exclude=node_modules -cf - . ) \
        | tar -xf - -C "$SNAP"
else
    log "Snapshot via git archive $REF"
    mkdir -p "$SNAP"
    git -C "$REPO_ROOT" archive "$REF" | tar -xf - -C "$SNAP"
fi

log "Entnahme privater/interner Inhalte"
rm -rf "$SNAP/.opencode" "$SNAP/openspec/changes" "$SNAP/AGENTS.md"
if [ -d "$SNAP/datasets" ]; then
    find "$SNAP/datasets" -mindepth 1 -maxdepth 1 ! -name README.md \
        -exec rm -rf {} +
fi

scan_dir "$SNAP" || exit 1

# --- Öffentliche Kette übernehmen -------------------------------------------
AUTHOR_NAME="${BRS_GIT_AUTHOR_NAME:-hlampesberger}"
AUTHOR_EMAIL="${BRS_GIT_AUTHOR_EMAIL:-hlampesberger@users.noreply.github.com}"
[ -n "$TAG" ] || TAG="release-$(date +%Y%m%d-%H%M%S)"

log "Öffentlichen Zweig $BRANCH von $REMOTE übernehmen"
if git ls-remote --heads "$REMOTE" "$BRANCH" 2>/dev/null | grep -q .; then
    git clone -q --branch "$BRANCH" "$REMOTE" "$PUB"
else
    log "Zweig $BRANCH existiert nicht — neue öffentliche Historie"
    git init -q "$PUB"
    git -C "$PUB" checkout -q -b "$BRANCH"
fi

# Snapshot-Inhalt in den öffentlichen Arbeitsstand übernehmen (.git bleibt).
git -C "$PUB" rm -rfq --cached . 2>/dev/null || true
find "$PUB" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$SNAP/." "$PUB/"
git -C "$PUB" add -A

if git -C "$PUB" diff --cached --quiet; then
    log "Keine Änderungen gegenüber dem öffentlichen Stand — nichts zu tun."
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    log "Dry-Run: Commit/Beschreibung wäre:"
    git -C "$PUB" diff --cached --stat | tail -5
    log "Dry-Run: kein Commit, kein Tag, kein Push."
    exit 0
fi

log "Commit (Autor: $AUTHOR_NAME <$AUTHOR_EMAIL>) und Tag $TAG"
export GIT_AUTHOR_NAME="$AUTHOR_NAME" GIT_AUTHOR_EMAIL="$AUTHOR_EMAIL"
export GIT_COMMITTER_NAME="$AUTHOR_NAME" GIT_COMMITTER_EMAIL="$AUTHOR_EMAIL"
git -C "$PUB" commit -q -m "Release $TAG

Snapshot des privaten Entwicklungsstands $REF (Squash, ohne private
Referenz-Samples und interne Planungsartefakte)."
git -C "$PUB" tag "$TAG"

log "Push -> $REMOTE ($BRANCH, $TAG)"
git -C "$PUB" push "$REMOTE" "HEAD:refs/heads/$BRANCH"
git -C "$PUB" push "$REMOTE" "refs/tags/$TAG"
log "Fertig: $BRANCH + $TAG auf $REMOTE"
