"""
app_config.py
Gestione configurazione applicativa condivisa.
"""

from __future__ import annotations

import os
import sys
import tempfile
import stat
from typing import Dict


CONF_NAME = "qc_inspector.conf"
SYSTEM_CONFIG_DIR = "/etc/qc-inspector"
SYSTEM_STATE_DIR = "/var/qc-inspector"
SYSTEM_OPTIONS_NAME = "qc_inspector.options.conf"
CONFIG_PATH_ENV = "QC_INSPECTOR_CONFIG"
EDITABLE_OPTION_KEYS = {
    "label_printer",
    "labels_qta",
    "label_enable",
    "audio_enable",
    "audio_pass_file",
    "audio_fail_file",
    "report_footer_text",
    "decimal_separator",
}
DEFAULT_CONFIG = {
    "label_printer": "Zebra-ZPL",
    "labels_qta": "2",
    "label_enable": "YES",
    "audio_enable": "YES",
    "audio_pass_file": "",
    "audio_fail_file": "",
    "report_footer_text": "",
    "db_path": "/var/qc-inspector/qc_database.sqlite",
    "pdf_dir": "/var/qc-inspector/pdf",
    "decimal_separator": ".",
}


def get_app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(__file__))


def is_system_install() -> bool:
    return bool(
        getattr(sys, "frozen", False)
        and get_app_root().startswith("/opt/qc-inspector")
    )


def _xdg_path(environment_key: str, fallback: str) -> str:
    root = os.environ.get(environment_key) or os.path.expanduser(fallback)
    return os.path.join(root, "qc-inspector")


def get_user_data_dir() -> str:
    return _xdg_path("XDG_DATA_HOME", "~/.local/share")


def get_config_path() -> str:
    explicit_path = os.environ.get(CONFIG_PATH_ENV)
    if explicit_path:
        return os.path.abspath(os.path.expanduser(explicit_path))
    if is_system_install():
        return os.path.join(SYSTEM_CONFIG_DIR, CONF_NAME)
    if getattr(sys, "frozen", False):
        return os.path.join(get_app_root(), CONF_NAME)
    return os.path.join(_xdg_path("XDG_CONFIG_HOME", "~/.config"), CONF_NAME)


def get_options_path() -> str:
    """File scrivibile delle opzioni; coincide col config fuori dal .deb."""
    if is_system_install() and not os.environ.get(CONFIG_PATH_ENV):
        return os.path.join(SYSTEM_STATE_DIR, SYSTEM_OPTIONS_NAME)
    return get_config_path()


def _runtime_defaults() -> Dict[str, str]:
    defaults = dict(DEFAULT_CONFIG)
    if is_system_install():
        return defaults
    if getattr(sys, "frozen", False):
        defaults["db_path"] = "qc_database.sqlite"
        defaults["pdf_dir"] = "pdf"
    else:
        data_dir = get_user_data_dir()
        defaults["db_path"] = os.path.join(data_dir, "qc_database.sqlite")
        defaults["pdf_dir"] = os.path.join(data_dir, "pdf")
    return defaults


def _read_config_values(
    path: str,
    cfg: Dict[str, str],
    file_keys: set[str],
    allowed_keys: set[str] | None = None,
) -> None:
    with open(path, "r", encoding="utf-8") as source:
        for raw in source:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = [part.strip() for part in line.split("=", 1)]
            key = key.lower()
            if key and (allowed_keys is None or key in allowed_keys):
                cfg[key] = value
                file_keys.add(key)


def load_or_create_config() -> Dict[str, str]:
    path = get_config_path()
    options_path = get_options_path()
    split_system_config = options_path != path
    config_dir = os.path.dirname(path)
    if config_dir and not split_system_config:
        os.makedirs(config_dir, exist_ok=True)
    if not os.path.exists(path):
        if split_system_config:
            raise FileNotFoundError(f"File di configurazione non trovato: {path}")
        with open(path, "w", encoding="utf-8") as f:
            for key, value in _runtime_defaults().items():
                f.write(f"{key} = {value}\n")

    runtime_defaults = _runtime_defaults()
    cfg = dict(runtime_defaults)
    file_keys = set()
    _read_config_values(path, cfg, file_keys)
    # backward compatibility
    if "printername" in file_keys and "label_printer" not in file_keys:
        cfg["label_printer"] = cfg["printername"]
    if split_system_config and os.path.exists(options_path):
        _read_config_values(
            options_path,
            cfg,
            file_keys,
            allowed_keys=EDITABLE_OPTION_KEYS,
        )
    if split_system_config:
        return cfg

    missing = [key for key in runtime_defaults if key not in file_keys]
    if missing:
        needs_newline = False
        if os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                needs_newline = f.read(1) != b"\n"
        with open(path, "a", encoding="utf-8") as f:
            if needs_newline:
                f.write("\n")
            for key in missing:
                value = cfg[key]
                f.write(f"{key} = {value}\n")
    return cfg


def _resolve_config_path(value: str) -> str:
    if os.path.isabs(value):
        return value
    return os.path.join(os.path.dirname(get_config_path()), value)


def save_options(options: Dict[str, str]) -> None:
    """Salva le preferenze preservando commenti, percorsi e chiavi aggiuntive."""
    if set(options) != EDITABLE_OPTION_KEYS:
        raise ValueError("Opzioni di configurazione non valide.")
    values = {key: str(value).strip() for key, value in options.items()}
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Le opzioni non possono contenere ritorni a capo.")
    if not values["label_printer"]:
        raise ValueError("Indica il nome della stampante.")
    if not 1 <= int(values["labels_qta"]) <= 999:
        raise ValueError("Il numero di copie deve essere compreso tra 1 e 999.")
    if values["label_enable"] not in {"YES", "NO"}:
        raise ValueError("Abilitazione stampa non valida.")
    if values["audio_enable"] not in {"YES", "NO"}:
        raise ValueError("Abilitazione audio non valida.")
    if values["decimal_separator"] not in {".", ","}:
        raise ValueError("Separatore decimale non valido.")
    for key in ("audio_pass_file", "audio_fail_file"):
        if values[key]:
            audio_path = _resolve_config_path(values[key])
            if not os.path.isfile(audio_path):
                raise ValueError(f"File audio non valido: {audio_path}")
            with open(audio_path, "rb"):
                pass
    path = get_options_path()
    if os.path.lexists(path):
        metadata = os.lstat(path)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"Il file delle opzioni non è un file regolare: {path}")
        with open(path, encoding="utf-8") as source:
            lines = source.readlines()
        output_mode = stat.S_IMODE(metadata.st_mode)
    else:
        lines = []
        output_mode = 0o664
    remaining = set(values)
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip().lower()
        if key in values:
            lines[index] = f"{key} = {values[key]}\n"
            remaining.discard(key)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.extend(f"{key} = {values[key]}\n" for key in values if key in remaining)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(path), delete=False
        ) as output:
            temporary = output.name
            output.writelines(lines)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), output_mode)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def get_db_path() -> str:
    return _resolve_config_path(
        load_or_create_config().get("db_path", "/var/qc-inspector/qc_database.sqlite")
    )


def get_pdf_dir() -> str:
    return _resolve_config_path(
        load_or_create_config().get("pdf_dir", "/var/qc-inspector/pdf")
    )


def is_audio_enabled() -> bool:
    """Legge la preferenza audio corrente, abilitata per impostazione predefinita."""
    return load_or_create_config().get("audio_enable", "YES").strip().upper() in {
        "YES", "Y", "TRUE", "1", "ON"
    }


def get_decimal_separator() -> str:
    sep = load_or_create_config().get("decimal_separator", ".").strip()
    return "," if sep == "," else "."


def format_decimal(value: float, decimals: int = 3, signed: bool = False) -> str:
    sign = "+" if signed else ""
    text = f"{value:{sign}.{decimals}f}"
    sep = get_decimal_separator()
    if sep != ".":
        text = text.replace(".", sep)
    return text


def parse_decimal(text: str) -> float:
    cleaned = text.strip().replace(",", ".")
    return float(cleaned)
