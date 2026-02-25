import difflib
import secrets
import string

import markdown
from flask import Blueprint, abort, redirect, render_template, request, session

from db import get_latest_revision, get_page, get_revision, get_revisions, save_page

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
        row = get_latest_revision(slug)
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

    save_page(slug, content, draft)

    owned = session.get("owned_sites", [])
    if slug not in owned:
        owned.append(slug)
        session["owned_sites"] = owned

    return redirect(f"/{slug}")


def _get_title(content):
    if content.startswith("# "):
        return content.split("\n", 1)[0][2:]
    return None


def _describe_change(prev, curr):
    old_title = _get_title(prev)
    new_title = _get_title(curr)

    if new_title != old_title and new_title:
        return f"Changed title to \u201c{new_title}\u201d"

    old_lines = prev.splitlines()
    new_lines = curr.splitlines()
    added = []
    removed = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes():
        if tag == "insert":
            added.extend(new_lines[j1:j2])
        elif tag == "delete":
            removed.extend(old_lines[i1:i2])
        elif tag == "replace":
            removed.extend(old_lines[i1:i2])
            added.extend(new_lines[j1:j2])

    # Skip the title line from snippets
    added = [l for l in added if not l.startswith("# ")]
    removed = [l for l in removed if not l.startswith("# ")]

    if added and not removed:
        snippet = added[0].strip()
        if snippet:
            return f"Added \u201c{snippet[:60]}\u201d"
        return f"Added {len(added)} line{'s' if len(added) != 1 else ''}"
    if removed and not added:
        snippet = removed[0].strip()
        if snippet:
            return f"Removed \u201c{snippet[:60]}\u201d"
        return f"Removed {len(removed)} line{'s' if len(removed) != 1 else ''}"
    if added and removed:
        old_snip = removed[0].strip()
        new_snip = added[0].strip()
        if old_snip and new_snip:
            return f"Changed \u201c{old_snip[:40]}\u201d to \u201c{new_snip[:40]}\u201d"

    return "Edited page"


@bp.route("/<slug>/history")
def page_history(slug):
    revisions = get_revisions(slug)

    if not revisions:
        abort(404)

    entries = []
    for i, rev in enumerate(revisions):
        if i == 0:
            description = None
        else:
            description = _describe_change(revisions[i - 1]["content"], rev["content"])
        entries.append({
            "revision": rev["revision"],
            "created_at": rev["created_at"],
            "description": description,
        })
    entries.reverse()

    return render_template("history.html", slug=slug, revisions=entries)


@bp.route("/<slug>/history/<int:revision>")
def view_revision(slug, revision):
    row = get_revision(slug, revision)

    if not row:
        abort(404)

    html = markdown.markdown(row["content"])
    return render_template(
        "revision.html",
        content=html,
        slug=slug,
        revision=row["revision"],
        created_at=row["created_at"],
    )


@bp.route("/<slug>")
def view_page(slug):
    row = get_page(slug)

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
