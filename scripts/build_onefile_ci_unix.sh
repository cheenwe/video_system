#!/usr/bin/env bash
# Linux / macOS 下一键构建单文件可执行程序（与 scripts/build_windows_exe.ps1 资源策略一致）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_NAME="${APP_NAME:-lab_system_server}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "==> Repo root: $ROOT"
echo "==> Installing dependencies + PyInstaller..."
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements.txt pyinstaller

LAUNCHER="$ROOT/scripts/_build_launcher_unix_ci.py"
cat > "$LAUNCHER" <<'PY'
import uvicorn
from src.main import app
from src.core.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
PY

# Unix 下 PyInstaller --add-data 分隔符为 src:dest
ADD_DATA=(
  "--add-data" "web:web"
  "--add-data" "alembic:alembic"
  "--add-data" "alembic.ini:."
)
if [[ -f "$ROOT/.env.example" ]]; then
  ADD_DATA+=("--add-data" ".env.example:.")
fi

echo "==> PyInstaller onefile ($APP_NAME)..."
"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name "$APP_NAME" \
  --paths "$ROOT" \
  --collect-submodules src \
  --collect-submodules uvicorn \
  "${ADD_DATA[@]}" \
  "$LAUNCHER"

rm -f "$LAUNCHER"
echo "==> Done: $ROOT/dist/$APP_NAME"
