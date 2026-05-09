#!/usr/bin/env sh
URL="http://127.0.0.1:17832/ui/"
if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"
else
  echo "$URL"
fi
