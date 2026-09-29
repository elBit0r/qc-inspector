"""Schema SQLite e migrazioni versionate di QC Inspector.

Questo modulo e l'unico punto autorizzato a creare o modificare lo schema.
La versione e conservata in ``PRAGMA user_version``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.app_config import get_db_path
from ..core.sampling_plans import (
    SAMPLING_PLAN_COLUMNS,
    SAMPLING_PLANS,
    get_default_sampling_plan,
)


CURRENT_SCHEMA_VERSION = 3

LEGACY_PRODUCTION_COLUMNS = {
    "setups": {
        "id", "name", "description", "pdf_path", "created_at", "updated_at",
    },
    "controls": {
        "id", "setup_id", "balloon_num", "balloon_x", "balloon_y",
        "pdf_page", "control_type", "label", "nominal", "tol_plus",
        "tol_minus", "description",
    },
    "lots": {
        "id", "setup_id", "lot_code", "n_samples", "operator", "notes",
        "created_at", "closed", "cancelled", "lot_quantity", "supplier",
        "supplier_id", "operator_id",
    },
    "measurements": {
        "id", "lot_id", "control_id", "sample_num", "value_num",
        "value_bool", "pass_fail", "recorded_at", "accepted_in_derogation",
        "derogation_reason", "derogation_authorized_by",
        "derogation_accepted_by", "derogation_at",
    },
    "operators": {
        "id", "name", "email", "phone", "notes", "created_at", "updated_at",
    },
    "suppliers": {
        "id", "name", "vat_code", "contact", "email", "phone", "notes",
        "created_at", "updated_at",
    },
}

V1_COLUMNS = {
    **LEGACY_PRODUCTION_COLUMNS,
    "setups": LEGACY_PRODUCTION_COLUMNS["setups"] | {"sampling_class_id"},
    "controls": LEGACY_PRODUCTION_COLUMNS["controls"] | {"criticality"},
    "lots": LEGACY_PRODUCTION_COLUMNS["lots"] | {
        "sampling_profile",
        "critical_n", "critical_ac", "critical_re",
        "important_n", "important_ac", "important_re",
        "normal_n", "normal_ac", "normal_re",
    },
    "sampling_classes": {
        "id", "code", "description", "is_default", "created_at", "updated_at",
    },
    "sampling_plans": {
        "sampling_class_id", "profile", "position", *SAMPLING_PLAN_COLUMNS,
    },
    "sampling_plan_defaults": {"profile", "position", *SAMPLING_PLAN_COLUMNS},
}

V2_COLUMNS = {
    **V1_COLUMNS,
    "sampling_classes": V1_COLUMNS["sampling_classes"] | {
        "history_validity_days",
        "extended_passes_required",
        "normal_passes_required",
        "fail_resets_extended",
        "derogation_counts_positive",
    },
}

V3_COLUMNS = {
    **V2_COLUMNS,
    "lots": V2_COLUMNS["lots"] | {
        "setup_revision_id", "final_status", "saved_at",
    },
    "setup_revisions": {
        "id", "revision_uid", "setup_id", "version_number", "content_hash",
        "name", "description", "pdf_path", "pdf_sha256",
        "sampling_class_code", "sampling_class_description", "created_at",
    },
    "revision_controls": {
        "id", "setup_revision_id", "source_control_id", "balloon_num",
        "balloon_x", "balloon_y", "pdf_page", "control_type",
        "criticality", "label", "nominal", "tol_plus", "tol_minus",
        "description",
    },
}

SCHEMA_V1_STATEMENTS = (
    """
    CREATE TABLE sampling_classes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT NOT NULL COLLATE NOCASE UNIQUE,
        description TEXT NOT NULL,
        is_default  INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0, 1)),
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE operators (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL COLLATE NOCASE UNIQUE,
        email       TEXT,
        phone       TEXT,
        notes       TEXT,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE suppliers (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL COLLATE NOCASE UNIQUE,
        vat_code    TEXT,
        contact     TEXT,
        email       TEXT,
        phone       TEXT,
        notes       TEXT,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE setups (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        name                TEXT NOT NULL,
        description         TEXT,
        pdf_path            TEXT NOT NULL,
        sampling_class_id   INTEGER NOT NULL
                            REFERENCES sampling_classes(id),
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE controls (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        setup_id      INTEGER NOT NULL REFERENCES setups(id) ON DELETE CASCADE,
        balloon_num   INTEGER NOT NULL,
        balloon_x     REAL NOT NULL,
        balloon_y     REAL NOT NULL,
        pdf_page      INTEGER NOT NULL DEFAULT 0,
        control_type  TEXT NOT NULL
                      CHECK(control_type IN ('dimensional', 'yesno')),
        criticality   TEXT NOT NULL DEFAULT 'N'
                      CHECK(criticality IN ('C', 'I', 'N')),
        label         TEXT,
        nominal       REAL,
        tol_plus      REAL,
        tol_minus     REAL,
        description   TEXT
    )
    """,
    """
    CREATE TABLE lots (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        setup_id      INTEGER NOT NULL REFERENCES setups(id) ON DELETE CASCADE,
        lot_code      TEXT NOT NULL,
        lot_quantity  INTEGER NOT NULL DEFAULT 0 CHECK(lot_quantity >= 0),
        n_samples     INTEGER NOT NULL DEFAULT 1 CHECK(n_samples >= 1),
        critical_n    INTEGER,
        critical_ac   INTEGER,
        critical_re   INTEGER,
        important_n   INTEGER,
        important_ac  INTEGER,
        important_re  INTEGER,
        normal_n      INTEGER,
        normal_ac     INTEGER,
        normal_re     INTEGER,
        sampling_profile TEXT
                         CHECK(sampling_profile IN ('ESTESO', 'NORMALE', 'RIDOTTO')
                               OR sampling_profile IS NULL),
        operator      TEXT,
        operator_id   INTEGER REFERENCES operators(id) ON DELETE SET NULL,
        supplier      TEXT,
        supplier_id   INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
        notes         TEXT,
        created_at    TEXT NOT NULL,
        closed        INTEGER NOT NULL DEFAULT 0 CHECK(closed IN (0, 1)),
        cancelled     INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0, 1)),
        CHECK(
            (critical_n IS NULL AND critical_ac IS NULL AND critical_re IS NULL)
            OR (critical_n >= 1 AND critical_ac >= 0
                AND critical_ac < critical_re AND critical_re <= critical_n)
        ),
        CHECK(
            (important_n IS NULL AND important_ac IS NULL AND important_re IS NULL)
            OR (important_n >= 1 AND important_ac >= 0
                AND important_ac < important_re AND important_re <= important_n)
        ),
        CHECK(
            (normal_n IS NULL AND normal_ac IS NULL AND normal_re IS NULL)
            OR (normal_n >= 1 AND normal_ac >= 0
                AND normal_ac < normal_re AND normal_re <= normal_n)
        )
    )
    """,
    """
    CREATE TABLE measurements (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        lot_id        INTEGER NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
        control_id    INTEGER NOT NULL REFERENCES controls(id) ON DELETE CASCADE,
        sample_num    INTEGER NOT NULL CHECK(sample_num >= 1),
        value_num     REAL,
        value_bool    INTEGER CHECK(value_bool IN (0, 1) OR value_bool IS NULL),
        pass_fail     INTEGER NOT NULL DEFAULT 0 CHECK(pass_fail IN (0, 1)),
        accepted_in_derogation INTEGER NOT NULL DEFAULT 0
                               CHECK(accepted_in_derogation IN (0, 1)),
        derogation_reason TEXT,
        derogation_authorized_by TEXT,
        derogation_accepted_by TEXT,
        derogation_at TEXT,
        recorded_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE sampling_plan_defaults (
        profile       TEXT NOT NULL
                      CHECK(profile IN ('ESTESO', 'NORMALE', 'RIDOTTO')),
        position      INTEGER NOT NULL CHECK(position >= 0),
        lot_min       INTEGER NOT NULL CHECK(lot_min >= 1),
        lot_max       INTEGER CHECK(lot_max IS NULL OR lot_max >= lot_min),
        critical_n    INTEGER NOT NULL CHECK(critical_n >= 1),
        critical_ac   INTEGER NOT NULL CHECK(critical_ac >= 0),
        critical_re   INTEGER NOT NULL
                      CHECK(critical_re > critical_ac AND critical_re <= critical_n),
        important_n   INTEGER NOT NULL CHECK(important_n >= 1),
        important_ac  INTEGER NOT NULL CHECK(important_ac >= 0),
        important_re  INTEGER NOT NULL
                      CHECK(important_re > important_ac AND important_re <= important_n),
        normal_n      INTEGER NOT NULL CHECK(normal_n >= 1),
        normal_ac     INTEGER NOT NULL CHECK(normal_ac >= 0),
        normal_re     INTEGER NOT NULL
                      CHECK(normal_re > normal_ac AND normal_re <= normal_n),
        PRIMARY KEY (profile, position)
    )
    """,
    """
    CREATE TABLE sampling_plans (
        sampling_class_id INTEGER NOT NULL
                          REFERENCES sampling_classes(id) ON DELETE CASCADE,
        profile       TEXT NOT NULL
                      CHECK(profile IN ('ESTESO', 'NORMALE', 'RIDOTTO')),
        position      INTEGER NOT NULL CHECK(position >= 0),
        lot_min       INTEGER NOT NULL CHECK(lot_min >= 1),
        lot_max       INTEGER CHECK(lot_max IS NULL OR lot_max >= lot_min),
        critical_n    INTEGER NOT NULL CHECK(critical_n >= 1),
        critical_ac   INTEGER NOT NULL CHECK(critical_ac >= 0),
        critical_re   INTEGER NOT NULL
                      CHECK(critical_re > critical_ac AND critical_re <= critical_n),
        important_n   INTEGER NOT NULL CHECK(important_n >= 1),
        important_ac  INTEGER NOT NULL CHECK(important_ac >= 0),
        important_re  INTEGER NOT NULL
                      CHECK(important_re > important_ac AND important_re <= important_n),
        normal_n      INTEGER NOT NULL CHECK(normal_n >= 1),
        normal_ac     INTEGER NOT NULL CHECK(normal_ac >= 0),
        normal_re     INTEGER NOT NULL
                      CHECK(normal_re > normal_ac AND normal_re <= normal_n),
        PRIMARY KEY (sampling_class_id, profile, position)
    )
    """,
    """
    CREATE UNIQUE INDEX ux_sampling_classes_default
    ON sampling_classes(is_default) WHERE is_default=1
    """,
    """
    CREATE TRIGGER prevent_default_sampling_class_delete
    BEFORE DELETE ON sampling_classes
    WHEN OLD.is_default = 1
    BEGIN
        SELECT RAISE(
            ABORT,
            'La classe di campionamento predefinita non può essere eliminata.'
        );
    END
    """,
)


class DatabaseSchemaError(RuntimeError):
    """Il database non e compatibile con lo schema atteso dall'applicazione."""


def get_schema_version(database_path: Optional[str] = None) -> int:
    path = database_path or get_db_path()
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def initialize_database(
        database_path: Optional[str] = None,
        create_backup: bool = True) -> int:
    """Crea lo schema corrente o applica in ordine le migrazioni note."""
    path = database_path or get_db_path()
    db_dir = os.path.dirname(path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > CURRENT_SCHEMA_VERSION:
            raise DatabaseSchemaError(
                f"Database versione {version}: questa applicazione supporta "
                f"fino alla versione {CURRENT_SCHEMA_VERSION}."
            )
        if version == CURRENT_SCHEMA_VERSION:
            _validate_v3(conn)
            return version

        tables = _user_tables(conn)
        database_was_empty = not tables
        if not tables:
            _create_new_v1(conn)
        elif version == 0 and _matches_columns(conn, LEGACY_PRODUCTION_COLUMNS):
            if create_backup:
                _backup_database(conn, path)
            _migrate_production_v0_to_v1(conn)
        elif version == 1 and _matches_columns(conn, V1_COLUMNS):
            if create_backup:
                _backup_database(conn, path, "v1-v2")
        elif version == 2 and _matches_columns(conn, V2_COLUMNS):
            pass
        else:
            raise DatabaseSchemaError(
                "Database senza versione con schema non riconosciuto. "
                "La migrazione automatica non riconosce questa struttura."
            )

        if int(conn.execute("PRAGMA user_version").fetchone()[0]) == 1:
            _migrate_v1_to_v2(conn)
        if int(conn.execute("PRAGMA user_version").fetchone()[0]) == 2:
            _validate_v2(conn)
            if create_backup and not database_was_empty:
                _backup_database(conn, path, "v2-v3")
            _migrate_v2_to_v3(conn)
        _validate_v3(conn)
        return CURRENT_SCHEMA_VERSION
    finally:
        conn.close()


def _user_tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[1] for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def _matches_columns(
        conn: sqlite3.Connection,
        expected: dict[str, set[str]]) -> bool:
    if _user_tables(conn) != set(expected):
        return False
    return all(
        _table_columns(conn, table) == columns
        for table, columns in expected.items()
    )


def _backup_database(
        conn: sqlite3.Connection, database_path: str,
        migration: str = "v0-v1") -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = f"{database_path}.pre-{migration}-{timestamp}.bak"
    backup_conn = sqlite3.connect(backup_path)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()
    return backup_path


def _create_schema_v1(conn: sqlite3.Connection):
    for statement in SCHEMA_V1_STATEMENTS:
        conn.execute(statement)


def _insert_default_class(conn: sqlite3.Connection) -> int:
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """INSERT INTO sampling_classes
           (code, description, is_default, created_at, updated_at)
           VALUES (?, ?, 1, ?, ?)""",
        ("DEFAULT", "Classe di campionamento predefinita", now, now),
    )
    return int(cursor.lastrowid)


def _insert_sampling_defaults(
        conn: sqlite3.Connection, sampling_class_id: int):
    for profile in SAMPLING_PLANS:
        for position, row in enumerate(get_default_sampling_plan(profile)):
            values = tuple(row[column] for column in SAMPLING_PLAN_COLUMNS)
            conn.execute(
                """INSERT INTO sampling_plan_defaults
                   (profile, position, lot_min, lot_max,
                    critical_n, critical_ac, critical_re,
                    important_n, important_ac, important_re,
                    normal_n, normal_ac, normal_re)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (profile, position, *values),
            )
            conn.execute(
                """INSERT INTO sampling_plans
                   (sampling_class_id, profile, position, lot_min, lot_max,
                    critical_n, critical_ac, critical_re,
                    important_n, important_ac, important_re,
                    normal_n, normal_ac, normal_re)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sampling_class_id, profile, position, *values),
            )


def _create_new_v1(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        _create_schema_v1(conn)
        default_class_id = _insert_default_class(conn)
        _insert_sampling_defaults(conn, default_class_id)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_production_v0_to_v1(conn: sqlite3.Connection):
    counts_before = {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in LEGACY_PRODUCTION_COLUMNS
    }

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for table in (
                "measurements", "lots", "controls", "setups",
                "operators", "suppliers"):
            conn.execute(f"ALTER TABLE {table} RENAME TO legacy_{table}")

        _create_schema_v1(conn)
        default_class_id = _insert_default_class(conn)
        _insert_sampling_defaults(conn, default_class_id)

        conn.execute("""
            INSERT INTO operators
            SELECT id, name, email, phone, notes, created_at, updated_at
            FROM legacy_operators
        """)
        conn.execute("""
            INSERT INTO suppliers
            SELECT id, name, vat_code, contact, email, phone, notes,
                   created_at, updated_at
            FROM legacy_suppliers
        """)
        conn.execute("""
            INSERT INTO setups
            (id, name, description, pdf_path, sampling_class_id,
             created_at, updated_at)
            SELECT id, name, description, pdf_path, ?, created_at, updated_at
            FROM legacy_setups
        """, (default_class_id,))
        conn.execute("""
            INSERT INTO controls
            (id, setup_id, balloon_num, balloon_x, balloon_y, pdf_page,
             control_type, criticality, label, nominal, tol_plus, tol_minus,
             description)
            SELECT id, setup_id, balloon_num, balloon_x, balloon_y, pdf_page,
                   control_type, 'C', label, nominal, tol_plus, tol_minus,
                   description
            FROM legacy_controls
        """)
        conn.execute("""
            INSERT INTO lots
            (id, setup_id, lot_code, lot_quantity, n_samples,
             critical_n, critical_ac, critical_re,
             important_n, important_ac, important_re,
             normal_n, normal_ac, normal_re, sampling_profile,
             operator, operator_id, supplier, supplier_id, notes,
             created_at, closed, cancelled)
            SELECT id, setup_id, lot_code, lot_quantity, n_samples,
                   NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                   operator, operator_id, supplier, supplier_id, notes,
                   created_at, closed, cancelled
            FROM legacy_lots
        """)
        conn.execute("""
            INSERT INTO measurements
            (id, lot_id, control_id, sample_num, value_num, value_bool,
             pass_fail, accepted_in_derogation, derogation_reason,
             derogation_authorized_by, derogation_accepted_by,
             derogation_at, recorded_at)
            SELECT id, lot_id, control_id, sample_num, value_num, value_bool,
                   pass_fail, accepted_in_derogation, derogation_reason,
                   derogation_authorized_by, derogation_accepted_by,
                   derogation_at, recorded_at
            FROM legacy_measurements
        """)

        for table in (
                "legacy_measurements", "legacy_lots", "legacy_controls",
                "legacy_setups", "legacy_operators", "legacy_suppliers"):
            conn.execute(f"DROP TABLE {table}")

        counts_after = {
            table: int(conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0])
            for table in LEGACY_PRODUCTION_COLUMNS
        }
        if counts_after != counts_before:
            raise DatabaseSchemaError(
                "Migrazione annullata: il conteggio dei record non coincide."
            )

        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    # La ricostruzione lascia pagine libere appartenute alle tabelle legacy.
    conn.execute("VACUUM")


def _validate_v1(conn: sqlite3.Connection):
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version != 1:
        raise DatabaseSchemaError(
            f"Versione schema non valida: {version}, attesa "
            "1."
        )
    if not _matches_columns(conn, V1_COLUMNS):
        raise DatabaseSchemaError(
            "Il database dichiara la versione 1 ma lo schema non coincide."
        )
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise DatabaseSchemaError(
            f"Il database contiene {len(foreign_key_errors)} errori di "
            "integrità referenziale."
        )
    quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
    if quick_check != "ok":
        raise DatabaseSchemaError(
            f"Controllo integrità SQLite fallito: {quick_check}."
        )
    default_count = int(conn.execute(
        "SELECT COUNT(*) FROM sampling_classes WHERE is_default=1"
    ).fetchone()[0])
    if default_count != 1:
        raise DatabaseSchemaError(
            "Lo schema richiede esattamente una classe predefinita."
        )
    required_objects = {
        ("index", "ux_sampling_classes_default"),
        ("trigger", "prevent_default_sampling_class_delete"),
    }
    actual_objects = {
        (row[0], row[1]) for row in conn.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE type IN ('index', 'trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    if not required_objects.issubset(actual_objects):
        raise DatabaseSchemaError(
            "Indice o trigger obbligatorio dello schema versione 1 mancante."
        )
    defaults_count = int(conn.execute(
        "SELECT COUNT(*) FROM sampling_plan_defaults"
    ).fetchone()[0])
    if defaults_count != sum(len(rows) for rows in SAMPLING_PLANS.values()):
        raise DatabaseSchemaError(
            "La copia dei piani di campionamento predefiniti non è completa."
        )
    class_ids = [
        row[0] for row in conn.execute("SELECT id FROM sampling_classes")
    ]
    for sampling_class_id in class_ids:
        profiles = {
            row[0] for row in conn.execute(
                "SELECT DISTINCT profile FROM sampling_plans "
                "WHERE sampling_class_id=?",
                (sampling_class_id,),
            ).fetchall()
        }
        if profiles != set(SAMPLING_PLANS):
            raise DatabaseSchemaError(
                f"Piani incompleti per la classe {sampling_class_id}."
            )


def _migrate_v1_to_v2(conn: sqlite3.Connection):
    """Aggiunge alla classe le regole per il piano suggerito."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "ALTER TABLE sampling_classes ADD COLUMN "
            "history_validity_days INTEGER NOT NULL DEFAULT 730 "
            "CHECK(history_validity_days >= 1)"
        )
        conn.execute(
            "ALTER TABLE sampling_classes ADD COLUMN "
            "extended_passes_required INTEGER NOT NULL DEFAULT 1 "
            "CHECK(extended_passes_required >= 1)"
        )
        conn.execute(
            "ALTER TABLE sampling_classes ADD COLUMN "
            "normal_passes_required INTEGER NOT NULL DEFAULT 2 "
            "CHECK(normal_passes_required >= 1)"
        )
        conn.execute(
            "ALTER TABLE sampling_classes ADD COLUMN "
            "fail_resets_extended INTEGER NOT NULL DEFAULT 1 "
            "CHECK(fail_resets_extended IN (0, 1))"
        )
        conn.execute(
            "ALTER TABLE sampling_classes ADD COLUMN "
            "derogation_counts_positive INTEGER NOT NULL DEFAULT 0 "
            "CHECK(derogation_counts_positive IN (0, 1))"
        )
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _file_sha256(path: str) -> str:
    """Calcola l'hash del PDF senza rendere la migrazione dipendente dal file."""
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _revision_content_hash(setup: dict, controls: list[dict]) -> str:
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


def _create_revision_tables(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE setup_revisions (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            revision_uid               TEXT NOT NULL UNIQUE,
            setup_id                   INTEGER NOT NULL
                                       REFERENCES setups(id) ON DELETE CASCADE,
            version_number             INTEGER NOT NULL CHECK(version_number >= 1),
            content_hash               TEXT NOT NULL,
            name                       TEXT NOT NULL,
            description                TEXT,
            pdf_path                   TEXT NOT NULL,
            pdf_sha256                 TEXT NOT NULL,
            sampling_class_code        TEXT,
            sampling_class_description TEXT,
            created_at                 TEXT NOT NULL,
            UNIQUE(setup_id, version_number)
        )
    """)
    conn.execute("""
        CREATE TABLE revision_controls (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            setup_revision_id INTEGER NOT NULL
                              REFERENCES setup_revisions(id) ON DELETE CASCADE,
            source_control_id INTEGER,
            balloon_num       INTEGER NOT NULL,
            balloon_x         REAL NOT NULL,
            balloon_y         REAL NOT NULL,
            pdf_page          INTEGER NOT NULL DEFAULT 0,
            control_type      TEXT NOT NULL
                              CHECK(control_type IN ('dimensional', 'yesno')),
            criticality       TEXT NOT NULL DEFAULT 'N'
                              CHECK(criticality IN ('C', 'I', 'N')),
            label             TEXT,
            nominal           REAL,
            tol_plus          REAL,
            tol_minus         REAL,
            description       TEXT,
            UNIQUE(setup_revision_id, balloon_num),
            UNIQUE(setup_revision_id, source_control_id)
        )
    """)


def _insert_initial_revisions(conn: sqlite3.Connection):
    setups = conn.execute("""
        SELECT s.*, sc.code AS sampling_class_code,
               sc.description AS sampling_class_description
        FROM setups s
        LEFT JOIN sampling_classes sc ON sc.id=s.sampling_class_id
        ORDER BY s.id
    """).fetchall()
    now = datetime.now().isoformat()
    for setup_row in setups:
        setup = dict(setup_row)
        controls = [dict(row) for row in conn.execute(
            "SELECT * FROM controls WHERE setup_id=? ORDER BY balloon_num, id",
            (setup["id"],),
        ).fetchall()]
        cursor = conn.execute("""
            INSERT INTO setup_revisions
            (revision_uid, setup_id, version_number, content_hash, name,
             description, pdf_path, pdf_sha256, sampling_class_code,
             sampling_class_description, created_at)
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), setup["id"],
            _revision_content_hash(setup, controls), setup["name"],
            setup.get("description"), setup["pdf_path"],
            _file_sha256(setup["pdf_path"]),
            setup.get("sampling_class_code"),
            setup.get("sampling_class_description"), now,
        ))
        revision_id = int(cursor.lastrowid)
        for control in controls:
            conn.execute("""
                INSERT INTO revision_controls
                (setup_revision_id, source_control_id, balloon_num, balloon_x,
                 balloon_y, pdf_page, control_type, criticality, label,
                 nominal, tol_plus, tol_minus, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                revision_id, control["id"], control["balloon_num"],
                control["balloon_x"], control["balloon_y"],
                control.get("pdf_page", 0), control["control_type"],
                control.get("criticality") or "N", control.get("label"),
                control.get("nominal"), control.get("tol_plus"),
                control.get("tol_minus"), control.get("description"),
            ))


def _deduplicate_setup_names(conn: sqlite3.Connection):
    conn.execute(
        "UPDATE setups SET name=CASE WHEN trim(name)='' "
        "THEN 'Setup ' || id ELSE trim(name) END"
    )
    duplicates = conn.execute("""
        SELECT name, COUNT(*) AS occurrences
        FROM setups
        GROUP BY name COLLATE NOCASE
        HAVING COUNT(*) > 1
        ORDER BY name COLLATE NOCASE
    """).fetchall()
    for duplicate in duplicates:
        same_name = conn.execute("""
            SELECT s.id, s.name
            FROM setups s
            WHERE s.name=? COLLATE NOCASE
            ORDER BY EXISTS(
                SELECT 1 FROM lots l
                WHERE l.setup_id=s.id AND l.closed=1 AND l.cancelled=0
            ) DESC, s.updated_at DESC, s.id DESC
        """, (duplicate["name"],)).fetchall()
        # Conserva il nome originale sul setup più rilevante; gli altri restano
        # disponibili con un nome esplicitamente distinguibile.
        for row in same_name[1:]:
            candidate = f"{row['name']} [duplicato {row['id']}]"
            while conn.execute(
                    "SELECT 1 FROM setups WHERE name=? COLLATE NOCASE",
                    (candidate,),
            ).fetchone() is not None:
                candidate += "_"
            conn.execute(
                "UPDATE setups SET name=?, updated_at=? WHERE id=?",
                (candidate, datetime.now().isoformat(), row["id"]),
            )


def _migrate_v2_to_v3(conn: sqlite3.Connection):
    """Introduce revisioni immutabili e conserva soltanto lotti conclusi."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        _deduplicate_setup_names(conn)
        # Il nuovo flusso persiste soltanto controlli completati. Le vecchie
        # sessioni aperte o annullate vengono eliminate insieme alle misure.
        conn.execute(
            "DELETE FROM measurements WHERE lot_id IN "
            "(SELECT id FROM lots WHERE closed=0 OR cancelled=1)"
        )
        conn.execute("DELETE FROM lots WHERE closed=0 OR cancelled=1")

        conn.execute(
            "CREATE UNIQUE INDEX ux_setups_name_nocase "
            "ON setups(name COLLATE NOCASE)"
        )
        _create_revision_tables(conn)
        _insert_initial_revisions(conn)

        conn.execute(
            "ALTER TABLE lots ADD COLUMN setup_revision_id INTEGER "
            "REFERENCES setup_revisions(id)"
        )
        conn.execute("ALTER TABLE lots ADD COLUMN final_status TEXT")
        conn.execute("ALTER TABLE lots ADD COLUMN saved_at TEXT")
        conn.execute("""
            UPDATE lots
            SET setup_revision_id=(
                    SELECT sr.id FROM setup_revisions sr
                    WHERE sr.setup_id=lots.setup_id AND sr.version_number=1
                ),
                saved_at=COALESCE(saved_at, created_at)
        """)

        conn.execute("ALTER TABLE measurements RENAME TO legacy_measurements_v2")
        legacy_measurement_count = int(conn.execute(
            "SELECT COUNT(*) FROM legacy_measurements_v2"
        ).fetchone()[0])
        conn.execute("""
            CREATE TABLE measurements (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                lot_id        INTEGER NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
                control_id    INTEGER NOT NULL
                              REFERENCES revision_controls(id),
                sample_num    INTEGER NOT NULL CHECK(sample_num >= 1),
                value_num     REAL,
                value_bool    INTEGER CHECK(value_bool IN (0, 1) OR value_bool IS NULL),
                pass_fail     INTEGER NOT NULL DEFAULT 0 CHECK(pass_fail IN (0, 1)),
                accepted_in_derogation INTEGER NOT NULL DEFAULT 0
                                       CHECK(accepted_in_derogation IN (0, 1)),
                derogation_reason TEXT,
                derogation_authorized_by TEXT,
                derogation_accepted_by TEXT,
                derogation_at TEXT,
                recorded_at   TEXT NOT NULL,
                UNIQUE(lot_id, control_id, sample_num),
                CHECK(pass_fail=0 OR accepted_in_derogation=0)
            )
        """)
        conn.execute("""
            INSERT INTO measurements
            (id, lot_id, control_id, sample_num, value_num, value_bool,
             pass_fail, accepted_in_derogation, derogation_reason,
             derogation_authorized_by, derogation_accepted_by,
             derogation_at, recorded_at)
            SELECT m.id, m.lot_id, rc.id, m.sample_num, m.value_num,
                   m.value_bool, m.pass_fail, m.accepted_in_derogation,
                   m.derogation_reason, m.derogation_authorized_by,
                   m.derogation_accepted_by, m.derogation_at, m.recorded_at
            FROM legacy_measurements_v2 m
            JOIN lots l ON l.id=m.lot_id
            JOIN revision_controls rc
              ON rc.setup_revision_id=l.setup_revision_id
             AND rc.source_control_id=m.control_id
        """)
        migrated_measurement_count = int(conn.execute(
            "SELECT COUNT(*) FROM measurements"
        ).fetchone()[0])
        if migrated_measurement_count != legacy_measurement_count:
            raise DatabaseSchemaError(
                "Migrazione interrotta: alcune misure storiche non sono "
                "associabili alla revisione del setup."
            )
        conn.execute("DROP TABLE legacy_measurements_v2")
        conn.execute("""
            CREATE TRIGGER prevent_setup_with_lots_delete
            BEFORE DELETE ON setups
            WHEN EXISTS(SELECT 1 FROM lots WHERE setup_id=OLD.id)
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Un setup con controlli salvati non può essere eliminato.'
                );
            END
        """)
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _validate_v2(conn: sqlite3.Connection):
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version != 2:
        raise DatabaseSchemaError(
            f"Versione schema non valida: {version}, attesa 2."
        )
    if not _matches_columns(conn, V2_COLUMNS):
        raise DatabaseSchemaError(
            "Il database dichiara la versione 2 ma lo schema non coincide."
        )
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise DatabaseSchemaError(
            f"Il database contiene {len(foreign_key_errors)} errori di "
            "integrità referenziale."
        )
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise DatabaseSchemaError("Controllo integrità SQLite fallito.")
    invalid_rules = int(conn.execute(
        """SELECT COUNT(*) FROM sampling_classes
           WHERE history_validity_days < 1
              OR extended_passes_required < 1
              OR normal_passes_required < 1
              OR fail_resets_extended NOT IN (0, 1)
              OR derogation_counts_positive NOT IN (0, 1)"""
    ).fetchone()[0])
    if invalid_rules:
        raise DatabaseSchemaError(
            "Sono presenti regole automatiche non valide nelle classi."
        )
    default_count = int(conn.execute(
        "SELECT COUNT(*) FROM sampling_classes WHERE is_default=1"
    ).fetchone()[0])
    if default_count != 1:
        raise DatabaseSchemaError(
            "Lo schema richiede esattamente una classe predefinita."
        )
    required_objects = {
        ("index", "ux_sampling_classes_default"),
        ("trigger", "prevent_default_sampling_class_delete"),
    }
    actual_objects = {
        (row[0], row[1]) for row in conn.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE type IN ('index', 'trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    if not required_objects.issubset(actual_objects):
        raise DatabaseSchemaError(
            "Indice o trigger obbligatorio dello schema mancante."
        )
    defaults_count = int(conn.execute(
        "SELECT COUNT(*) FROM sampling_plan_defaults"
    ).fetchone()[0])
    if defaults_count != sum(len(rows) for rows in SAMPLING_PLANS.values()):
        raise DatabaseSchemaError(
            "La copia dei piani di campionamento predefiniti non è completa."
        )
    for sampling_class_id, in conn.execute("SELECT id FROM sampling_classes"):
        profiles = {
            row[0] for row in conn.execute(
                "SELECT DISTINCT profile FROM sampling_plans "
                "WHERE sampling_class_id=?", (sampling_class_id,),
            ).fetchall()
        }
        if profiles != set(SAMPLING_PLANS):
            raise DatabaseSchemaError(
                f"Piani incompleti per la classe {sampling_class_id}."
            )


def _validate_v3(conn: sqlite3.Connection):
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version != CURRENT_SCHEMA_VERSION:
        raise DatabaseSchemaError(
            f"Versione schema non valida: {version}, attesa "
            f"{CURRENT_SCHEMA_VERSION}."
        )
    if not _matches_columns(conn, V3_COLUMNS):
        raise DatabaseSchemaError(
            "Il database dichiara la versione 3 ma lo schema non coincide."
        )
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise DatabaseSchemaError("Controllo integrità SQLite fallito.")
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise DatabaseSchemaError(
            f"Il database contiene {len(foreign_key_errors)} errori di "
            "integrità referenziale."
        )
    required_objects = {
        ("index", "ux_sampling_classes_default"),
        ("index", "ux_setups_name_nocase"),
        ("trigger", "prevent_default_sampling_class_delete"),
        ("trigger", "prevent_setup_with_lots_delete"),
    }
    actual_objects = {
        (row[0], row[1]) for row in conn.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE type IN ('index', 'trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    if not required_objects.issubset(actual_objects):
        raise DatabaseSchemaError(
            "Indici o trigger obbligatori dello schema versione 3 mancanti."
        )
    invalid_lots = int(conn.execute(
        "SELECT COUNT(*) FROM lots "
        "WHERE closed<>1 OR cancelled<>0 OR setup_revision_id IS NULL"
    ).fetchone()[0])
    if invalid_lots:
        raise DatabaseSchemaError(
            "Lo schema versione 3 contiene lotti aperti, annullati o senza "
            "revisione del setup."
        )
    _validate_v2_rules_and_plans(conn)


def _validate_v2_rules_and_plans(conn: sqlite3.Connection):
    """Validazioni di contenuto condivise con lo schema v3."""
    invalid_rules = int(conn.execute(
        """SELECT COUNT(*) FROM sampling_classes
           WHERE history_validity_days < 1
              OR extended_passes_required < 1
              OR normal_passes_required < 1
              OR fail_resets_extended NOT IN (0, 1)
              OR derogation_counts_positive NOT IN (0, 1)"""
    ).fetchone()[0])
    if invalid_rules:
        raise DatabaseSchemaError(
            "Sono presenti regole automatiche non valide nelle classi."
        )
    if int(conn.execute(
            "SELECT COUNT(*) FROM sampling_classes WHERE is_default=1"
            ).fetchone()[0]) != 1:
        raise DatabaseSchemaError(
            "Lo schema richiede esattamente una classe predefinita."
        )
    defaults_count = int(conn.execute(
        "SELECT COUNT(*) FROM sampling_plan_defaults"
    ).fetchone()[0])
    if defaults_count != sum(len(rows) for rows in SAMPLING_PLANS.values()):
        raise DatabaseSchemaError(
            "La copia dei piani di campionamento predefiniti non è completa."
        )
    for sampling_class_id, in conn.execute("SELECT id FROM sampling_classes"):
        profiles = {
            row[0] for row in conn.execute(
                "SELECT DISTINCT profile FROM sampling_plans "
                "WHERE sampling_class_id=?", (sampling_class_id,),
            ).fetchall()
        }
        if profiles != set(SAMPLING_PLANS):
            raise DatabaseSchemaError(
                f"Piani incompleti per la classe {sampling_class_id}."
            )


def _cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crea o migra il database di QC Inspector."
    )
    parser.add_argument("database", help="Percorso del database SQLite")
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Non creare il backup prima delle migrazioni.",
    )
    args = parser.parse_args(argv)
    version = initialize_database(
        str(Path(args.database)), create_backup=not args.no_backup
    )
    print(f"Database pronto: schema versione {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
