"""Archivi portabili del database e dei disegni PDF."""

from collections.abc import Callable
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from ..database.db_manager import _revision_content_hash
from ..database.schema_manager import (
    CURRENT_SCHEMA_VERSION, V5_COLUMNS, _validate_revision_schema,
)
from .pdf_storage import _sha256_file


DATABASE = "database.sqlite"
MANIFEST = "backup.json"
PDF_TABLES = ("setups", "setup_revisions")
TABLES = (
    "operators", "suppliers", "sampling_classes", "sampling_plan_defaults",
    "sampling_plans", "setups", "controls", "setup_revisions",
    "revision_controls", "lots", "measurements",
)
ConflictResolver = Callable[[str], tuple[str, str] | None]


class RestoreCancelled(Exception):
    """L'utente ha annullato il ripristino."""


def _connect(path: Path, mode: str = "rw") -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA trusted_schema = OFF")
    return conn


def _pdf_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.suffix.lower() == ".pdf" and (path.is_file() or path.is_symlink())
    }


def _pdf_references(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0] for table in PDF_TABLES
        for row in conn.execute(f"SELECT DISTINCT pdf_path FROM {table}")
    }


def create_backup(destination: Path, database: Path, pdf_dir: Path) -> Path:
    """Pubblica lo ZIP solo dopo aver copiato database e PDF."""
    with closing(_connect(database)) as live:
        # Serializza la copia dei PDF con le scritture e gli altri ripristini.
        live.execute("BEGIN IMMEDIATE")
        return _create_backup(destination, database, pdf_dir, "qc-inspector")


def _create_backup(destination: Path, database: Path, pdf_dir: Path,
                   prefix: str) -> Path:
    now = datetime.now(timezone.utc)
    name = f"{prefix}-{now:%Y%m%dT%H%M%S%fZ}-{uuid4().hex[:8]}.zip"
    with TemporaryDirectory(prefix=".backup-", dir=destination) as workdir:
        work = Path(workdir)
        snapshot_path = work / DATABASE
        with closing(_connect(database, "ro")) as source, \
                closing(_connect(snapshot_path, "rwc")) as snapshot:
            source.backup(snapshot)
            references = _pdf_references(snapshot)
            count = snapshot.execute("SELECT COUNT(*) FROM setups").fetchone()[0]
            schema_version = snapshot.execute("PRAGMA user_version").fetchone()[0]

        files = _pdf_files(pdf_dir)
        by_path = {path.resolve(): name for name, path in files.items()}
        paths = {}
        for original in sorted(references):
            if not original:
                continue
            path = Path(original).resolve()
            name_in_archive = by_path.get(path)
            if name_in_archive is None:
                name_in_archive = f"{uuid4().hex}.pdf"
                files[name_in_archive] = path
                by_path[path] = name_in_archive
            paths[original] = name_in_archive

        manifest = {
            "format_version": 1,
            "schema_version": schema_version,
            "generated_at": now.isoformat(),
            "setup_count": count,
            "pdf_paths": paths,
        }
        archive = work / name
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
            output.write(snapshot_path, DATABASE)
            for relative, path in files.items():
                if not path.is_file():
                    raise ValueError(f"PDF non disponibile: {path}")
                output.write(path, f"pdf/{relative}")
            output.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.chmod(0o600)
        result = destination / name
        os.replace(archive, result)
    return result


def _unpack(archive: Path, work: Path) -> dict:
    with ZipFile(archive) as source:
        names = source.namelist()
        if len(set(names)) != len(names) or not {DATABASE, MANIFEST} <= set(names):
            raise ValueError("L'archivio di backup è incompleto o contiene duplicati.")
        manifest = json.loads(source.read(MANIFEST))
        if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
            raise ValueError("Formato di backup non supportato.")
        for name in names:
            if name == MANIFEST:
                continue
            relative = PurePosixPath(name)
            if name != DATABASE and (
                not name.startswith("pdf/") or relative.suffix.lower() != ".pdf"
                or ".." in relative.parts or relative.as_posix() != name
                or "\\" in name or ":" in name
            ):
                raise ValueError(f"Percorso non valido nell'archivio: {name}")
            target = work.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(name) as origin, target.open("xb") as output:
                shutil.copyfileobj(origin, output)
    return manifest


def _check_backup(source: sqlite3.Connection, manifest: dict, files: dict) -> None:
    references = _pdf_references(source) - {""}
    paths = manifest.get("pdf_paths")
    if (not isinstance(paths, dict) or set(paths) != references
            or any(not isinstance(path, str) or path not in files for path in paths.values())):
        raise ValueError("L'archivio non contiene tutti i PDF indicati nel database.")
    if manifest.get("setup_count") != source.execute("SELECT COUNT(*) FROM setups").fetchone()[0]:
        raise ValueError("Il numero di setup non coincide con quello dichiarato nel backup.")


def _insert(conn: sqlite3.Connection, table: str, values: dict) -> int:
    columns = ", ".join('"' + column.replace('"', '""') + '"' for column in values)
    placeholders = ", ".join("?" for _ in values)
    return conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values())
    ).lastrowid


def _replace_database(live: sqlite3.Connection, source: sqlite3.Connection) -> None:
    trigger = live.execute(
        "SELECT sql FROM sqlite_schema WHERE name='prevent_default_sampling_class_delete'"
    ).fetchone()[0]
    live.execute("DROP TRIGGER prevent_default_sampling_class_delete")
    for table in reversed(TABLES):
        live.execute(f"DELETE FROM {table}")
    for table in TABLES:
        for row in source.execute(f"SELECT * FROM {table}"):
            _insert(live, table, dict(row))
    live.execute(trigger)
    live.execute("DELETE FROM sqlite_sequence")
    live.executemany(
        "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
        source.execute("SELECT name, seq FROM sqlite_sequence"),
    )


def _name_key(name: str) -> str:
    # SQLite NOCASE distingue i caratteri non ASCII.
    return name.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def _setup_names(live: sqlite3.Connection, source: sqlite3.Connection,
                 resolve: ConflictResolver) -> tuple[dict[int, str], list[int]]:
    names = {}
    replacements = []
    for setup_id, name in source.execute("SELECT id, name FROM setups ORDER BY id"):
        existing = live.execute(
            "SELECT id FROM setups WHERE name=? COLLATE NOCASE", (name,)
        ).fetchone()
        if existing:
            while True:
                choice = resolve(name)
                if choice is None:
                    raise RestoreCancelled()
                action, new_name = choice
                if action == "replace":
                    replacements.append(existing[0])
                    break
                if action != "rename":
                    raise ValueError("Scelta per il setup duplicato non valida.")
                name = new_name.strip()
                if name and not (
                    live.execute("SELECT 1 FROM setups WHERE name=? COLLATE NOCASE", (name,)).fetchone()
                    or source.execute("SELECT 1 FROM setups WHERE name=? COLLATE NOCASE", (name,)).fetchone()
                    or any(_name_key(name) == _name_key(used) for used in names.values())
                ):
                    break
        names[setup_id] = name
    return names, replacements


def _same_values(left: dict, right: sqlite3.Row, ignored: set) -> bool:
    return all(left[key] == right[key] for key in left.keys() - ignored)


def _merge_registry(live: sqlite3.Connection, source: sqlite3.Connection,
                    table: str, key: str) -> dict[int, int]:
    ids = {}
    for row in source.execute(f"SELECT * FROM {table} ORDER BY id"):
        item = dict(row)
        old_id = item.pop("id")
        plans = []
        if table == "sampling_classes":
            item["is_default"] = 0
            plans = list(source.execute(
                "SELECT * FROM sampling_plans WHERE sampling_class_id=? ORDER BY profile, position",
                (old_id,),
            ))
        original = item[key]
        suffix = 1
        while True:
            existing = live.execute(
                f"SELECT * FROM {table} WHERE {key}=? COLLATE NOCASE", (item[key],)
            ).fetchone()
            if existing is None:
                new_id = _insert(live, table, item)
                for plan in plans:
                    _insert(live, "sampling_plans", dict(plan) | {"sampling_class_id": new_id})
                break
            new_id = existing["id"]
            if _same_values(item, existing, {key, "is_default", "created_at", "updated_at"}):
                current_plans = list(live.execute(
                    "SELECT * FROM sampling_plans WHERE sampling_class_id=? ORDER BY profile, position",
                    (new_id,),
                )) if plans else []
                if len(plans) == len(current_plans) and all(
                    _same_values(dict(plan), current, {"sampling_class_id"})
                    for plan, current in zip(plans, current_plans)
                ):
                    break
            suffix += 1
            item[key] = f"{original} ({suffix})"
        ids[old_id] = new_id
    return ids


def _merge_database(live: sqlite3.Connection, source: sqlite3.Connection,
                    names: dict[int, str], replacements: list[int]) -> None:
    for setup_id in replacements:
        # I lotti devono essere eliminati prima del setup per rispettare il trigger.
        live.execute("DELETE FROM lots WHERE setup_id=?", (setup_id,))
        live.execute("DELETE FROM setups WHERE id=?", (setup_id,))

    ids = {
        "operator_id": _merge_registry(live, source, "operators", "name"),
        "supplier_id": _merge_registry(live, source, "suppliers", "name"),
        "sampling_class_id": _merge_registry(live, source, "sampling_classes", "code"),
    }
    for table, id_key, foreign_keys in (
        ("setups", "setup_id", ("sampling_class_id",)),
        ("controls", "source_control_id", ("setup_id",)),
        ("setup_revisions", "setup_revision_id", ("setup_id",)),
        ("revision_controls", "control_id", ("setup_revision_id", "source_control_id")),
        ("lots", "lot_id", ("setup_id", "setup_revision_id", "operator_id", "supplier_id")),
        ("measurements", None, ("lot_id", "control_id")),
    ):
        remapped = {}
        for row in source.execute(f"SELECT * FROM {table} ORDER BY id"):
            item = dict(row)
            old_id = item.pop("id")
            for key in foreign_keys:
                # Un controllo corrente può essere stato eliminato dopo la revisione.
                item[key] = ids[key].get(item[key])
            if table == "setups":
                item["name"] = names[old_id]
            if table == "setup_revisions" and live.execute(
                "SELECT 1 FROM setup_revisions WHERE revision_uid=?", (item["revision_uid"],)
            ).fetchone():
                item["revision_uid"] = str(uuid4())
            remapped[old_id] = _insert(live, table, item)
        ids[id_key] = remapped


def _relocate_revisions(source: sqlite3.Connection, paths: dict[str, str],
                        names: dict[int, str]) -> None:
    for table in PDF_TABLES:
        source.executemany(
            f"UPDATE {table} SET pdf_path=? WHERE id=?",
            [(paths[row["pdf_path"]], row["id"]) for row in source.execute(
                f"SELECT id, pdf_path FROM {table} WHERE pdf_path<>''"
            )],
        )
    for row in source.execute("""
        SELECT r.*, s.name AS current_name
        FROM setup_revisions r JOIN setups s ON s.id=r.setup_id
    """):
        revision = dict(row)
        if revision["name"] == revision["current_name"]:
            revision["name"] = names.get(revision["setup_id"], revision["name"])
        controls = [dict(control) for control in source.execute(
            "SELECT * FROM revision_controls WHERE setup_revision_id=?", (revision["id"],)
        )]
        source.execute(
            "UPDATE setup_revisions SET name=?, content_hash=?, pdf_sha256=? WHERE id=?",
            (revision["name"], _revision_content_hash(revision, controls),
             _sha256_file(revision["pdf_path"]) if revision["pdf_path"] else "", revision["id"]),
        )


@contextmanager
def _restore_pdfs(root: Path, files: dict[str, Path], *, complete: bool):
    """Ripristina i file spostati se la transazione SQLite fallisce."""
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    existing = _pdf_files(root)
    with TemporaryDirectory(prefix=".ripristino-", dir=root) as staging:
        previous = Path(staging)
        moved = {}
        installed = []
        created_dirs = []
        targets = {}
        reserved = set(files)
        try:
            for name, origin in files.items():
                target = root / name
                if target.resolve() != target or (target.exists() and not target.is_file()):
                    raise ValueError(f"Destinazione PDF non valida: {target}")
                if not complete and target.exists():
                    digest = _sha256_file(origin)
                    while target.exists() and _sha256_file(target) != digest:
                        candidate = f"{uuid4().hex}.pdf"
                        if candidate not in reserved:
                            target = root / candidate
                            reserved.add(candidate)
                targets[name] = str(target)
                if target.exists() and _sha256_file(target) == _sha256_file(origin):
                    continue
                missing = [parent for parent in target.parents if not parent.exists()]
                for parent in reversed(missing):
                    parent.mkdir()
                    created_dirs.append(parent)
                if target.exists():
                    saved = previous / uuid4().hex
                    target.replace(saved)
                    moved[target] = saved
                temporary = previous / uuid4().hex
                shutil.copyfile(origin, temporary)
                group = target.parent.stat().st_gid
                if temporary.stat().st_gid != group:
                    os.chown(temporary, -1, group)
                temporary.chmod(0o640)
                temporary.replace(target)
                installed.append(target)
            if complete:
                for name in existing.keys() - files.keys():
                    target = existing[name]
                    if not target.parent.resolve().is_relative_to(root):
                        raise ValueError(f"Percorso PDF non valido: {target}")
                    saved = previous / uuid4().hex
                    target.replace(saved)
                    moved[target] = saved
            yield targets
        except BaseException:
            for target in reversed(installed):
                target.unlink()
            for target, saved in moved.items():
                saved.replace(target)
            for directory in reversed(created_dirs):
                directory.rmdir()
            raise


def restore_backup(archive: Path, database: Path, pdf_dir: Path, *,
                   resolve_conflict: ConflictResolver | None = None,
                   safety_destination: Path | None = None) -> Path | None:
    """Ripristina tutto con una copia di sicurezza, oppure importa con un resolver."""
    complete = resolve_conflict is None
    if complete and safety_destination is None:
        raise ValueError("Scegli una cartella per la copia di sicurezza.")
    safety_backup = None
    with TemporaryDirectory(prefix="qc-restore-") as directory:
        work = Path(directory)
        manifest = _unpack(archive, work)
        files = _pdf_files(work / "pdf")
        with closing(_connect(work / DATABASE)) as source, closing(_connect(database)) as live:
            version = source.execute("PRAGMA user_version").fetchone()[0]
            if version != CURRENT_SCHEMA_VERSION or manifest.get("schema_version") != version:
                raise ValueError("Versione del database di backup non compatibile.")
            _validate_revision_schema(source, version, V5_COLUMNS)
            _check_backup(source, manifest, files)

            live.execute("BEGIN IMMEDIATE")
            if complete:
                safety_backup = _create_backup(
                    safety_destination, database, pdf_dir, "qc-inspector-prima-del-ripristino"
                )
                names, replacements = {}, []
            else:
                names, replacements = _setup_names(live, source, resolve_conflict)
            with _restore_pdfs(pdf_dir, files, complete=complete) as targets, live:
                paths = {original: targets[name] for original, name in manifest["pdf_paths"].items()}
                _relocate_revisions(source, paths, names)
                if complete:
                    _replace_database(live, source)
                else:
                    _merge_database(live, source, names, replacements)
                if live.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Il ripristino contiene riferimenti a dati mancanti.")
    return safety_backup
