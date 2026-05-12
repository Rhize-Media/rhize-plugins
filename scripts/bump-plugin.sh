#!/usr/bin/env bash
# bump-plugin.sh — atomically bump a plugin's version in BOTH
#   <plugin>/.claude-plugin/plugin.json
#   .claude-plugin/marketplace.json
#
# This prevents the drift that hides updates from Claude Desktop: the
# cowork_plugins cache is keyed by the version in marketplace.json, so if
# only the per-plugin plugin.json moves, Claude considers the marketplace
# "Already up to date" and never pulls.
#
# Usage:
#   scripts/bump-plugin.sh <plugin-name> <patch|minor|major>
#
# Examples:
#   scripts/bump-plugin.sh seo-aeo-geo patch    # 1.1.0 -> 1.1.1
#   scripts/bump-plugin.sh project-launcher minor   # 1.1.0 -> 1.2.0
#   scripts/bump-plugin.sh obsidian-second-brain major  # 1.1.0 -> 2.0.0
#
# Requires: jq (brew install jq)

set -euo pipefail

PLUGIN="${1:-}"
BUMP="${2:-}"

if [[ -z "$PLUGIN" || -z "$BUMP" ]]; then
  echo "Usage: $0 <plugin-name> <patch|minor|major>" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required. Install with: brew install jq" >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PLUGIN_MANIFEST="$REPO_ROOT/$PLUGIN/.claude-plugin/plugin.json"
MARKETPLACE="$REPO_ROOT/.claude-plugin/marketplace.json"

if [[ ! -f "$PLUGIN_MANIFEST" ]]; then
  echo "Error: $PLUGIN_MANIFEST not found" >&2
  exit 1
fi
if [[ ! -f "$MARKETPLACE" ]]; then
  echo "Error: $MARKETPLACE not found" >&2
  exit 1
fi

# Confirm the plugin is registered in marketplace.json
REGISTERED=$(jq -r --arg name "$PLUGIN" '.plugins[] | select(.name==$name) | .name' "$MARKETPLACE")
if [[ -z "$REGISTERED" ]]; then
  echo "Error: '$PLUGIN' is not registered in $MARKETPLACE" >&2
  echo "Registered plugins:" >&2
  jq -r '.plugins[].name | "  - " + .' "$MARKETPLACE" >&2
  exit 1
fi

# Read current versions from both sources
PLUGIN_VER=$(jq -r '.version' "$PLUGIN_MANIFEST")
MARKET_VER=$(jq -r --arg name "$PLUGIN" '.plugins[] | select(.name==$name) | .version' "$MARKETPLACE")

if [[ "$PLUGIN_VER" != "$MARKET_VER" ]]; then
  echo "Warning: $PLUGIN versions disagree BEFORE bump:" >&2
  echo "  plugin.json:      $PLUGIN_VER" >&2
  echo "  marketplace.json: $MARKET_VER" >&2
  echo "Using plugin.json ($PLUGIN_VER) as the source of truth and bumping from there." >&2
fi

# Validate semver shape
if ! [[ "$PLUGIN_VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: current version '$PLUGIN_VER' is not a plain semver (X.Y.Z)" >&2
  exit 1
fi

# Compute new version
IFS='.' read -r MAJOR MINOR PATCH <<< "$PLUGIN_VER"
case "$BUMP" in
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
  *) echo "Error: bump must be one of: patch | minor | major" >&2; exit 1 ;;
esac
NEW_VER="$MAJOR.$MINOR.$PATCH"

# Write plugin.json (atomic via temp file in same dir for same-fs rename)
tmp=$(mktemp "${PLUGIN_MANIFEST}.XXXXXX")
jq --arg v "$NEW_VER" '.version = $v' "$PLUGIN_MANIFEST" > "$tmp"
mv "$tmp" "$PLUGIN_MANIFEST"

# Write marketplace.json
tmp=$(mktemp "${MARKETPLACE}.XXXXXX")
jq --arg name "$PLUGIN" --arg v "$NEW_VER" \
  '(.plugins[] | select(.name==$name) | .version) = $v' \
  "$MARKETPLACE" > "$tmp"
mv "$tmp" "$MARKETPLACE"

echo "Bumped $PLUGIN: $PLUGIN_VER -> $NEW_VER"
echo ""
echo "Modified:"
echo "  $PLUGIN_MANIFEST"
echo "  $MARKETPLACE"
echo ""
echo "Next steps:"
echo "  1. Review:   git diff"
echo "  2. Commit:   git add -A && git commit -m 'chore($PLUGIN): bump to $NEW_VER'"
echo "  3. Push:     git push"
echo "  4. In Claude Desktop, refresh the rhize-plugins marketplace to pull the new version."
echo ""
echo "Tip: if this change represents a marketplace-level release (new plugin, schema change, etc.),"
echo "     also bump the top-level 'version' in $MARKETPLACE manually."
