#!/bin/bash
# Assemble a portable, shareable zip of the RedArc Video Tool.
# Excludes the venv, output, and built .app — those are created by setup.command
# on the recipient's machine. Run from the tool folder: ./make-package.sh
set -e
cd "$(dirname "$0")"

NAME="RedArc-Video-Tool"
STAGE="$(mktemp -d)/$NAME"
mkdir -p "$STAGE"

# Code + recipient-facing files
cp process_video.py grab.py droplet.applescript README.md setup.command "$STAGE/"
cp "READ ME FIRST.txt" "$STAGE/"
chmod +x "$STAGE/setup.command"

# The PDF guide lives in the published site repo; include it if present.
GUIDE="../redarcenv-site/video-tool/RedArc_Video_Tool_Guide.pdf"
[ -f "$GUIDE" ] && cp "$GUIDE" "$STAGE/"

# Zip it (cd into stage parent so the archive contains the named folder).
rm -f "$NAME.zip"
( cd "$(dirname "$STAGE")" && zip -r -q -X "$OLDPWD/$NAME.zip" "$NAME" )
rm -rf "$(dirname "$STAGE")"

echo "Built $NAME.zip:"
unzip -l "$NAME.zip"
