"""Photos et vidéos du club : fichiers sur le disque du serveur (VPS), métadonnées en base.

Les fichiers ne sont PAS dans la base de données (taille). Le type est vérifié par la signature du
contenu (pas seulement l'extension), le nom est aléatoire, la taille est limitée.
"""
import re
import secrets
import shutil
from pathlib import Path

from .uploads import ALLOWED as PHOTO_SIGNATURES
from .uploads import EXT_ALIASES, UploadError

VIDEO_SIGNATURES = {
    "mp4": lambda h: h[4:8] == b"ftyp",
    "m4v": lambda h: h[4:8] == b"ftyp",
    "mov": lambda h: h[4:8] == b"ftyp",
    "webm": lambda h: h.startswith(b"\x1a\x45\xdf\xa3"),
}
MIME = {
    "jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    "mp4": "video/mp4", "m4v": "video/mp4", "mov": "video/quicktime", "webm": "video/webm",
}
NAME_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|gif|webp|mp4|m4v|mov|webm)$")
MIN_FREE_BYTES = 200 * 1024 * 1024  # on laisse toujours 200 Mo libres sur le disque
CHUNK = 1024 * 1024


def kind_for_ext(ext):
    if ext in PHOTO_SIGNATURES:
        return "photo"
    if ext in VIDEO_SIGNATURES:
        return "video"
    return None


def store_file(file_storage, media_dir, max_photo_bytes, max_video_bytes):
    """Valide et enregistre le fichier. Retourne un dict (kind, filename, original_name, mimetype, size)."""
    if file_storage is None or not file_storage.filename:
        raise UploadError("Aucun fichier choisi.")
    original = Path(file_storage.filename).name
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    ext = EXT_ALIASES.get(ext, ext)
    kind = kind_for_ext(ext)
    if kind is None:
        raise UploadError("Format non autorisé. Photos : JPG, PNG, WEBP, GIF. Vidéos : MP4, MOV, WEBM.")
    limit = max_photo_bytes if kind == "photo" else max_video_bytes
    directory = Path(media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < MIN_FREE_BYTES:
        raise UploadError("Espace disque insuffisant sur le serveur.")

    stream = file_storage.stream
    head = stream.read(16)
    signature = (PHOTO_SIGNATURES if kind == "photo" else VIDEO_SIGNATURES)[ext]
    if not head or not signature(head):
        raise UploadError("Le contenu du fichier ne correspond pas à son format.")

    filename = f"{secrets.token_hex(16)}.{ext}"
    target = directory / filename
    size = len(head)
    try:
        with open(target, "wb") as out:
            out.write(head)
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise UploadError(f"Fichier trop volumineux (maximum {limit // (1024 * 1024)} Mo).")
                out.write(chunk)
        try:
            target.chmod(0o640)
        except OSError:
            pass
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {"kind": kind, "filename": filename, "original_name": original[:200],
            "mimetype": MIME[ext], "size": size}


def delete_file(media_dir, filename):
    if filename and NAME_RE.match(filename):
        (Path(media_dir) / filename).unlink(missing_ok=True)


def file_exists(media_dir, filename):
    return bool(filename) and NAME_RE.match(filename) is not None and (Path(media_dir) / filename).is_file()


# ----------------------------------------------------------------- base de données
def list_items(db, public_only=False, limit=200, offset=0):
    where = "WHERE i.is_public = 1" if public_only else ""
    return db.execute(
        "SELECT i.*, s.session_date, s.title AS session_title FROM media_items i "
        f"LEFT JOIN club_sessions s ON s.id = i.session_id {where} "
        "ORDER BY i.created_at DESC, i.id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()


def get_item(db, item_id):
    return db.execute("SELECT * FROM media_items WHERE id = ?", (item_id,)).fetchone()


def get_item_by_filename(db, filename):
    return db.execute("SELECT * FROM media_items WHERE filename = ?", (filename,)).fetchone()


def count_public(db):
    return db.execute("SELECT COUNT(*) AS n FROM media_items WHERE is_public = 1").fetchone()["n"]


def add_item(db, stored, title, caption, session_id, is_public, consent):
    with db:
        return db.insert(
            "INSERT INTO media_items(kind, filename, original_name, mimetype, size_bytes, title, caption, "
            "session_id, is_public, consent_confirmed) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (stored["kind"], stored["filename"], stored["original_name"], stored["mimetype"],
             stored["size"], title, caption, session_id, 1 if is_public else 0, 1 if consent else 0))


def update_item(db, item_id, title, caption, session_id, is_public, consent):
    with db:
        db.execute("UPDATE media_items SET title=?, caption=?, session_id=?, is_public=?, "
                   "consent_confirmed=?, updated_at=datetime('now') WHERE id=?",
                   (title, caption, session_id, 1 if is_public else 0, 1 if consent else 0, item_id))


def delete_item(db, item_id):
    with db:
        db.execute("DELETE FROM media_items WHERE id = ?", (item_id,))
