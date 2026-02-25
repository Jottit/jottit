import difflib
import secrets
import string

import markdown
from flask import Blueprint, abort, redirect, render_template, request, session

from db import (
    claim_site,
    create_verification_code,
    find_or_create_user,
    get_latest_revision,
    get_page,
    get_revision,
    get_revisions,
    get_site,
    get_sites_for_user,
    get_user_email,
    save_page,
    verify_code,
)
from mail import send_verification_email

bp = Blueprint("routes", __name__)


def generate_slug(length=5):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@bp.route("/")
def home():
    signed_in = "user_id" in session
    return render_template("home.html", signed_in=signed_in)


@bp.route("/new")
def new_page():
    slug = generate_slug()
    return redirect(f"/{slug}/edit")


@bp.route("/<slug>/edit", methods=["GET", "POST"])
def edit_page(slug):
    site = get_site(slug)
    if site and site["user_id"] is not None:
        if session.get("user_id") != site["user_id"]:
            return redirect(f"/{slug}")

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
    return redirect(f"/{slug}")


@bp.route("/<slug>/claim", methods=["GET", "POST"])
def claim_page(slug):
    site = get_site(slug)
    if not site or site["user_id"] is not None:
        return redirect(f"/{slug}")

    if request.method == "GET":
        return render_template("claim.html", slug=slug)

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("claim.html", slug=slug, error="Email is required.")

    code = create_verification_code(email, "claim")
    send_verification_email(email, code)
    session["claim_email"] = email
    return redirect(f"/{slug}/claim/verify")


@bp.route("/<slug>/claim/verify", methods=["GET", "POST"])
def claim_verify(slug):
    site = get_site(slug)
    if not site or site["user_id"] is not None:
        return redirect(f"/{slug}")

    email = session.get("claim_email")
    if not email:
        return redirect(f"/{slug}/claim")

    if request.method == "GET":
        return render_template("verify.html", slug=slug, action=f"/{slug}/claim/verify")

    code = request.form.get("code", "").strip()
    if not verify_code(email, code, "claim"):
        return render_template(
            "verify.html", slug=slug, action=f"/{slug}/claim/verify", error="Invalid or expired code."
        )

    user_id = find_or_create_user(email)
    claim_site(slug, user_id)
    session.pop("claim_email", None)
    session["user_id"] = user_id
    return redirect(f"/{slug}")


@bp.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "GET":
        return render_template("signin.html")

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("signin.html", error="Email is required.")

    code = create_verification_code(email, "signin")
    send_verification_email(email, code)
    session["signin_email"] = email
    return redirect("/signin/verify")


@bp.route("/signin/verify", methods=["GET", "POST"])
def signin_verify():
    email = session.get("signin_email")
    if not email:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("verify.html", action="/signin/verify")

    code = request.form.get("code", "").strip()
    if not verify_code(email, code, "signin"):
        return render_template("verify.html", action="/signin/verify", error="Invalid or expired code.")

    user_id = find_or_create_user(email)
    session.pop("signin_email", None)
    session["user_id"] = user_id
    return redirect("/")


@bp.route("/signout")
def signout():
    session.pop("user_id", None)
    return redirect("/")


@bp.route("/settings")
def settings():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/signin")

    sites = get_sites_for_user(user_id)
    email = get_user_email(user_id)
    return render_template("settings.html", sites=sites, email=email)


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
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, old_lines, new_lines
    ).get_opcodes():
        if tag == "insert":
            added.extend(new_lines[j1:j2])
        elif tag == "delete":
            removed.extend(old_lines[i1:i2])
        elif tag == "replace":
            removed.extend(old_lines[i1:i2])
            added.extend(new_lines[j1:j2])

    # Skip the title line from snippets
    added = [line for line in added if not line.startswith("# ")]
    removed = [line for line in removed if not line.startswith("# ")]

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
        entries.append(
            {
                "revision": rev["revision"],
                "created_at": rev["created_at"],
                "description": description,
            }
        )
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

    unclaimed = row["user_id"] is None
    is_owner = session.get("user_id") == row["user_id"] and not unclaimed
    show_actions = is_owner or unclaimed
    html = markdown.markdown(row["content"])
    return render_template(
        "page.html",
        content=html,
        draft=row["draft"],
        slug=slug,
        show_actions=show_actions,
        unclaimed=unclaimed,
        updated_at=row["created_at"],
    )
