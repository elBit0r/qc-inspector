"""
db_manager.py
Gestione database SQLite per QC Inspector.
Tabelle: setups, controls, setup_revisions, revision_controls, lots,
measurements, operators, suppliers, sampling_classes, sampling_plans,
sampling_plan_defaults
"""

import sqlite3
import os
import math
import hashlib
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict

from ..core.app_config import get_db_path
from ..core.sampling_plans import (
    SAMPLING_PLAN_COLUMNS, SAMPLING_PLANS, get_default_sampling_plan,
    validate_sampling_plans,
)
from ..core.inspection_engine import (
    evaluate_sampling_lot, get_required_controls_for_sample,
    STATUS_EMPTY, STATUS_PASS, STATUS_FAIL, STATUS_DEROGATION,
)


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _file_sha256(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _revision_content_hash(setup: Dict, controls: List[Dict]) -> str:
    payload = {
        "name": setup.get("name") or "",
        "description": setup.get("description") or "",
        "pdf_path": setup.get("pdf_path") or "",
        "pdf_sha256": _file_sha256(setup.get("pdf_path") or ""),
        "sampling_class_code": setup.get("sampling_class_code") or "",
        "sampling_class_description": (
            setup.get("sampling_class_description") or ""
        ),
        "controls": [
            {
                key: control.get(key)
                for key in (
                    "balloon_num", "balloon_x", "balloon_y", "pdf_page",
                    "control_type", "criticality", "label", "nominal",
                    "tol_plus", "tol_minus", "description",
                )
            }
            for control in sorted(
                controls,
                key=lambda item: (
                    int(item.get("balloon_num") or 0), int(item.get("id") or 0)
                ),
            )
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _create_setup_revision(
        conn: sqlite3.Connection, setup_id: int,
        controls: List[Dict]) -> tuple[int, int]:
    setup_row = conn.execute("""
        SELECT s.*, sc.code AS sampling_class_code,
               sc.description AS sampling_class_description
        FROM setups s
        LEFT JOIN sampling_classes sc ON sc.id=s.sampling_class_id
        WHERE s.id=?
    """, (setup_id,)).fetchone()
    if setup_row is None:
        raise ValueError(f"Setup {setup_id} non trovato")
    setup = dict(setup_row)
    content_hash = _revision_content_hash(setup, controls)
    latest = conn.execute("""
        SELECT id, version_number, content_hash
        FROM setup_revisions
        WHERE setup_id=?
        ORDER BY version_number DESC
        LIMIT 1
    """, (setup_id,)).fetchone()
    if latest is not None and latest["content_hash"] == content_hash:
        return int(latest["id"]), int(latest["version_number"])

    version_number = 1 if latest is None else int(latest["version_number"]) + 1
    cursor = conn.execute("""
        INSERT INTO setup_revisions
        (revision_uid, setup_id, version_number, content_hash, name,
         description, pdf_path, pdf_sha256, sampling_class_code,
         sampling_class_description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4()), setup_id, version_number, content_hash,
        setup["name"], setup.get("description"), setup["pdf_path"],
        _file_sha256(setup["pdf_path"]), setup.get("sampling_class_code"),
        setup.get("sampling_class_description"), datetime.now().isoformat(),
    ))
    revision_id = int(cursor.lastrowid)
    for control in controls:
        conn.execute("""
            INSERT INTO revision_controls
            (setup_revision_id, source_control_id, balloon_num, balloon_x,
             balloon_y, pdf_page, control_type, criticality, label, nominal,
             tol_plus, tol_minus, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            revision_id, control.get("id"), control["balloon_num"],
            control["balloon_x"], control["balloon_y"],
            control.get("pdf_page", 0), control["control_type"],
            control.get("criticality") or "N", control.get("label"),
            control.get("nominal"), control.get("tol_plus"),
            control.get("tol_minus"), control.get("description"),
        ))
    return revision_id, version_number


# ─── MASTER DATA ────────────────────────────────────────────────────────────────

def get_all_operators() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM operators ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_operator(name: str, email: str, phone: str, notes: str,
                  operator_id: Optional[int] = None) -> int:
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        if operator_id is None:
            cursor = conn.execute("""
                INSERT INTO operators (name, email, phone, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name.strip(), email.strip(), phone.strip(), notes.strip(), now, now))
            result = cursor.lastrowid
        else:
            conn.execute("""
                UPDATE operators SET name=?, email=?, phone=?, notes=?, updated_at=?
                WHERE id=?
            """, (name.strip(), email.strip(), phone.strip(), notes.strip(), now,
                  operator_id))
            result = operator_id
        conn.commit()
        return result
    finally:
        conn.close()


def delete_operator(operator_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM operators WHERE id=?", (operator_id,))
    conn.commit()
    conn.close()


def get_all_suppliers() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM suppliers ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_supplier(name: str, vat_code: str, contact: str, email: str,
                  phone: str, notes: str,
                  supplier_id: Optional[int] = None) -> int:
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        if supplier_id is None:
            cursor = conn.execute("""
                INSERT INTO suppliers
                (name, vat_code, contact, email, phone, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (name.strip(), vat_code.strip(), contact.strip(), email.strip(),
                  phone.strip(), notes.strip(), now, now))
            result = cursor.lastrowid
        else:
            conn.execute("""
                UPDATE suppliers
                SET name=?, vat_code=?, contact=?, email=?, phone=?, notes=?, updated_at=?
                WHERE id=?
            """, (name.strip(), vat_code.strip(), contact.strip(), email.strip(),
                  phone.strip(), notes.strip(), now, supplier_id))
            result = supplier_id
        conn.commit()
        return result
    finally:
        conn.close()


def delete_supplier(supplier_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()


def get_all_sampling_classes() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sampling_classes ORDER BY code COLLATE NOCASE"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_sampling_class(
        code: str, description: str, history_validity_days: int = 730,
        extended_passes_required: int = 1,
        normal_passes_required: int = 2,
        fail_resets_extended: bool = True,
        derogation_counts_positive: bool = False,
        sampling_class_id: Optional[int] = None) -> int:
    code = code.strip()
    description = description.strip()
    if not code or not description:
        raise ValueError("Codice e descrizione della classe sono obbligatori.")
    history_validity_days = int(history_validity_days)
    extended_passes_required = int(extended_passes_required)
    normal_passes_required = int(normal_passes_required)
    if min(
            history_validity_days, extended_passes_required,
            normal_passes_required) < 1:
        raise ValueError("I parametri numerici delle regole devono essere positivi.")
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        if sampling_class_id is None:
            cursor = conn.execute(
                """INSERT INTO sampling_classes
                   (code, description, history_validity_days,
                    extended_passes_required, normal_passes_required,
                    fail_resets_extended, derogation_counts_positive,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (code, description, history_validity_days,
                 extended_passes_required, normal_passes_required,
                 int(bool(fail_resets_extended)),
                 int(bool(derogation_counts_positive)), now, now),
            )
            result = cursor.lastrowid
            conn.execute(
                """INSERT INTO sampling_plans
                   (sampling_class_id, profile, position, lot_min, lot_max,
                    critical_n, critical_ac, critical_re,
                    important_n, important_ac, important_re,
                    normal_n, normal_ac, normal_re)
                   SELECT ?, profile, position, lot_min, lot_max,
                          critical_n, critical_ac, critical_re,
                          important_n, important_ac, important_re,
                          normal_n, normal_ac, normal_re
                   FROM sampling_plan_defaults""",
                (result,),
            )
        else:
            conn.execute(
                """UPDATE sampling_classes
                   SET code=?, description=?, history_validity_days=?,
                       extended_passes_required=?, normal_passes_required=?,
                       fail_resets_extended=?, derogation_counts_positive=?,
                       updated_at=? WHERE id=?""",
                (code, description, history_validity_days,
                 extended_passes_required, normal_passes_required,
                 int(bool(fail_resets_extended)),
                 int(bool(derogation_counts_positive)), now,
                 sampling_class_id),
            )
            result = sampling_class_id
        conn.commit()
        return result
    finally:
        conn.close()


def get_sampling_class_setup_count(sampling_class_id: int) -> int:
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM setups WHERE sampling_class_id=?",
        (sampling_class_id,),
    ).fetchone()[0]
    conn.close()
    return int(count)


def get_sampling_class_setups(sampling_class_id: int) -> List[Dict]:
    """Restituisce i setup che impediscono l'eliminazione della classe."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, name, description
           FROM setups
           WHERE sampling_class_id=?
           ORDER BY name COLLATE NOCASE, id""",
        (sampling_class_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_sampling_class(sampling_class_id: int):
    conn = get_connection()
    try:
        sampling_class = conn.execute(
            "SELECT code, is_default FROM sampling_classes WHERE id=?",
            (sampling_class_id,),
        ).fetchone()
        if sampling_class is None:
            raise ValueError("La classe di campionamento non esiste.")
        if sampling_class["is_default"]:
            raise ValueError(
                "La classe di campionamento predefinita non può essere eliminata."
            )
        linked_setups = conn.execute(
            "SELECT name FROM setups WHERE sampling_class_id=? ORDER BY name COLLATE NOCASE",
            (sampling_class_id,),
        ).fetchall()
        if linked_setups:
            setup_names = ", ".join(row["name"] for row in linked_setups)
            raise ValueError(
                "La classe di campionamento è associata ai setup: " + setup_names
            )
        conn.execute(
            "DELETE FROM sampling_classes WHERE id=?", (sampling_class_id,)
        )
        conn.commit()
    finally:
        conn.close()


def get_sampling_plans(sampling_class_id: int) -> Dict[str, List[Dict]]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM sampling_plans
           WHERE sampling_class_id=? ORDER BY profile, position""",
        (sampling_class_id,),
    ).fetchall()
    conn.close()
    plans = {profile: [] for profile in SAMPLING_PLANS}
    for row in rows:
        data = dict(row)
        data.pop("sampling_class_id")
        plans[data.pop("profile")].append(data)
    return plans


def get_sampling_plan_defaults(profile: str) -> List[Dict]:
    """Legge dal DB la copia originale non modificabile di un profilo."""
    if profile not in SAMPLING_PLANS:
        raise ValueError(f"Profilo di campionamento sconosciuto: {profile}.")
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM sampling_plan_defaults
           WHERE profile=? ORDER BY position""",
        (profile,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_sampling_plan_for_quantity(
        profile: str, lot_quantity: int,
        sampling_class_id: Optional[int] = None) -> Optional[Dict]:
    """Restituisce la riga operativa che comprende la quantità del lotto."""
    if profile not in SAMPLING_PLANS:
        raise ValueError(f"Profilo di campionamento sconosciuto: {profile}.")
    if not isinstance(lot_quantity, int) or isinstance(lot_quantity, bool):
        raise ValueError("La quantità del lotto deve essere un numero intero.")
    if lot_quantity < 1:
        raise ValueError("La quantità del lotto deve essere positiva.")
    conn = get_connection()
    if sampling_class_id is None:
        default_class = conn.execute(
            "SELECT id FROM sampling_classes WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if default_class is None:
            conn.close()
            return None
        sampling_class_id = default_class["id"]
    row = conn.execute(
        """SELECT * FROM sampling_plans
           WHERE sampling_class_id=? AND profile=? AND lot_min<=?
             AND (lot_max IS NULL OR lot_max>=?)
           ORDER BY position LIMIT 1""",
        (sampling_class_id, profile, lot_quantity, lot_quantity),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_sampling_plans(sampling_class_id: int,
                        plans: Dict[str, List[Dict]]):
    """Sostituisce i tre piani di una classe in un'unica transazione."""
    validate_sampling_plans(plans)
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sampling_classes WHERE id=?", (sampling_class_id,)
        ).fetchone()
        if not exists:
            raise ValueError("La classe di campionamento selezionata non esiste.")
        conn.execute(
            "DELETE FROM sampling_plans WHERE sampling_class_id=?",
            (sampling_class_id,),
        )
        for profile in ("ESTESO", "NORMALE", "RIDOTTO"):
            for position, row in enumerate(plans[profile]):
                conn.execute(
                    """INSERT INTO sampling_plans
                       (sampling_class_id, profile, position, lot_min, lot_max,
                        critical_n, critical_ac, critical_re,
                        important_n, important_ac, important_re,
                        normal_n, normal_ac, normal_re)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sampling_class_id, profile, position,
                        *(row[column] for column in SAMPLING_PLAN_COLUMNS),
                    ),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── SETUP ───────────────────────────────────────────────────────────────────

def save_setup(name: str, description: str, pdf_path: str,
               sampling_class_id: int) -> int:
    raise RuntimeError(
        "Usa save_programming_changes() per creare setup e relativa revisione."
    )


def update_setup(setup_id: int, name: str, description: str, pdf_path: str,
                 sampling_class_id: int):
    raise RuntimeError(
        "Usa save_programming_changes() per aggiornare setup e revisione."
    )


def save_programming_changes(
        setup_id: Optional[int], name: str, description: str, pdf_path: str,
        sampling_class_id: int,
        controls: Optional[List[Dict]] = None,
        deleted_control_ids: Optional[List[int]] = None
        ) -> tuple[int, List[Dict]]:
    """Salva l'intero modello di programmazione in un'unica transazione."""
    name = name.strip()
    description = description.strip()
    if not name:
        raise ValueError("Il nome del setup è obbligatorio.")
    now = datetime.now().isoformat()
    deleted_ids = list(deleted_control_ids or [])
    conn = get_connection()
    try:
        cursor = conn.cursor()
        duplicate = cursor.execute(
            "SELECT id FROM setups WHERE name=? COLLATE NOCASE "
            "AND (? IS NULL OR id<>?) LIMIT 1",
            (name, setup_id, setup_id),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(
                f"Esiste già un setup con il nome '{name}'. "
                "I nomi dei setup devono essere univoci."
            )
        sampling_class_exists = cursor.execute(
            "SELECT 1 FROM sampling_classes WHERE id=?", (sampling_class_id,)
        ).fetchone()
        if not sampling_class_exists:
            raise ValueError("La Classe di Collaudo selezionata non esiste.")
        if setup_id is None:
            cursor.execute(
                """INSERT INTO setups
                   (name, description, pdf_path, sampling_class_id,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (name, description, pdf_path, sampling_class_id, now, now),
            )
            setup_id = cursor.lastrowid
        else:
            cursor.execute(
                """UPDATE setups
                   SET name=?, description=?, pdf_path=?, sampling_class_id=?,
                       updated_at=?
                   WHERE id=?""",
                (name, description, pdf_path, sampling_class_id, now, setup_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Setup {setup_id} non trovato")

        for control in controls or []:
            control_id = control.get("id")
            criticality = control.get("criticality", "N") or "N"
            if criticality not in {"C", "I", "N"}:
                raise ValueError(
                    f"Criticità non valida per il controllo {control_id}: "
                    f"{criticality}"
                )
            values = (
                criticality, control["label"],
                control.get("nominal"),
                control.get("tol_plus"), control.get("tol_minus"),
                control["description"],
            )
            if control_id is None or int(control_id) < 0:
                cursor.execute(
                    """INSERT INTO controls
                       (setup_id, balloon_num, balloon_x, balloon_y, pdf_page,
                        control_type, criticality, label, nominal, tol_plus,
                        tol_minus, description)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        setup_id, control["balloon_num"], control["balloon_x"],
                        control["balloon_y"], control["pdf_page"],
                        control["control_type"], *values,
                    ),
                )
            else:
                cursor.execute(
                    """UPDATE controls
                       SET balloon_num=?, balloon_x=?, balloon_y=?, pdf_page=?,
                           criticality=?, label=?, nominal=?, tol_plus=?,
                           tol_minus=?, description=?
                       WHERE id=? AND setup_id=?""",
                    (
                        control["balloon_num"], control["balloon_x"],
                        control["balloon_y"], control["pdf_page"],
                        *values, control_id, setup_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError(f"Controllo {control_id} non trovato")

        for deleted_id in deleted_ids:
            cursor.execute(
                "DELETE FROM controls WHERE id=? AND setup_id=?",
                (deleted_id, setup_id),
            )

        rows = cursor.execute(
            "SELECT * FROM controls WHERE setup_id=? ORDER BY balloon_num",
            (setup_id,),
        ).fetchall()
        saved_controls = [dict(row) for row in rows]
        _create_setup_revision(conn, setup_id, saved_controls)
        conn.commit()
        return setup_id, saved_controls
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_setup(setup_id: int):
    conn = get_connection()
    try:
        lot_count = int(conn.execute(
            "SELECT COUNT(*) FROM lots WHERE setup_id=?", (setup_id,)
        ).fetchone()[0])
        if lot_count:
            raise ValueError(
                "Il setup contiene controlli salvati e non può essere eliminato."
            )
        conn.execute("DELETE FROM setups WHERE id=?", (setup_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_setups() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, sc.code AS sampling_class_code,
                  sc.description AS sampling_class_description,
                  sc.history_validity_days,
                  sc.extended_passes_required,
                  sc.normal_passes_required,
                  sc.fail_resets_extended,
                  sc.derogation_counts_positive,
                  sr.id AS setup_revision_id,
                  sr.version_number AS setup_version_number,
                  sr.revision_uid AS setup_revision_uid
           FROM setups s
           LEFT JOIN sampling_classes sc ON sc.id=s.sampling_class_id
           LEFT JOIN setup_revisions sr ON sr.id=(
               SELECT current_sr.id FROM setup_revisions current_sr
               WHERE current_sr.setup_id=s.id
               ORDER BY current_sr.version_number DESC LIMIT 1
           )
           ORDER BY s.updated_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_setup(setup_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        """SELECT s.*, sc.code AS sampling_class_code,
                  sc.description AS sampling_class_description,
                  sc.history_validity_days,
                  sc.extended_passes_required,
                  sc.normal_passes_required,
                  sc.fail_resets_extended,
                  sc.derogation_counts_positive,
                  sr.id AS setup_revision_id,
                  sr.version_number AS setup_version_number,
                  sr.revision_uid AS setup_revision_uid
           FROM setups s
           LEFT JOIN sampling_classes sc ON sc.id=s.sampling_class_id
           LEFT JOIN setup_revisions sr ON sr.id=(
               SELECT current_sr.id FROM setup_revisions current_sr
               WHERE current_sr.setup_id=s.id
               ORDER BY current_sr.version_number DESC LIMIT 1
           )
           WHERE s.id=?""",
        (setup_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_setup_revision(revision_id: int) -> Optional[Dict]:
    """Restituisce lo snapshot immutabile di una revisione del setup."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM setup_revisions WHERE id=?", (revision_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def get_revision_controls(revision_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM revision_controls WHERE setup_revision_id=? "
        "ORDER BY balloon_num, id",
        (revision_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ─── CONTROLS ────────────────────────────────────────────────────────────────

def save_control(setup_id: int, balloon_num: int, balloon_x: float, balloon_y: float,
                 pdf_page: int, control_type: str, label: str,
                 nominal: Optional[float], tol_plus: Optional[float],
                 tol_minus: Optional[float], description: str,
                 criticality: str = "N") -> int:
    raise RuntimeError(
        "Usa save_programming_changes() per salvare controlli e revisione."
    )


def update_control(control_id: int, label: str, nominal: Optional[float],
                   tol_plus: Optional[float], tol_minus: Optional[float],
                   description: str, criticality: str = "N"):
    raise RuntimeError(
        "Usa save_programming_changes() per salvare controlli e revisione."
    )


def delete_control(control_id: int):
    raise RuntimeError(
        "Usa save_programming_changes() per eliminare controlli e revisionare."
    )


def get_controls_for_setup(setup_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM controls WHERE setup_id=? ORDER BY balloon_num",
        (setup_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_control(control_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM controls WHERE id=?", (control_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── LOTS ────────────────────────────────────────────────────────────────────

def create_lot(setup_id: int, lot_code: str, n_samples: int,
               operator: str, notes: str, lot_quantity: int = 0,
               supplier: str = "", supplier_id: Optional[int] = None,
               operator_id: Optional[int] = None,
               sampling_profile: Optional[str] = None,
               sampling_requirements: Optional[Dict] = None) -> int:
    raise RuntimeError(
        "La creazione di lotti aperti non è più supportata. Usa "
        "save_completed_inspection() al termine del controllo."
    )


def save_completed_inspection(
        setup_id: int, setup_revision_id: int, lot_code: str,
        lot_quantity: int, n_samples: int, sampling_profile: str,
        sampling_requirements: Dict, operator: str,
        operator_id: Optional[int], supplier: str,
        supplier_id: Optional[int], measurements: List[Dict],
        notes: str = "") -> int:
    """Salva atomicamente un controllo completo e il suo snapshot storico."""
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        revision = conn.execute(
            "SELECT * FROM setup_revisions WHERE id=? AND setup_id=?",
            (setup_revision_id, setup_id),
        ).fetchone()
        if revision is None:
            raise ValueError("La revisione del setup non è disponibile.")
        controls = [dict(row) for row in conn.execute(
            "SELECT * FROM revision_controls WHERE setup_revision_id=? "
            "ORDER BY balloon_num, id",
            (setup_revision_id,),
        ).fetchall()]
        if not controls:
            raise ValueError("La revisione del setup non contiene controlli.")

        def values(criticality: str) -> tuple[int, int, int]:
            requirement = sampling_requirements.get(criticality)
            if not requirement:
                raise ValueError(
                    f"Requisiti di campionamento {criticality} mancanti."
                )
            sample_n = int(requirement["n"])
            acceptance = int(requirement["ac"])
            rejection = int(requirement["re"])
            if not (sample_n >= 1 and 0 <= acceptance < rejection <= sample_n):
                raise ValueError(
                    f"Piano {criticality} non valido: deve rispettare "
                    "n ≥ 1 e 0 ≤ Ac < Re ≤ n."
                )
            return sample_n, acceptance, rejection

        critical_values = values("C")
        important_values = values("I")
        normal_values = values("N")
        sample_counts = {
            "C": critical_values[0],
            "I": important_values[0],
            "N": normal_values[0],
        }
        expected_measurement_keys = {
            (control["id"], sample_num)
            for control in controls
            for sample_num in range(
                1,
                sample_counts[control.get("criticality") or "N"] + 1,
            )
        }
        cursor = conn.execute("""
            INSERT INTO lots
            (setup_id, setup_revision_id, lot_code, lot_quantity, n_samples,
             critical_n, critical_ac, critical_re,
             important_n, important_ac, important_re,
             normal_n, normal_ac, normal_re, sampling_profile,
             operator, operator_id, supplier, supplier_id, notes,
             created_at, closed, cancelled, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, 1, 0, ?)
        """, (
            setup_id, setup_revision_id, lot_code.strip(), int(lot_quantity),
            int(n_samples), *critical_values, *important_values, *normal_values,
            sampling_profile, operator.strip(), operator_id, supplier.strip(),
            supplier_id, notes.strip(), now, now,
        ))
        lot_id = int(cursor.lastrowid)
        controls_by_id = {control["id"]: control for control in controls}
        seen = set()
        stored_measurements = []
        for measurement in measurements:
            control_id = int(measurement["control_id"])
            sample_num = int(measurement["sample_num"])
            key = (control_id, sample_num)
            if control_id not in controls_by_id:
                raise ValueError(
                    "Una misura non appartiene alla revisione selezionata."
                )
            if key not in expected_measurement_keys:
                raise ValueError(
                    "Una misura contiene una coppia controllo/campione "
                    "non prevista dal piano di campionamento."
                )
            if key in seen:
                raise ValueError("Sono presenti misure duplicate nel controllo.")
            seen.add(key)
            control = controls_by_id[control_id]
            value_num = measurement.get("value_num")
            value_bool = measurement.get("value_bool")
            if control["control_type"] == "dimensional":
                if (type(value_num) not in (int, float)
                        or not math.isfinite(value_num) or value_bool is not None):
                    raise ValueError("La misura dimensionale deve essere un numero finito.")
                pass_fail = (
                    control["nominal"] - abs(control["tol_minus"])
                    <= value_num <= control["nominal"] + abs(control["tol_plus"])
                )
            elif control["control_type"] == "yesno":
                if (type(value_bool) not in (bool, int)
                        or value_bool not in (0, 1) or value_num is not None):
                    raise ValueError("La misura Sì/No deve contenere una risposta booleana.")
                pass_fail = bool(value_bool)
            else:
                raise ValueError("Tipo di controllo non riconosciuto.")
            for field in ("pass_fail", "accepted_in_derogation"):
                flag = measurement.get(field, False)
                if type(flag) not in (bool, int) or flag not in (0, 1):
                    raise ValueError(f"Il campo {field} deve essere booleano.")
            if "pass_fail" not in measurement or pass_fail != measurement["pass_fail"]:
                raise ValueError("Esito incompatibile con la misura e la revisione del controllo.")
            derogated = bool(measurement.get("accepted_in_derogation", False))
            if pass_fail and derogated:
                raise ValueError("Una misura PASS non può essere derogata.")
            if derogated:
                for field in ("derogation_reason", "derogation_authorized_by",
                              "derogation_accepted_by", "derogation_at"):
                    value = measurement.get(field)
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(f"Dati di deroga incompleti: {field}.")
                try:
                    datetime.fromisoformat(measurement["derogation_at"])
                except ValueError as exc:
                    raise ValueError("Data della deroga non valida.") from exc
            recorded_at = measurement.get("recorded_at") or now
            conn.execute("""
                INSERT INTO measurements
                (lot_id, control_id, sample_num, value_num, value_bool,
                 pass_fail, accepted_in_derogation, derogation_reason,
                 derogation_authorized_by, derogation_accepted_by,
                 derogation_at, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lot_id, control_id, sample_num, measurement.get("value_num"),
                (int(measurement["value_bool"])
                 if measurement.get("value_bool") is not None else None),
                int(pass_fail), int(derogated),
                measurement.get("derogation_reason"),
                measurement.get("derogation_authorized_by"),
                measurement.get("derogation_accepted_by"),
                measurement.get("derogation_at"), recorded_at,
            ))
            stored = dict(measurement)
            stored.update({
                "lot_id": lot_id,
                "control_id": control_id,
                "sample_num": sample_num,
                "pass_fail": int(pass_fail),
                "accepted_in_derogation": int(derogated),
                "recorded_at": recorded_at,
            })
            stored_measurements.append(stored)

        if seen != expected_measurement_keys:
            missing_count = len(expected_measurement_keys - seen)
            raise ValueError(
                "Il controllo non contiene tutte le misure previste: "
                f"mancano {missing_count} coppie controllo/campione."
            )

        lot = dict(conn.execute(
            "SELECT * FROM lots WHERE id=?", (lot_id,)
        ).fetchone())
        evaluation = evaluate_sampling_lot(lot, controls, stored_measurements)
        if not evaluation["complete"]:
            raise ValueError(
                "Il controllo non contiene tutte le misure previste "
                f"({evaluation['completed_total']}/{evaluation['expected_total']})."
            )
        conn.execute(
            "UPDATE lots SET final_status=? WHERE id=?",
            (evaluation["status"], lot_id),
        )
        conn.commit()
        return lot_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def close_lot(lot_id: int):
    raise RuntimeError("I controlli vengono salvati direttamente come conclusi.")


def cancel_lot(lot_id: int):
    raise RuntimeError("Le bozze interrotte non vengono salvate nel database.")


def get_lots_for_setup(setup_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM lots WHERE setup_id=? ORDER BY created_at DESC",
        (setup_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lot(lot_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM lots WHERE id=?", (lot_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_lot_history_for_setup(setup_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            l.*,
            sr.version_number AS setup_version_number,
            COUNT(m.id) AS measurement_count,
            COALESCE(SUM(CASE WHEN m.pass_fail = 0 THEN 1 ELSE 0 END), 0) AS failed_count,
            COALESCE(SUM(CASE WHEN m.pass_fail = 0 AND m.accepted_in_derogation = 1
                              THEN 1 ELSE 0 END), 0) AS derogated_count,
            COALESCE(SUM(CASE WHEN m.pass_fail = 0 AND m.accepted_in_derogation = 0
                              THEN 1 ELSE 0 END), 0) AS open_failed_count
        FROM lots l
        JOIN setup_revisions sr ON sr.id=l.setup_revision_id
        LEFT JOIN measurements m ON m.lot_id = l.id
        WHERE l.setup_id = ? AND l.closed=1 AND l.cancelled=0
        GROUP BY l.id
        ORDER BY l.created_at DESC
    """, (setup_id,)).fetchall()
    lot_ids = [row["id"] for row in rows]
    measurements_by_lot = {lot_id: [] for lot_id in lot_ids}
    if lot_ids:
        placeholders = ",".join("?" for _ in lot_ids)
        measurement_rows = conn.execute(f"""
            SELECT * FROM measurements
            WHERE lot_id IN ({placeholders})
            ORDER BY lot_id, sample_num, control_id
        """, lot_ids).fetchall()
        for measurement in measurement_rows:
            measurements_by_lot[measurement["lot_id"]].append(dict(measurement))
    revision_ids = {
        int(row["setup_revision_id"])
        for row in rows if row["setup_revision_id"] is not None
    }
    controls_by_revision = {revision_id: [] for revision_id in revision_ids}
    if revision_ids:
        placeholders = ",".join("?" for _ in revision_ids)
        control_rows = conn.execute(f"""
            SELECT * FROM revision_controls
            WHERE setup_revision_id IN ({placeholders})
            ORDER BY setup_revision_id, balloon_num, id
        """, tuple(sorted(revision_ids))).fetchall()
        for control in control_rows:
            controls_by_revision[control["setup_revision_id"]].append(dict(control))
    conn.close()

    history = []
    for row in rows:
        lot = dict(row)
        controls = controls_by_revision.get(lot.get("setup_revision_id"), [])
        evaluation = evaluate_sampling_lot(
            lot, controls, measurements_by_lot.get(lot["id"], [])
        )

        if lot.get("cancelled"):
            state = "ANNULLATO"
        elif lot.get("closed"):
            state = "CHIUSO"
        else:
            state = "APERTO"

        result = evaluation["status"]
        if result == STATUS_EMPTY:
            result = "—"

        lot["control_count"] = len(controls)
        lot["expected_count"] = evaluation["expected_total"]
        lot["result"] = result
        lot["state"] = state
        lot["is_complete"] = evaluation["complete"]
        lot["sampling_evaluation"] = evaluation
        history.append(lot)
    return history


def get_setup_quality_statistics(setup_id: int) -> Dict:
    """Aggrega lotti, campioni e misure di qualita per uno specifico setup."""
    conn = get_connection()
    lots = [dict(row) for row in conn.execute("""
        SELECT * FROM lots
        WHERE setup_id=? AND closed=1 AND cancelled=0
        ORDER BY created_at, id
    """, (setup_id,)).fetchall()]

    lot_ids = [lot["id"] for lot in lots]
    measurements = []
    if lot_ids:
        placeholders = ",".join("?" for _ in lot_ids)
        measurements = [dict(row) for row in conn.execute(f"""
            SELECT * FROM measurements
            WHERE lot_id IN ({placeholders})
            ORDER BY lot_id, sample_num, control_id
        """, lot_ids).fetchall()]
    revision_ids = sorted({
        int(lot["setup_revision_id"])
        for lot in lots if lot.get("setup_revision_id") is not None
    })
    controls_by_revision = {revision_id: [] for revision_id in revision_ids}
    if revision_ids:
        placeholders = ",".join("?" for _ in revision_ids)
        for row in conn.execute(f"""
            SELECT * FROM revision_controls
            WHERE setup_revision_id IN ({placeholders})
            ORDER BY setup_revision_id, balloon_num, id
        """, revision_ids).fetchall():
            controls_by_revision[row["setup_revision_id"]].append(dict(row))
    conn.close()

    controls = [
        control
        for revision_controls in controls_by_revision.values()
        for control in revision_controls
    ]
    control_ids = {control["id"] for control in controls}
    control_by_id = {control["id"]: control for control in controls}
    measurements_by_lot: Dict[int, List[Dict]] = {
        lot_id: [] for lot_id in lot_ids
    }
    measurements_by_control: Dict[int, List[Dict]] = {
        control_id: [] for control_id in control_ids
    }
    for measurement in measurements:
        measurements_by_lot[measurement["lot_id"]].append(measurement)
        if measurement["control_id"] in measurements_by_control:
            measurements_by_control[measurement["control_id"]].append(measurement)

    by_lot = {}
    inspected_samples = conforming_samples = failed_samples = derogated_samples = 0
    conforming_lots = 0
    complete_lots = 0

    for lot in lots:
        lot_controls = controls_by_revision.get(lot.get("setup_revision_id"), [])
        samples: Dict[int, List[Dict]] = {}
        for measurement in measurements_by_lot[lot["id"]]:
            samples.setdefault(int(measurement["sample_num"]), []).append(measurement)

        lot_pass = lot_fail = lot_derogated = 0
        for sample_num in range(1, int(lot.get("n_samples") or 0) + 1):
            required_controls = get_required_controls_for_sample(
                lot, lot_controls, sample_num
            )
            required_control_ids = {
                control["id"] for control in required_controls
            }
            sample_measurements = [
                measurement for measurement in samples.get(sample_num, [])
                if measurement["control_id"] in required_control_ids
            ]
            measured_controls = {
                measurement["control_id"] for measurement in sample_measurements
            }
            if (not required_control_ids
                    or not required_control_ids.issubset(measured_controls)):
                continue

            inspected_samples += 1
            open_fail = any(
                not measurement["pass_fail"]
                and not measurement.get("accepted_in_derogation")
                for measurement in sample_measurements
                if measurement["control_id"] in required_control_ids
            )
            has_derogation = any(
                not measurement["pass_fail"]
                and measurement.get("accepted_in_derogation")
                for measurement in sample_measurements
                if measurement["control_id"] in required_control_ids
            )
            if open_fail:
                lot_fail += 1
                failed_samples += 1
            elif has_derogation:
                lot_derogated += 1
                derogated_samples += 1
            else:
                lot_pass += 1
                conforming_samples += 1

        evaluation = evaluate_sampling_lot(
            lot, lot_controls, measurements_by_lot[lot["id"]]
        )
        completed_samples = lot_pass + lot_fail + lot_derogated
        if evaluation["complete"]:
            complete_lots += 1
            if evaluation["status"] == STATUS_PASS:
                conforming_lots += 1

        by_lot[lot["id"]] = {
            "pass": lot_pass,
            "fail": lot_fail,
            "derogated": lot_derogated,
            "inspected": completed_samples,
            "conformity_percent": (
                lot_pass / completed_samples * 100 if completed_samples else 0.0
            ),
            "result": evaluation["status"],
        }

    fail_by_control = []
    dimensional_controls = []
    for control_id, control_measurements in measurements_by_control.items():
        control = control_by_id[control_id]
        fail_count = sum(
            1 for measurement in control_measurements
            if not measurement["pass_fail"]
        )
        if fail_count:
            fail_by_control.append({
                "control_id": control_id,
                "balloon_num": control["balloon_num"],
                "label": control.get("label") or "(senza descrizione)",
                "fail_count": fail_count,
            })

        if control["control_type"] != "dimensional":
            continue
        values = [
            float(measurement["value_num"])
            for measurement in control_measurements
            if measurement.get("value_num") is not None
        ]
        if not values:
            continue
        average = sum(values) / len(values)
        variance = sum((value - average) ** 2 for value in values) / len(values)
        dimensional_controls.append({
            "control_id": control_id,
            "balloon_num": control["balloon_num"],
            "label": control.get("label") or "(senza descrizione)",
            "nominal": control.get("nominal"),
            "count": len(values),
            "average": average,
            "minimum": min(values),
            "maximum": max(values),
            "std_dev": math.sqrt(variance),
            "fail_count": fail_count,
            "fail_percent": fail_count / len(values) * 100,
        })

    fail_by_control.sort(key=lambda item: (-item["fail_count"], item["balloon_num"]))
    dimensional_controls.sort(key=lambda item: item["balloon_num"])
    total_lot_quantity = sum(int(lot.get("lot_quantity") or 0) for lot in lots)

    return {
        "totals": {
            "lots": len(lots),
            "complete_lots": complete_lots,
            "lot_quantity": total_lot_quantity,
            "inspected_samples": inspected_samples,
            "conforming_samples": conforming_samples,
            "failed_samples": failed_samples,
            "derogated_samples": derogated_samples,
            "sample_conformity_percent": (
                conforming_samples / inspected_samples * 100
                if inspected_samples else 0.0
            ),
            "lot_conformity_percent": (
                conforming_lots / complete_lots * 100 if complete_lots else 0.0
            ),
        },
        "by_lot": by_lot,
        "fail_by_control": fail_by_control,
        "dimensional_controls": dimensional_controls,
    }


def get_recent_lot_history(limit: int = 6) -> List[Dict]:
    """Restituisce gli ultimi lotti di tutti i setup per il riepilogo launcher."""
    limit = max(1, int(limit))
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            l.*,
            COALESCE(sr.name, s.name) AS setup_name,
            COALESCE(sr.description, s.description) AS setup_description,
            (SELECT COUNT(*) FROM revision_controls rc
             WHERE rc.setup_revision_id = l.setup_revision_id)
                AS control_count,
            COUNT(m.id) AS measurement_count,
            COALESCE(SUM(CASE WHEN m.pass_fail = 0 AND m.accepted_in_derogation = 1
                              THEN 1 ELSE 0 END), 0) AS derogated_count,
            COALESCE(SUM(CASE WHEN m.pass_fail = 0 AND m.accepted_in_derogation = 0
                              THEN 1 ELSE 0 END), 0) AS open_failed_count
        FROM lots l
        JOIN setups s ON s.id = l.setup_id
        LEFT JOIN setup_revisions sr ON sr.id=l.setup_revision_id
        LEFT JOIN measurements m ON m.lot_id = l.id
        WHERE l.closed=1 AND l.cancelled=0
        GROUP BY l.id
        ORDER BY l.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    recent = []
    for row in rows:
        lot = dict(row)
        summary = get_lot_summary(lot["id"])
        evaluation = summary["sampling_evaluation"]
        if lot.get("cancelled"):
            result = "ANNULLATO"
        elif evaluation["status"] == STATUS_EMPTY:
            result = "—"
        else:
            result = evaluation["status"]
        lot["expected_count"] = evaluation["expected_total"]
        lot["result"] = result
        recent.append(lot)
    return recent


def get_supplier_quality_statistics(start_date: str, end_date: str) -> Dict:
    """Aggrega per fornitore gli esiti dei singoli pezzi controllati."""
    conn = get_connection()
    lot_rows = conn.execute("""
        SELECT l.*, COALESCE(sr.name, s.name) AS setup_name,
               sp.name AS supplier_current_name
        FROM lots l
        JOIN setups s ON s.id = l.setup_id
        LEFT JOIN setup_revisions sr ON sr.id=l.setup_revision_id
        LEFT JOIN suppliers sp ON sp.id = l.supplier_id
        WHERE l.closed = 1
          AND l.cancelled = 0
          AND SUBSTR(l.created_at, 1, 10) BETWEEN ? AND ?
        ORDER BY l.created_at, l.id
    """, (start_date, end_date)).fetchall()

    lot_ids = [row["id"] for row in lot_rows]
    measurements_by_lot: Dict[int, List[Dict]] = {lot_id: [] for lot_id in lot_ids}
    if lot_ids:
        placeholders = ",".join("?" for _ in lot_ids)
        measurement_rows = conn.execute(f"""
            SELECT lot_id, control_id, sample_num, pass_fail,
                   accepted_in_derogation
            FROM measurements
            WHERE lot_id IN ({placeholders})
            ORDER BY lot_id, sample_num, control_id
        """, lot_ids).fetchall()
        for row in measurement_rows:
            measurements_by_lot[row["lot_id"]].append(dict(row))
    revision_ids = sorted({
        row["setup_revision_id"] for row in lot_rows
        if row["setup_revision_id"] is not None
    })
    controls_by_revision: Dict[int, List[Dict]] = {
        revision_id: [] for revision_id in revision_ids
    }
    if revision_ids:
        placeholders = ",".join("?" for _ in revision_ids)
        control_rows = conn.execute(f"""
            SELECT * FROM revision_controls
            WHERE setup_revision_id IN ({placeholders})
            ORDER BY setup_revision_id, balloon_num
        """, revision_ids).fetchall()
        for row in control_rows:
            controls_by_revision[row["setup_revision_id"]].append(dict(row))
    conn.close()

    grouped: Dict[str, Dict] = {}
    excluded_incomplete = 0
    for raw_lot in lot_rows:
        lot = dict(raw_lot)
        controls = controls_by_revision.get(lot.get("setup_revision_id"), [])
        lot_measurements = measurements_by_lot.get(lot["id"], [])
        evaluation = evaluate_sampling_lot(lot, controls, lot_measurements)
        if not evaluation["complete"]:
            excluded_incomplete += 1
            continue

        by_sample: Dict[int, List[Dict]] = {}
        for measurement in lot_measurements:
            by_sample.setdefault(measurement["sample_num"], []).append(measurement)

        n_samples = int(lot.get("n_samples") or 0)

        supplier_name = (
            lot.get("supplier_current_name")
            or lot.get("supplier")
            or "Fornitore non specificato"
        )
        supplier_id = lot.get("supplier_id")
        key = (
            f"id:{supplier_id}" if supplier_id is not None
            else f"name:{supplier_name.casefold()}"
        )
        stats = grouped.setdefault(key, {
            "supplier_id": supplier_id,
            "supplier": supplier_name,
            "lots": 0,
            "lot_pass": 0,
            "lot_derogated": 0,
            "lot_fail": 0,
            "pieces": 0,
            "passed": 0,
            "derogated": 0,
            "failed": 0,
            "details": [],
            "unspecified": supplier_name == "Fornitore non specificato",
        })

        lot_counts = {"passed": 0, "derogated": 0, "failed": 0}
        for sample_num in range(1, n_samples + 1):
            required_ids = {
                control["id"]
                for control in get_required_controls_for_sample(
                    lot, controls, sample_num
                )
            }
            sample = [
                measurement for measurement in by_sample.get(sample_num, [])
                if measurement["control_id"] in required_ids
            ]
            if any(
                    not bool(m["pass_fail"])
                    and not bool(m["accepted_in_derogation"])
                    for m in sample):
                result = "failed"
            elif any(
                    not bool(m["pass_fail"])
                    and bool(m["accepted_in_derogation"])
                    for m in sample):
                result = "derogated"
            else:
                result = "passed"
            lot_counts[result] += 1

        if evaluation["status"] == STATUS_FAIL:
            lot_result = "FAIL"
            stats["lot_fail"] += 1
        elif evaluation["status"] == STATUS_DEROGATION:
            lot_result = "DEROGA"
            stats["lot_derogated"] += 1
        else:
            lot_result = "PASS"
            stats["lot_pass"] += 1

        stats["lots"] += 1
        stats["pieces"] += n_samples
        for result in ("passed", "derogated", "failed"):
            stats[result] += lot_counts[result]
        stats["details"].append({
            "date": str(lot.get("created_at") or "")[:10],
            "setup": lot.get("setup_name") or "—",
            "lot_code": lot.get("lot_code") or "—",
            "pieces": n_samples,
            "passed": lot_counts["passed"],
            "derogated": lot_counts["derogated"],
            "failed": lot_counts["failed"],
            "result": lot_result,
        })

    suppliers = list(grouped.values())
    for stats in suppliers:
        pieces = stats["pieces"] or 1
        stats["pass_rate"] = stats["passed"] / pieces * 100
        stats["derogation_rate"] = stats["derogated"] / pieces * 100
        stats["fail_rate"] = stats["failed"] / pieces * 100
        stats["limited_sample"] = stats["pieces"] < 30
    suppliers.sort(key=lambda item: (
        item["unspecified"], item["fail_rate"],
        item["derogation_rate"], -item["pieces"], item["supplier"].casefold()
    ))

    totals = {
        "suppliers": len([s for s in suppliers if not s["unspecified"]]),
        "lots": sum(s["lots"] for s in suppliers),
        "pieces": sum(s["pieces"] for s in suppliers),
        "passed": sum(s["passed"] for s in suppliers),
        "derogated": sum(s["derogated"] for s in suppliers),
        "failed": sum(s["failed"] for s in suppliers),
    }
    pieces = totals["pieces"] or 1
    totals["pass_rate"] = totals["passed"] / pieces * 100
    totals["derogation_rate"] = totals["derogated"] / pieces * 100
    totals["fail_rate"] = totals["failed"] / pieces * 100
    return {
        "start_date": start_date,
        "end_date": end_date,
        "suppliers": suppliers,
        "totals": totals,
        "excluded_incomplete": excluded_incomplete,
    }


def get_lot_report_data(lot_id: int) -> Optional[Dict]:
    lot = get_lot(lot_id)
    if not lot:
        return None

    setup = get_setup_revision(lot.get("setup_revision_id"))
    if not setup:
        return None

    return {
        "setup": setup,
        "controls": get_revision_controls(lot["setup_revision_id"]),
        "summary": get_lot_summary(lot_id),
    }


# ─── MEASUREMENTS ────────────────────────────────────────────────────────────

def save_measurement(lot_id: int, control_id: int, sample_num: int,
                     value_num: Optional[float], value_bool: Optional[bool],
                     pass_fail: bool) -> int:
    raise RuntimeError(
        "Le misure vengono salvate insieme al controllo completo."
    )


def get_measurements_for_lot(lot_id: int) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM measurements WHERE lot_id=? ORDER BY sample_num, control_id",
        (lot_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def accept_measurement_in_derogation(
        lot_id: int, control_id: int, sample_num: int,
        reason: str, authorized_by: str, accepted_by: str) -> bool:
    raise RuntimeError("Le deroghe sono definitive al salvataggio del controllo.")


def accept_measurements_in_derogation(
        lot_id: int, measurements: List[tuple[int, int]],
        reason: str, authorized_by: str, accepted_by: str) -> bool:
    raise RuntimeError("Le deroghe sono definitive al salvataggio del controllo.")


def revoke_measurement_derogation(
        lot_id: int, control_id: int, sample_num: int) -> bool:
    raise RuntimeError("Le deroghe sono definitive al salvataggio del controllo.")


def get_lot_summary(lot_id: int) -> Dict:
    """Restituisce statistiche riassuntive del lotto."""
    conn = get_connection()
    lot_row = conn.execute("SELECT * FROM lots WHERE id=?", (lot_id,)).fetchone()
    if lot_row is None:
        conn.close()
        raise ValueError(f"Lotto {lot_id} non trovato")
    lot = dict(lot_row)
    controls = [dict(row) for row in conn.execute(
        "SELECT * FROM revision_controls WHERE setup_revision_id=? "
        "ORDER BY balloon_num, id",
        (lot["setup_revision_id"],),
    ).fetchall()]
    measurements = [dict(r) for r in conn.execute(
        "SELECT * FROM measurements WHERE lot_id=?", (lot_id,)
    ).fetchall()]
    conn.close()

    total = len(measurements)
    passed = sum(1 for m in measurements if m["pass_fail"] == 1)
    failed = total - passed
    derogated = sum(
        1 for m in measurements
        if m["pass_fail"] == 0 and m["accepted_in_derogation"] == 1
    )
    open_failed = failed - derogated
    sampling_evaluation = evaluate_sampling_lot(lot, controls, measurements)
    lot_pass = sampling_evaluation["status"] in {
        STATUS_PASS, STATUS_DEROGATION,
    }

    return {
        "lot": lot,
        "controls": controls,
        "measurements": measurements,
        "total": total,
        "passed": passed,
        "failed": failed,
        "derogated": derogated,
        "open_failed": open_failed,
        "lot_pass": lot_pass,
        "status": sampling_evaluation["status"],
        "status_message": sampling_evaluation["message"],
        "expected_total": sampling_evaluation["expected_total"],
        "sampling_evaluation": sampling_evaluation,
    }
