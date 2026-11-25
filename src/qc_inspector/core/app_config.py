"""
app_config.py
Gestione configurazione applicativa condivisa.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import stat
from io import BytesIO
from typing import Dict

from reportlab.lib.utils import ImageReader


CONF_NAME = "qc_inspector.conf"
SYSTEM_CONFIG_DIR = "/etc/qc-inspector"
SYSTEM_STATE_DIR = "/var/qc-inspector"
SYSTEM_OPTIONS_NAME = "qc_inspector.options.conf"
CONFIG_PATH_ENV = "QC_INSPECTOR_CONFIG"
DEFAULT_REPORT_LOGO = "@default"
APPLICATION_OPTION_KEYS = {
    "audio_enable",
    "audio_pass_file",
    "audio_fail_file",
    "decimal_separator",
}
LEGACY_LABEL_OPTION_KEYS = {"label_printer", "labels_qta", "label_enable"}
GENERAL_OPTION_KEYS = APPLICATION_OPTION_KEYS | LEGACY_LABEL_OPTION_KEYS
LABEL_OPTION_KEYS = {
    "label_printer", "labels_qta", "label_auto_print", "label_width_mm",
    "label_height_mm", "label_template",
}
DEFAULT_LABEL_TEMPLATE = (
    "# QC Inspector — {setup}\n"
    "Lotto: {lotto}\nOperatore: {operatore}\nData: {data}\n"
    "Campioni: {campioni}\nDescrizione: {descrizione}\n---\n**Esito: {esito}**"
)
LABEL_SIZE_RANGE = (10, 500)
REPORT_APPEARANCE_KEYS = {"report_logo_file", "report_footer_text"}
REPORT_OPTION_KEYS = REPORT_APPEARANCE_KEYS | {"report_dir", "report_auto_save"}
BACKUP_OPTION_KEYS = {"backup_dir"}
EDITABLE_OPTION_KEYS = GENERAL_OPTION_KEYS | REPORT_OPTION_KEYS | LABEL_OPTION_KEYS | BACKUP_OPTION_KEYS
DEFAULT_CONFIG = {
    "label_printer": "Zebra-ZPL",
    "labels_qta": "2",
    "label_enable": "YES",
    "label_auto_print": "NO",
    "label_width_mm": "105",
    "label_height_mm": "60",
    "label_template": json.dumps(DEFAULT_LABEL_TEMPLATE, ensure_ascii=False),
    "audio_enable": "YES",
    "audio_pass_file": "",
    "audio_fail_file": "",
    "report_logo_file": DEFAULT_REPORT_LOGO,
    "report_footer_text": "",
    "report_dir": "",
    "backup_dir": "",
    "report_auto_save": "NO",
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
    """Percorso delle opzioni scrivibili, separato per le installazioni di sistema."""
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
    # Recupera il nome della stampante dai file di configurazione precedenti.
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

    # Le nuove preferenze usano i valori predefiniti fino al primo salvataggio.
    optional_keys = (LABEL_OPTION_KEYS - LEGACY_LABEL_OPTION_KEYS) | BACKUP_OPTION_KEYS | {
        "report_logo_file", "report_dir", "report_auto_save",
    }
    missing = [
        key for key in runtime_defaults
        if key not in file_keys and key not in optional_keys
    ]
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


def get_report_dir(cfg: Dict[str, str]) -> str:
    value = cfg.get("report_dir", "").strip()
    return _resolve_config_path(os.path.expanduser(value)) if value else ""


def is_report_auto_save_enabled(cfg: Dict[str, str]) -> bool:
    return cfg.get("report_auto_save", "NO").strip().upper() == "YES"


def load_report_logo(value: str) -> BytesIO:
    if value == DEFAULT_REPORT_LOGO:
        asset_root = getattr(sys, "_MEIPASS", get_app_root())
        path = os.path.join(asset_root, "assets", "icons", "report-logo.png")
    else:
        path = _resolve_config_path(os.path.expanduser(value))
    try:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        with open(path, "rb") as source:
            image = BytesIO(source.read())
        ImageReader(image).getRGBData()
        image.seek(0)
        return image
    except Exception as exc:
        raise ValueError(f"Impossibile leggere l'immagine del logo: {path}") from exc


def get_label_layout(cfg: Dict[str, str]) -> tuple[float, float, str]:
    dimensions = []
    for key in ("label_width_mm", "label_height_mm"):
        value = float(cfg.get(key, DEFAULT_CONFIG[key]))
        if not LABEL_SIZE_RANGE[0] <= value <= LABEL_SIZE_RANGE[1]:
            raise ValueError("Le dimensioni devono essere comprese tra 10 e 500 mm.")
        dimensions.append(value)
    template = json.loads(cfg.get("label_template", DEFAULT_CONFIG["label_template"]))
    if not isinstance(template, str) or not template.strip():
        raise ValueError("Inserisci il contenuto dell’etichetta.")
    return dimensions[0], dimensions[1], template


def save_options(options: Dict[str, str]) -> None:
    """Salva le preferenze preservando commenti, percorsi e chiavi aggiuntive."""
    keys = set(options)
    if keys not in (
        GENERAL_OPTION_KEYS,
        GENERAL_OPTION_KEYS | {"report_footer_text"},
        APPLICATION_OPTION_KEYS,
        LABEL_OPTION_KEYS,
        GENERAL_OPTION_KEYS | REPORT_OPTION_KEYS,
        EDITABLE_OPTION_KEYS,
        EDITABLE_OPTION_KEYS - BACKUP_OPTION_KEYS,
        BACKUP_OPTION_KEYS,
        REPORT_OPTION_KEYS,
        REPORT_APPEARANCE_KEYS,
    ):
        raise ValueError("Opzioni di configurazione non valide.")
    values = {key: str(value).strip() for key, value in options.items()}
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Le opzioni non possono contenere ritorni a capo.")
    if "label_printer" in keys:
        if not values["label_printer"] and values.get("label_auto_print") != "NO":
            raise ValueError("Indica il nome della stampante.")
        if not 1 <= int(values["labels_qta"]) <= 999:
            raise ValueError("Il numero di copie deve essere compreso tra 1 e 999.")
        if values.get("label_enable", "NO") not in {"YES", "NO"}:
            raise ValueError("Abilitazione stampa non valida.")
    if LABEL_OPTION_KEYS <= keys:
        if values["label_auto_print"] not in {"YES", "NO"}:
            raise ValueError("Abilitazione della stampa automatica non valida.")
        get_label_layout(values)
    if APPLICATION_OPTION_KEYS <= keys:
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
    if values.get("report_logo_file"):
        load_report_logo(values["report_logo_file"])
    if "report_auto_save" in values:
        if values["report_auto_save"] not in {"YES", "NO"}:
            raise ValueError("Salvataggio automatico dei report non valido.")
        report_dir = get_report_dir(values)
        auto_save = is_report_auto_save_enabled(values)
        if auto_save and not report_dir:
            raise ValueError("Scegli una cartella per il salvataggio automatico dei report.")
        if report_dir and not os.path.isdir(report_dir):
            raise ValueError(f"Cartella report non disponibile: {report_dir}")
        if auto_save and not os.access(report_dir, os.W_OK | os.X_OK):
            raise ValueError(f"Cartella report non scrivibile: {report_dir}")
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
