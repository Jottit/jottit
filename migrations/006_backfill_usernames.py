import re
import secrets


def _slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def migrate(conn):
    users = conn.execute(
        "SELECT id, email FROM users WHERE username IS NULL"
    ).fetchall()
    if not users:
        return

    taken = {
        row["username"]
        for row in conn.execute(
            "SELECT username FROM users WHERE username IS NOT NULL"
        ).fetchall()
    }

    for user in users:
        prefix = user["email"].split("@")[0]
        base = _slugify(prefix)
        if not base:
            base = "user"
        username = base
        while username in taken:
            username = f"{base}-{secrets.token_hex(2)}"
        taken.add(username)
        conn.execute(
            "UPDATE users SET username = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (username, user["id"]),
        )
