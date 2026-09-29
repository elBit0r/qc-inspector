"""Verifica preventiva dell'accesso ai percorsi runtime, senza modificare dati."""

import os
import tempfile

from .app_config import get_config_path, get_db_path, get_options_path, get_pdf_dir


def _check_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        raise PermissionError(f"Permessi insufficienti sulla cartella: {path}")
    # Verifica anche filesystem in sola lettura e ACL con una scrittura reale.
    with tempfile.NamedTemporaryFile(prefix=".qc-access-", dir=path) as probe:
        probe.write(b"QC")
        probe.flush()


def _check_file(path: str) -> None:
    _check_directory(os.path.dirname(os.path.abspath(path)))
    if os.path.lexists(path):
        # Non tronca il file e non ne modifica il contenuto.
        with open(path, "r+b"):
            pass


def _check_readable_file(path: str) -> None:
    if os.path.lexists(path):
        with open(path, "rb"):
            pass
        return
    _check_directory(os.path.dirname(os.path.abspath(path)))


def check_runtime_access() -> None:
    """Controlla config, database e PDF prima di inizializzare SQLite."""
    config_path = get_config_path()
    options_path = get_options_path()
    if options_path == config_path:
        _check_file(config_path)
    else:
        _check_readable_file(config_path)
        _check_file(options_path)
    _check_file(get_db_path())
    _check_directory(get_pdf_dir())


def permission_error_message(error: OSError) -> str:
    message = (
        "L'utente non dispone dei permessi necessari per utilizzare QC Inspector.\n\n"
        f"Dettaglio: {error}\n\n"
        "Sono necessari la lettura della configurazione, la scrittura delle "
        "opzioni e del database e l'accesso alle relative cartelle e ai PDF."
    )
    if os.name == "posix":
        import grp
        try:
            group_id = grp.getgrnam("qc-inspector").gr_gid
        except KeyError:
            group_id = None
        if group_id is not None and group_id not in {os.getegid(), *os.getgroups()}:
            message += (
                "\n\nIl gruppo qc-inspector non è attivo nella sessione corrente "
                "dell'utente. Chiedi all'amministratore di eseguire:\n"
                "sudo usermod -aG qc-inspector <utente>\n"
                "Poi esci dalla sessione desktop e accedi nuovamente."
            )
    return message + "\n\nSe il problema persiste, chiedi all'amministratore di verificare i permessi dei percorsi indicati."
