#!/usr/bin/env bash
# Verifica il caricamento reale con lo stesso search path del binario frozen.
set -euo pipefail
RUNTIME_DIR="$(cd "${1:?Specificare la directory _internal del bundle}" && pwd)"
for tool in gst-inspect-1.0 gst-launch-1.0; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Verifica audio: installare gstreamer1.0-tools sulla macchina di build." >&2
    exit 1
  fi
done
CHECK_DIR="$(mktemp -d)"
trap 'rm -rf "$CHECK_DIR"' EXIT
export LD_LIBRARY_PATH="$RUNTIME_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# Non riutilizzare il registro dell'utente: potrebbe nascondere plugin mancanti.
export GST_REGISTRY="$CHECK_DIR/registry.bin"
unset GST_PLUGIN_PATH GST_PLUGIN_PATH_1_0 GST_PLUGIN_SYSTEM_PATH GST_PLUGIN_SYSTEM_PATH_1_0
unset GST_PLUGIN_SCANNER GST_PLUGIN_SCANNER_1_0
for element in identity oggdemux vorbisdec audioconvert audioresample autoaudiosink pulsesink; do
  gst-inspect-1.0 "$element" > "$CHECK_DIR/inspect.log" 2>&1 || {
    cat "$CHECK_DIR/inspect.log" >&2
    echo "Verifica audio fallita: elemento $element non caricabile nel bundle." >&2
    exit 1
  }
done
for sound in pass.oga error.oga; do
  timeout 20s gst-launch-1.0 -q filesrc location="$RUNTIME_DIR/assets/audio/$sound" \
    '!' decodebin '!' audioconvert '!' audioresample '!' identity '!' fakesink
done
echo "Verifica audio: identity, plugin e decodifica PASS/FAIL OK (uscita simulata)."
