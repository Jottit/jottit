import io
import zipfile

from flask import Response, abort, g, redirect, render_template, request, session

from db import (
    check_username_available,
    claim_page,
    create_verification_code,
    delete_page,
    find_or_create_user,
    find_page_owner_for_redirect,
    get_export_pages,
    get_export_pages_for_user,
    get_page,
    get_page_meta,
    get_pages_for_user,
    get_user,
    rename_page,
    save_page,
    set_user_username,
    update_page_listing,
    update_user_settings,
    verify_code,
)
from mail import send_verification_email
from utils import (
    RESERVED_SLUGS,
    RESERVED_USERNAMES,
    generate_slug,
    get_body,
    get_title,
    slugify,
    valid_email,
    valid_username,
)
from routes import (
    bp,
    limiter,
    LISTING_OPTIONS,
    can_edit,
    find_page,
    is_creator,
    subdomain_url,
    base_url,
)


@bp.route("/api/check-username")
def check_username_route():
    username = request.args.get("username", "").strip().lower()
    if not username:
        return {"available": False}
    if not valid_username(username):
        return {
            "available": False,
            "error": "Username must be lowercase letters, numbers, and hyphens only.",
        }
    if username in RESERVED_USERNAMES:
        return {"available": False, "error": "That username is reserved."}
    if not check_username_available(username):
        return {"available": False, "error": "That username is already taken."}
    return {"available": True}


@bp.route("/pages")
def pages_list():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/signin")
    pages = get_pages_for_user(user_id)
    page_list = []
    for p in pages:
        title = get_title(p["content"]) if p["content"] else None
        page_list.append(
            {
                "slug": p["slug"],
                "title": title or "",
                "draft": p["draft"],
            }
        )
    return render_template("pages.html", pages=page_list)


@bp.route("/new", methods=["GET", "POST"])
@limiter.limit("30 per hour", methods=["POST"])
def new_page():
    subdomain_user = g.subdomain_user

    if request.method == "GET":
        return render_template(
            "edit.html",
            slug=None,
            title="",
            content="",
            draft=False,
            is_new=True,
            is_subdomain=subdomain_user is not None,
        )

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    draft = "draft" in request.form

    if title:
        content = f"# {title}\n\n{content}"

    subdomain_user_id = subdomain_user["id"] if subdomain_user else None
    owner_id = subdomain_user_id or session.get("user_id")
    reserved = RESERVED_SLUGS if not subdomain_user else set()
    slug = None
    if title:
        nice_slug = slugify(title)
        if nice_slug and nice_slug not in reserved:
            if not owner_id or not get_page_meta(nice_slug, owner_id):
                slug = nice_slug
    if not slug:
        slug = generate_slug()

    slug = save_page(slug, content, draft, subdomain_user_id)
    _track_new_page(slug, subdomain_user_id)

    return redirect(f"/{slug}")


def _track_new_page(slug, subdomain_user_id):
    new_page_meta = get_page_meta(slug, subdomain_user_id)
    if not new_page_meta:
        return
    created_pages = session.get("created_pages", [])
    created_pages.append(new_page_meta["id"])
    session["created_pages"] = created_pages
    if session.get("user_id") and not subdomain_user_id:
        claim_page(new_page_meta["id"], session["user_id"])
    return new_page_meta


@bp.route("/<slug>/edit", methods=["GET", "POST"])
@limiter.limit("30 per hour", methods=["POST"])
def edit_page(slug):
    subdomain_user = g.subdomain_user
    if slug in RESERVED_SLUGS and not subdomain_user:
        abort(404)
    page_meta = find_page(slug)

    if not page_meta and not subdomain_user:
        owner_user_id = find_page_owner_for_redirect(slug)
        if owner_user_id:
            user = get_user(owner_user_id)
            if user and user.get("username"):
                return redirect(subdomain_url(user["username"], f"/{slug}/edit"))
            return redirect(f"/{slug}")

    if not can_edit(page_meta):
        return redirect(f"/{slug}")

    if request.method == "GET":
        row = get_page(page_meta["id"]) if page_meta else None
        content = row["content"] if row else ""
        draft = row["draft"] if row else False
        title = get_title(content) or ""
        content = get_body(content)
        return render_template(
            "edit.html",
            slug=slug,
            title=title,
            content=content,
            draft=draft,
            is_new=page_meta is None,
            is_subdomain=subdomain_user is not None,
        )

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    draft = "draft" in request.form

    if title:
        content = f"# {title}\n\n{content}"

    is_new = page_meta is None
    subdomain_user_id = subdomain_user["id"] if subdomain_user else None
    slug = save_page(slug, content, draft, subdomain_user_id)

    if is_new:
        new_page_meta = _track_new_page(slug, subdomain_user_id)
        if new_page_meta:
            effective_user_id = subdomain_user_id or session.get("user_id")
            if effective_user_id and title:
                nice_slug = slugify(title)
                reserved = RESERVED_SLUGS if not subdomain_user else set()
                if (
                    nice_slug
                    and nice_slug != slug
                    and nice_slug not in reserved
                    and not get_page_meta(nice_slug, effective_user_id)
                ):
                    rename_page(new_page_meta["id"], nice_slug)
                    slug = nice_slug

    return redirect(f"/{slug}")


@bp.route("/<slug>/claim", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def claim_page_route(slug):
    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    if not is_creator(page_meta):
        return redirect(f"/{slug}")

    if request.method == "GET":
        return render_template("claim.html", slug=slug)

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("claim.html", slug=slug, error="Email is required.")
    if not valid_email(email):
        return render_template(
            "claim.html", slug=slug, error="Please enter a valid email address."
        )

    code = create_verification_code(email, "claim")
    send_verification_email(email, code)
    session["claim_email"] = email
    return redirect(f"/{slug}/claim/verify")


@bp.route("/<slug>/claim/verify", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def claim_verify(slug):
    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    email = request.form.get("email") or session.get("claim_email")
    if not email:
        return redirect(f"/{slug}/claim")

    session_email = session.get("claim_email")
    form_email = request.form.get("email")
    if session_email and form_email and form_email != session_email:
        return redirect(f"/{slug}/claim")

    if request.method == "GET":
        return render_template(
            "verify.html", slug=slug, email=email, action=f"/{slug}/claim/verify"
        )

    code = request.form.get("code", "").strip()
    if not verify_code(email, code, "claim"):
        return render_template(
            "verify.html",
            slug=slug,
            email=email,
            action=f"/{slug}/claim/verify",
            error="Invalid or expired code.",
        )

    user_id = find_or_create_user(email)
    session["user_id"] = user_id

    user = get_user(user_id)
    if user and user.get("username"):
        return _finish_claim(slug, page_meta, user_id, user["username"])

    session["claim_verified"] = True
    return redirect(f"/{slug}/claim/setup")


def _finish_claim(slug, page_meta, user_id, username):
    claim_page(page_meta["id"], user_id)

    row = get_page(page_meta["id"])
    if row:
        title = get_title(row["content"])
        if title:
            nice_slug = slugify(title)
            if (
                nice_slug
                and nice_slug != slug
                and nice_slug not in RESERVED_SLUGS
                and not get_page_meta(nice_slug, user_id)
            ):
                rename_page(page_meta["id"], nice_slug)
                slug = nice_slug

    session.pop("claim_email", None)
    session.pop("claim_verified", None)
    session.pop("claim_name", None)
    return redirect(subdomain_url(username, f"/{slug}"))


@bp.route("/<slug>/claim/setup", methods=["GET", "POST"])
def claim_setup(slug):
    if not session.get("claim_verified") or not session.get("user_id"):
        return redirect(f"/{slug}/claim")

    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    if request.method == "GET":
        return render_template("claim_setup.html", slug=slug)

    name = request.form.get("name", "").strip()
    if not name:
        return render_template("claim_setup.html", slug=slug, error="Name is required.")

    session["claim_name"] = name
    return redirect(f"/{slug}/claim/address")


@bp.route("/<slug>/claim/address", methods=["GET", "POST"])
def claim_address(slug):
    if not session.get("claim_verified") or not session.get("user_id"):
        return redirect(f"/{slug}/claim")
    if not session.get("claim_name"):
        return redirect(f"/{slug}/claim/setup")

    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    if request.method == "GET":
        return render_template("claim_address.html", slug=slug)

    username = request.form.get("username", "").strip().lower()

    if not username:
        return render_template(
            "claim_address.html", slug=slug, error="Address is required."
        )
    if not valid_username(username):
        return render_template(
            "claim_address.html",
            slug=slug,
            error="Username must be lowercase letters, numbers, and hyphens only.",
            username=username,
        )
    if username in RESERVED_USERNAMES:
        return render_template(
            "claim_address.html",
            slug=slug,
            error="That username is reserved.",
            username=username,
        )
    if not check_username_available(username):
        return render_template(
            "claim_address.html",
            slug=slug,
            error="That username is already taken.",
            username=username,
        )

    user_id = session["user_id"]
    name = session["claim_name"]
    set_user_username(user_id, username)
    update_user_settings(user_id, name=name, username=username, bio="", license=None)
    return _finish_claim(slug, page_meta, user_id, username)


@bp.route("/<slug>/delete", methods=["GET", "POST"])
def delete_page_route(slug):
    page_meta = find_page(slug)
    if not page_meta:
        return redirect("/")

    user_id = session.get("user_id")
    if not page_meta["user_id"] or page_meta["user_id"] != user_id:
        return redirect(f"/{slug}")

    row = get_page(page_meta["id"])
    page_title = get_title(row["content"]) if row else None

    if request.method == "GET":
        return render_template(
            "delete_page.html", slug=slug, page_title=page_title or slug
        )

    delete_page(page_meta["id"])
    if g.subdomain_user:
        return redirect(subdomain_url(g.subdomain_user["username"]))
    return redirect(base_url("/"))


@bp.route("/<slug>/listing", methods=["POST"])
def update_listing(slug):
    page_meta = find_page(slug)
    if not page_meta:
        abort(404)

    user_id = session.get("user_id")
    if not page_meta["user_id"] or page_meta["user_id"] != user_id:
        abort(403)

    listing = request.form.get("listing", "listed")
    if listing not in LISTING_OPTIONS:
        listing = "listed"

    update_page_listing(page_meta["id"], listing)

    if request.headers.get("X-Requested-With") == "fetch":
        return "", 204

    return redirect(f"/{slug}")


@bp.route("/<slug>/export")
def export_page_route(slug):
    page_meta = find_page(slug)
    if not page_meta:
        abort(404)
    if not can_edit(page_meta):
        return redirect(f"/{slug}")

    pages = get_export_pages(page_meta["id"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in pages:
            title = get_title(p["content"]) or slug
            body = get_body(p["content"])
            date = p["created_at"].strftime("%Y-%m-%d")
            md = f"---\ntitle: {title}\ndate: {date}\n---\n\n{body}\n"
            zf.writestr(f"{slug}.md", md)
    buf.seek(0)

    return Response(
        buf.getvalue(),
        content_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@bp.route("/export")
def export_all():
    user_id = session.get("user_id")
    if not user_id:
        return redirect("/signin")
    pages = get_export_pages_for_user(user_id)
    user = get_user(user_id)
    name = (user.get("username") or "jottit") if user else "jottit"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in pages:
            title = get_title(p["content"]) or p["slug"]
            body = get_body(p["content"])
            date = p["created_at"].strftime("%Y-%m-%d")
            md = f"---\ntitle: {title}\ndate: {date}\n---\n\n{body}\n"
            zf.writestr(f"{name}/{p['slug']}.md", md)
    buf.seek(0)

    return Response(
        buf.getvalue(),
        content_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )
