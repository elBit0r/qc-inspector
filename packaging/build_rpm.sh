#!/usr/bin/env bash
set -euo pipefail

VERSION="$1"
GLIBC_MIN="$2"
export QC_INSPECTOR_PACKAGE_ROOT="$3"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RPM_WORK="$(mktemp -d)"
trap 'rm -rf "$RPM_WORK"' EXIT
RPM_NAME="qc-inspector-${VERSION}-1.x86_64.rpm"
RPM_OUTPUT="$ROOT_DIR/dist/rpm"

echo "Costruisco RPM..."
cp "$QC_INSPECTOR_PACKAGE_ROOT/DEBIAN/"{preinst,postinst} "$RPM_WORK/"
rpmbuild -bb --nodeps --target x86_64 \
  --define "_topdir $RPM_WORK" \
  --define "_tmppath $RPM_WORK" \
  --define "_rpmformat 4" \
  --define "app_version $VERSION" \
  --define "glibc_min $GLIBC_MIN" \
  "$ROOT_DIR/packaging/qc-inspector.rpm.spec"

mkdir -p "$RPM_OUTPUT"
install -m 0644 "$RPM_WORK/RPMS/x86_64/$RPM_NAME" "$RPM_OUTPUT/$RPM_NAME"
(
  cd "$RPM_OUTPUT"
  sha256sum "$RPM_NAME" > "$RPM_NAME.sha256"
)
echo "Pacchetto creato: $RPM_OUTPUT/$RPM_NAME"
