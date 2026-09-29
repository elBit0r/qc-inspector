#!/usr/bin/env bash
set -euo pipefail

APP_NAME="qc-inspector"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR_SOURCE="$ROOT_DIR/src/qc_inspector"
APP_VERSION="$(awk -F '"' '/^__version__[[:space:]]*=/ { print $2; exit }' "$PACKAGE_DIR_SOURCE/__init__.py")"
VENV_PY="$ROOT_DIR/.venv/bin/python"
VENV_PIP="$ROOT_DIR/.venv/bin/pip"
PYINSTALLER="$ROOT_DIR/.venv/bin/pyinstaller"
TARGET="linux-x86_64"
PACKAGE_DIR="$ROOT_DIR/dist/${APP_NAME}-package"

if [[ "$(uname -m)" != "x86_64" ]]; then
  echo "Build supportata soltanto su host x86_64." >&2
  exit 1
fi

if [[ -z "$APP_VERSION" ]]; then
  echo "Errore: __version__ non trovata nel package"
  exit 1
fi

if [[ ! -x "$VENV_PY" ]]; then
  echo "Errore: ambiente virtuale non trovato in .venv"
  echo "Crea prima il venv: python3 -m venv .venv"
  exit 1
fi

if ! "$VENV_PY" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller non trovato nel venv: installo..."
  "$VENV_PIP" install -c "$ROOT_DIR/constraints-release.txt" pyinstaller
fi
"$VENV_PY" - "$ROOT_DIR/constraints-release.txt" <<'PY'
import importlib.metadata
import sys
from pathlib import Path

errors = []
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    name, expected = line.split("==")
    try:
        actual = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        actual = "non installato"
    if actual != expected:
        errors.append(f"{name}: atteso {expected}, trovato {actual}")
if errors:
    sys.exit("Ambiente diverso dai vincoli di release:\n" + "\n".join(errors))
PY
"$VENV_PIP" install --no-deps --no-build-isolation --editable "$ROOT_DIR"

cd "$ROOT_DIR"

echo "Pulizia output precedente..."
rm -rf build dist

echo "Build PyInstaller v$APP_VERSION..."
"$PYINSTALLER" --noconfirm --clean "$ROOT_DIR/qc-inspector.spec"

# GStreamer deve usare librerie, plugin e scanner della stessa installazione.
# Le copie rilocate da PyInstaller cercano i plugin nel bundle, dove mancano
# coreelements (identity) e i codec. Anche GLib resta quella del sistema.
echo "Uso GStreamer e GLib del sistema..."
rm -f "dist/$APP_NAME/_internal/"libgst*.so* \
  "dist/$APP_NAME/_internal/"libglib-2.0.so* \
  "dist/$APP_NAME/_internal/"libgobject-2.0.so* \
  "dist/$APP_NAME/_internal/"libgmodule-2.0.so* \
  "dist/$APP_NAME/_internal/"libgio-2.0.so*
bash "$ROOT_DIR/tools/check_audio_runtime.sh" "$ROOT_DIR/dist/$APP_NAME/_internal"

echo "Preparo pacchetto..."
mkdir -p "$PACKAGE_DIR"
cp -r "dist/${APP_NAME}" "$PACKAGE_DIR/"
cp LICENSE NOTICE.md THIRD_PARTY_NOTICES.md "$PACKAGE_DIR/"
cp -a third_party "$PACKAGE_DIR/"
mkdir -p "$PACKAGE_DIR/${APP_NAME}/pdf"
rm -f "$PACKAGE_DIR/${APP_NAME}/qc_database.sqlite"
cat > "$PACKAGE_DIR/${APP_NAME}/qc_inspector.conf.sample" <<'EOF'
label_printer = Zebra-ZPL
labels_qta = 2
label_enable = YES
db_path = qc_database.sqlite
pdf_dir = pdf
decimal_separator = .
EOF

echo "Creo database portable vuoto con lo schema corrente..."
PORTABLE_DB="$PACKAGE_DIR/${APP_NAME}/qc_database.sqlite"
(
  cd "$ROOT_DIR"
  "$VENV_PY" -m qc_inspector.database.schema_manager \
    "$PORTABLE_DB" --no-backup
)

cat > "$PACKAGE_DIR/README.txt" <<EOF
QC Inspector package (Linux x86_64)
Version: $APP_VERSION

1) Entra nella cartella qc-inspector
2) Copia qc_inspector.conf.sample in qc_inspector.conf
3) Imposta parametri stampante nel file qc_inspector.conf:
   - label_printer
   - labels_qta
   - label_enable
4) Imposta path runtime:
   - db_path
   - pdf_dir
5) Avvia con: ./qc-inspector

Nota:
- Il pacchetto portable usa il config accanto all'eseguibile.
- Il database portable incluso e vuoto e viene ricreato a ogni build.
- Il pacchetto .deb usa invece /etc/qc-inspector/qc_inspector.conf.
EOF

echo "Creo archivio distribuzione..."
tar -czf "dist/${APP_NAME}-${APP_VERSION}-${TARGET}.tar.gz" -C dist "$(basename "$PACKAGE_DIR")"
(
  cd dist
  sha256sum "${APP_NAME}-${APP_VERSION}-${TARGET}.tar.gz" > "${APP_NAME}-${APP_VERSION}-${TARGET}.tar.gz.sha256"
)

echo ""
echo "Build completata:"
echo "  - Eseguibile: dist/${APP_NAME}/${APP_NAME}"
echo "  - Archivio:   dist/${APP_NAME}-${APP_VERSION}-${TARGET}.tar.gz"
