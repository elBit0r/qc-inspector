#!/usr/bin/env bash
set -euo pipefail

APP_NAME="qc-inspector"
PKG_NAME="qc-inspector"
ARCH="amd64"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR_SOURCE="$ROOT_DIR/src/qc_inspector"
VERSION="$(awk -F '"' '/^__version__[[:space:]]*=/ { print $2; exit }' "$PACKAGE_DIR_SOURCE/__init__.py")"
DEB_ROOT="$ROOT_DIR/dist/debroot"
PKG_DIR="$DEB_ROOT/${PKG_NAME}_${VERSION}_${ARCH}"
INSTALL_DIR="/opt/${APP_NAME}"
CONFIG_DIR="/etc/qc-inspector"
CONFIG_PATH="$CONFIG_DIR/qc_inspector.conf"

if [[ -z "$VERSION" ]]; then
  echo "Errore: __version__ non trovata nel package"
  exit 1
fi

"$ROOT_DIR/build.sh"

# Ricava il requisito reale degli ELF incorporati, non quello dell'host.
command -v readelf >/dev/null || { echo "Installare binutils (readelf)." >&2; exit 1; }
GLIBC_MIN="$(
  while IFS= read -r -d '' file; do
    readelf --version-info "$file" 2>/dev/null || true
  done < <(find "$ROOT_DIR/dist/$APP_NAME" -type f -print0) |
    sed -n 's/.*Name: GLIBC_\([0-9][0-9.]*\).*/\1/p' | sort -Vu | tail -n 1
)"
if [[ -z "$GLIBC_MIN" ]]; then
  echo "Impossibile determinare la versione minima di glibc." >&2
  exit 1
fi

echo "Preparo struttura .deb..."
rm -rf "$DEB_ROOT"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR$INSTALL_DIR"
mkdir -p "$PKG_DIR$CONFIG_DIR"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/512x512/apps"
mkdir -p "$PKG_DIR/usr/share/doc/$APP_NAME"
install -m 0644 "$ROOT_DIR/LICENSE" "$PKG_DIR/usr/share/doc/$APP_NAME/LICENSE"
install -m 0644 "$ROOT_DIR/NOTICE.md" "$PKG_DIR/usr/share/doc/$APP_NAME/copyright"
install -m 0644 "$ROOT_DIR/THIRD_PARTY_NOTICES.md" \
  "$PKG_DIR/usr/share/doc/$APP_NAME/THIRD_PARTY_NOTICES.md"
mkdir -p "$PKG_DIR/usr/share/doc/$APP_NAME/third_party/licenses"
cp -a "$ROOT_DIR/third_party/licenses/." \
  "$PKG_DIR/usr/share/doc/$APP_NAME/third_party/licenses/"

echo "Copio runtime in $INSTALL_DIR..."
cp -a "$ROOT_DIR/dist/$APP_NAME/." "$PKG_DIR$INSTALL_DIR/"
rm -f "$PKG_DIR$INSTALL_DIR/qc_database.sqlite"
install -m 0644 "$ROOT_DIR/packaging/qc_inspector.debian.conf" "$PKG_DIR$CONFIG_PATH"
cp -f "$PACKAGE_DIR_SOURCE/assets/icons/qc-inspector.png" "$PKG_DIR/usr/share/icons/hicolor/512x512/apps/qc-inspector.png"

# Launcher nel PATH: il runtime applicativo resta in /opt/qc-inspector.
cat > "$PKG_DIR/usr/bin/$APP_NAME" <<'EOF'
#!/usr/bin/env bash
exec /opt/qc-inspector/qc-inspector "$@"
EOF
chmod 0755 "$PKG_DIR/usr/bin/$APP_NAME"

cat > "$PKG_DIR/usr/share/applications/qc-inspector.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=QC Inspector
Comment=Controllo dimensionale e report
Exec=/usr/bin/qc-inspector
Icon=qc-inspector
Terminal=false
Categories=Utility;Engineering;
StartupNotify=true
EOF
chmod 0644 "$PKG_DIR/usr/share/applications/qc-inspector.desktop"

cat > "$PKG_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: QC Inspector Team
Depends: libc6 (>= $GLIBC_MIN), libstdc++6, cups-client, libgstreamer1.0-0, libgstreamer-plugins-base1.0-0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good
Description: QC Inspector desktop application
 PyQt-based tool for setup programming and dimensional inspection.
EOF

cat > "$PKG_DIR/DEBIAN/conffiles" <<EOF
$CONFIG_PATH
EOF

cat > "$PKG_DIR/DEBIAN/preinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="/etc/qc-inspector"
CONFIG_PATH="$CONFIG_DIR/qc_inspector.conf"

fail_unsafe_path() {
  echo "Errore: percorso non sicuro durante l'aggiornamento: $1" >&2
  echo "Rimuovere eventuali link e ripetere l'installazione." >&2
  exit 1
}

case "${1:-}" in
  install|upgrade)
    # /etc è amministrata da root: una directory reale sotto /etc non può
    # essere sostituita dagli utenti mentre ne vengono rimossi i permessi di
    # scrittura. Bloccarla prima di ispezionare il conffile chiude la race.
    [[ ! -L "$CONFIG_DIR" ]] || fail_unsafe_path "$CONFIG_DIR"
    if [[ -e "$CONFIG_DIR" ]]; then
      [[ -d "$CONFIG_DIR" ]] || fail_unsafe_path "$CONFIG_DIR"
      [[ "$(stat -c %u -- "$CONFIG_DIR")" == "0" ]] || fail_unsafe_path "$CONFIG_DIR"
      chmod 0755 -- "$CONFIG_DIR"
      chown root:root -- "$CONFIG_DIR"

      [[ ! -L "$CONFIG_PATH" ]] || fail_unsafe_path "$CONFIG_PATH"
      if [[ -e "$CONFIG_PATH" ]]; then
        [[ -f "$CONFIG_PATH" ]] || fail_unsafe_path "$CONFIG_PATH"
        [[ "$(stat -c %h -- "$CONFIG_PATH")" == "1" ]] || fail_unsafe_path "$CONFIG_PATH"
        chown root:root -- "$CONFIG_PATH"
        chmod 0644 -- "$CONFIG_PATH"
      fi
    fi
    ;;
esac
EOF
chmod 0755 "$PKG_DIR/DEBIAN/preinst"

cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

GROUP_NAME="qc-inspector"
VAR_ROOT="/var/qc-inspector"
PDF_DIR="/var/qc-inspector/pdf"
DB_PATH="$VAR_ROOT/qc_database.sqlite"
OPTIONS_PATH="$VAR_ROOT/qc_inspector.options.conf"
CONFIG_DIR="/etc/qc-inspector"

if ! getent group "$GROUP_NAME" >/dev/null 2>&1; then
  groupadd --system "$GROUP_NAME"
fi

fail_unsafe_path() {
  echo "Errore: percorso non sicuro durante la configurazione: $1" >&2
  echo "Nessun file collegato è stato modificato. Correggere il percorso e ripetere l'installazione." >&2
  exit 1
}

# Il conffile è amministrativo e non viene più reso scrivibile dal gruppo.
[[ ! -L "$CONFIG_DIR" && -d "$CONFIG_DIR" ]] || fail_unsafe_path "$CONFIG_DIR"
[[ "$(stat -c %u -- "$CONFIG_DIR")" == "0" ]] || fail_unsafe_path "$CONFIG_DIR"
chmod 0755 -- "$CONFIG_DIR"
chown root:root -- "$CONFIG_DIR"

# La directory principale è stabile perché /var è amministrata da root.
# Prima di ispezionare le sue voci viene tolta la scrittura al gruppo, così
# nessun percorso può essere sostituito tra controllo e utilizzo.
[[ ! -L "$VAR_ROOT" ]] || fail_unsafe_path "$VAR_ROOT"
if [[ ! -e "$VAR_ROOT" ]]; then
  install -d -o root -g root -m 0700 -- "$VAR_ROOT"
else
  [[ -d "$VAR_ROOT" ]] || fail_unsafe_path "$VAR_ROOT"
  [[ "$(stat -c %u -- "$VAR_ROOT")" == "0" ]] || fail_unsafe_path "$VAR_ROOT"
fi
chgrp "$GROUP_NAME" -- "$VAR_ROOT"
chmod 2755 -- "$VAR_ROOT"

restore_var_permissions() {
  if [[ ! -L "$VAR_ROOT" && -d "$VAR_ROOT" ]]; then
    chmod 2775 -- "$VAR_ROOT"
  fi
}
trap restore_var_permissions EXIT

[[ ! -L "$PDF_DIR" ]] || fail_unsafe_path "$PDF_DIR"
if [[ -e "$PDF_DIR" ]]; then
  [[ -d "$PDF_DIR" ]] || fail_unsafe_path "$PDF_DIR"
else
  install -d -o root -g "$GROUP_NAME" -m 2775 -- "$PDF_DIR"
fi

[[ ! -L "$DB_PATH" ]] || fail_unsafe_path "$DB_PATH"
if [[ -e "$DB_PATH" ]]; then
  [[ -f "$DB_PATH" ]] || fail_unsafe_path "$DB_PATH"
  [[ "$(stat -c %h -- "$DB_PATH")" == "1" ]] || fail_unsafe_path "$DB_PATH"
else
  install -o root -g "$GROUP_NAME" -m 0664 /dev/null "$DB_PATH"
fi

[[ ! -L "$OPTIONS_PATH" ]] || fail_unsafe_path "$OPTIONS_PATH"
if [[ -e "$OPTIONS_PATH" ]]; then
  [[ -f "$OPTIONS_PATH" ]] || fail_unsafe_path "$OPTIONS_PATH"
  [[ "$(stat -c %h -- "$OPTIONS_PATH")" == "1" ]] || fail_unsafe_path "$OPTIONS_PATH"
else
  install -o root -g "$GROUP_NAME" -m 0664 /dev/null "$OPTIONS_PATH"
fi

restore_var_permissions
trap - EXIT

cat <<'MSG'

QC Inspector installato.
Configurazione:

  /etc/qc-inspector/qc_inspector.conf
  /var/qc-inspector/qc_inspector.options.conf (opzioni modificabili dalla GUI)

Per salvare le opzioni e accedere al database e ai PDF condivisi, aggiungi gli utenti al gruppo:

  sudo usermod -aG qc-inspector <utente>

Dopo la modifica, l'utente deve chiudere la sessione e rientrare.

MSG

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
EOF
chmod 0755 "$PKG_DIR/DEBIAN/postinst"

cat > "$PKG_DIR/DEBIAN/prerm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# Dati in /var/qc-inspector preservati su remove/upgrade.
exit 0
EOF
chmod 0755 "$PKG_DIR/DEBIAN/prerm"

cat > "$PKG_DIR/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
# Non rimuovere mai dati runtime in /var/qc-inspector.
exit 0
EOF
chmod 0755 "$PKG_DIR/DEBIAN/postrm"

echo "Verifico struttura pacchetto..."
test -x "$PKG_DIR/usr/bin/$APP_NAME"
grep -qx 'exec /opt/qc-inspector/qc-inspector "$@"' "$PKG_DIR/usr/bin/$APP_NAME"
grep -qx 'Exec=/usr/bin/qc-inspector' "$PKG_DIR/usr/share/applications/qc-inspector.desktop"
test -f "$PKG_DIR$INSTALL_DIR/$APP_NAME"
test ! -e "$PKG_DIR$INSTALL_DIR/qc_database.sqlite"
test -f "$PKG_DIR$CONFIG_PATH"
grep -qx "$CONFIG_PATH" "$PKG_DIR/DEBIAN/conffiles"
test -x "$PKG_DIR/DEBIAN/preinst"
test -x "$PKG_DIR/DEBIAN/postinst"

echo "Costruisco .deb..."
dpkg-deb --root-owner-group --build "$PKG_DIR"
(
  cd "$(dirname "$PKG_DIR")"
  sha256sum "$(basename "$PKG_DIR").deb" > "$(basename "$PKG_DIR").deb.sha256"
)

echo ""
echo "Pacchetto creato:"
echo "  $PKG_DIR.deb"
