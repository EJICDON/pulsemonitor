#!/usr/bin/env bash
# PulseMonitor Semantic Version Bump & Git Tagging Script
# Usage: ./scripts/release.sh <new_version> [release_notes]
# Example: ./scripts/release.sh 1.2.0 "Add disk temperature alert"
set -e

cd "$(dirname "$0")/.."

NEW_VER="$1"
NOTES="${2:-Release v$1}"

if [ -z "$NEW_VER" ]; then
  echo "Usage: ./scripts/release.sh <version> [commit_message]"
  echo "Current version: $(cat VERSION)"
  exit 1
fi

echo "${NEW_VER}" > VERSION
echo "📌 Updated VERSION to ${NEW_VER}"

# Update Info.plist version in macos_app/build_app.sh if present
python3 linux/build_linux_packages.py

git add VERSION
git commit -m "chore(release): v${NEW_VER} - ${NOTES}"
git tag -a "v${NEW_VER}" -m "PulseMonitor v${NEW_VER}: ${NOTES}"

echo ""
echo "✅ Created commit and annotated Git tag: v${NEW_VER}"
echo "🚀 To push to GitHub and trigger automated GitHub Release builds, run:"
echo "   git push origin main --follow-tags"
