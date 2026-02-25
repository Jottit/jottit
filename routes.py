import secrets
import string

import markdown
from flask import Blueprint, abort, redirect, render_template, request, session

from db import get_db

bp = Blueprint("routes", __name__)


def generate_slug(length=5):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@bp.route("/")
def home():
    return render_template("home.html")


@bp.route("/new")
def new_page():
    slug = generate_slug()
    return redirect(f"/{slug}/edit")


@bp.route("/<slug>/edit", methods=["GET", "POST"])
def edit_page(slug):
    if request.method == "GET":
        db = get_db()
        row = db.execute(
            """SELECT r.content, r.draft FROM revisions r
               JOIN pages p ON r.page_id = p.id
               JOIN sites s ON p.site_id = s.id
               WHERE s.slug = %s
               ORDER BY r.revision DESC LIMIT 1""",
            (slug,),
        ).fetchone()
        db.close()
        content = row["content"] if row else ""
        title = ""
        if content.startswith("# "):
            parts = content.split("\n", 1)
            title = parts[0][2:]
            content = parts[1].strip() if len(parts) > 1 else ""
        return render_template("edit.html", slug=slug, title=title, content=content)

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    draft = "draft" in request.form

    if title:
        content = f"# {title}\n\n{content}"

    db = get_db()
    site = db.execute("SELECT id FROM sites WHERE slug = %s", (slug,)).fetchone()

    if site:
        page = db.execute(
            "SELECT id FROM pages WHERE site_id = %s", (site["id"],)
        ).fetchone()
        next_rev = db.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 AS next_rev FROM revisions WHERE page_id = %s",
            (page["id"],),
        ).fetchone()["next_rev"]
        db.execute(
            "INSERT INTO revisions (page_id, revision, content, draft) VALUES (%s, %s, %s, %s)",
            (page["id"], next_rev, content, draft),
        )
        db.execute(
            "UPDATE pages SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (page["id"],),
        )
    else:
        cursor = db.execute("INSERT INTO sites (slug) VALUES (%s) RETURNING id", (slug,))
        site_id = cursor.fetchone()["id"]
        cursor = db.execute(
            "INSERT INTO pages (site_id, slug) VALUES (%s, '-') RETURNING id",
            (site_id,),
        )
        page_id = cursor.fetchone()["id"]
        db.execute(
            "INSERT INTO revisions (page_id, revision, content, draft) VALUES (%s, 1, %s, %s)",
            (page_id, content, draft),
        )

    db.commit()
    db.close()

    owned = session.get("owned_sites", [])
    if slug not in owned:
        owned.append(slug)
        session["owned_sites"] = owned

    return redirect(f"/{slug}")


@bp.route("/<slug>")
def view_page(slug):
    db = get_db()
    row = db.execute(
        """SELECT r.content, r.draft, r.created_at, s.user_id
           FROM revisions r
           JOIN pages p ON r.page_id = p.id
           JOIN sites s ON p.site_id = s.id
           WHERE s.slug = %s
           ORDER BY r.revision DESC LIMIT 1""",
        (slug,),
    ).fetchone()
    db.close()

    if not row:
        abort(404)

    owned = session.get("owned_sites", [])
    is_owner = slug in owned
    unclaimed = row["user_id"] is None
    show_actions = is_owner or unclaimed
    html = markdown.markdown(row["content"])
    return render_template(
        "page.html",
        content=html,
        draft=row["draft"],
        slug=slug,
        show_actions=show_actions,
        updated_at=row["created_at"],
    )
