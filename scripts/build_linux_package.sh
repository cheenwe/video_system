#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${APP_NAME:-lab_system_server}"
OUT_DIR="${OUT_DIR:-dist/linux}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "==> Installing build dependencies..."
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install pyinstaller

LAUNCHER="scripts/_build_launcher_linux.py"
cat > "$LAUNCHER" <<'PY'
import uvicorn
from src.main import app
from src.core.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
PY

echo "==> Building Linux binary..."
"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name "$APP_NAME" \
  --paths . \
  "$LAUNCHER"

rm -f "$LAUNCHER"

mkdir -p "$OUT_DIR"
cp "dist/$APP_NAME" "$OUT_DIR/$APP_NAME"
cp -r web "$OUT_DIR/web"
cp -r src "$OUT_DIR/src"
cp -r scripts "$OUT_DIR/scripts"
cp requirements.txt "$OUT_DIR/requirements.txt"
cp README.md "$OUT_DIR/README.md"

PKG="dist/${APP_NAME}_linux_$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf "$PKG" -C "$OUT_DIR" .
echo "==> Done. Package: $PKG"

