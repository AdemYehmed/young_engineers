"""Images envoyées depuis l'administration.

Elles sont stockées dans la base de données (table `media`) et non sur le disque : l'hébergeur
Render efface son disque à chaque redémarrage, alors que PostgreSQL conserve les données.
Type vérifié par signature, taille limitée, nom aléatoire.
"""
import secrets

ALLOWED = {
    "png": lambda h: h.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda h: h.startswith(b"\xff\xd8\xff"),
    "gif": lambda h: h.startswith((b"GIF87a", b"GIF89a")),
    "webp": lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP",
}
EXT_ALIASES = {"jpeg": "jpg"}
MIME = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


class UploadError(Exception):
    """Message destiné à l'administrateur (en français)."""


def save_image(db, file_storage, max_bytes):
    """Valide et enregistre l'image. Retourne son nom (ou '' si aucun fichier envoyé)."""
    if file_storage is None or not file_storage.filename:
        return ""
    original = file_storage.filename
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    ext = EXT_ALIASES.get(ext, ext)
    if ext not in ALLOWED:
        raise UploadError("Format non autorisé. Formats acceptés : PNG, JPG, WEBP, GIF.")
    data = file_storage.stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadError(f"Image trop volumineuse (maximum {max_bytes // (1024 * 1024)} Mo).")
    if not data:
        raise UploadError("Le fichier est vide.")
    if not ALLOWED[ext](data[:16]):
        raise UploadError("Le contenu du fichier ne correspond pas à une image valide.")
    name = f"{secrets.token_hex(16)}.{ext}"
    with db:
        db.execute("INSERT INTO media(name, mimetype, data) VALUES (?,?,?)",
                   (name, MIME[ext], data))
    return name


def delete_image(db, name):
    if not name or "/" in name or "\\" in name or ".." in name:
        return
    with db:
        db.execute("DELETE FROM media WHERE name = ?", (name,))


def mimetype_for(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return MIME.get(EXT_ALIASES.get(ext, ext), "application/octet-stream")
