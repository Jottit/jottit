import io
import zipfile

from flask import (
    Response,
    abort,
    g,
    make_response,
    redirect,
    render_template,
    request,
    session,
)

from db import (
    check_username_available,
    claim_page,
    create_page_secret,
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
    update_page_visibility,
    update_user_settings,
    verify_code,
    verify_page_secret,
)
from utils import (
    MAX_CONTENT_LENGTH,
    RESERVED_SLUGS,
    RESERVED_USERNAMES,
    generate_slug,
    get_body,
    get_title,
    is_random_slug,
    slugify,
    valid_email,
    valid_username,
)
from routes import (
    bp,
    limiter,
    VISIBILITY_OPTIONS,
    _set_profile_user,
    base_url,
    can_edit,
    find_page,
    profile_url,
    send_verification,
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
    user = g.current_user
    username = user.get("username") if user else None
    pages = get_pages_for_user(user_id)
    page_list = []
    for p in pages:
        title = get_title(p["content"]) if p["content"] else None
        page_list.append(
            {
                "slug": p["slug"],
                "title": title or "",
                "visibility": p["visibility"],
            }
        )
    return render_template("pages.html", pages=page_list, username=username)


# --- @username routes for site actions ---


@bp.route("/@<username>/new", methods=["GET", "POST"])
def profile_new_page(username):
    _set_profile_user(username)
    return new_page()


@bp.route("/@<username>/<slug>/edit", methods=["GET", "POST"])
def profile_edit_page(username, slug):
    _set_profile_user(username)
    return edit_page(slug)


@bp.route("/@<username>/<slug>/delete", methods=["GET", "POST"])
def profile_delete_page(username, slug):
    _set_profile_user(username)
    return delete_page_route(slug)


@bp.route("/@<username>/<slug>/visibility", methods=["POST"])
def profile_update_visibility(username, slug):
    _set_profile_user(username)
    return update_visibility(slug)


@bp.route("/@<username>/<slug>/export")
def profile_export_page(username, slug):
    _set_profile_user(username)
    return export_page_route(slug)


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
            is_new=True,
            is_subdomain=subdomain_user is not None,
        )

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()[:MAX_CONTENT_LENGTH]

    if title:
        content = f"# {title}\n\n{content}"

    subdomain_user_id = subdomain_user["id"] if subdomain_user else None
    owner_id = subdomain_user_id or session.get("user_id")
    reserved = RESERVED_SLUGS if not subdomain_user else set()
    slug = None
    if owner_id and title:
        nice_slug = slugify(title)
        if nice_slug and nice_slug not in reserved:
            if not get_page_meta(nice_slug, owner_id):
                slug = nice_slug
    if not slug:
        slug = generate_slug()

    visibility = "listed" if owner_id else "unlisted"
    slug = save_page(slug, content, visibility, subdomain_user_id)

    new_page_meta = get_page_meta(slug, subdomain_user_id)
    if new_page_meta and session.get("user_id") and not subdomain_user_id:
        claim_page(new_page_meta["id"], session["user_id"])

    resp = make_response(redirect(f"{g.url_prefix}/{slug}"))
    if not owner_id and new_page_meta:
        secret = create_page_secret(new_page_meta["id"])
        resp.set_cookie(
            f"page_token_{slug}",
            secret,
            httponly=True,
            samesite="Lax",
            max_age=30 * 24 * 3600,
        )
    return resp


@bp.route("/<slug>/edit", methods=["GET", "POST"])
@limiter.limit("30 per 5 minutes", methods=["POST"])
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
                return redirect(profile_url(user["username"], f"/{slug}/edit"))
            return redirect(f"/{slug}")

    # Allow editing unclaimed pages via token (e.g. from CLI publish output URL).
    # On first visit with ?token=, validate and move to a httponly cookie to avoid
    # leaking the secret in Referer headers, browser history, and server logs.
    query_token = request.args.get("token", "")
    if query_token and page_meta and page_meta["user_id"] is None:
        if verify_page_secret(slug, query_token) is not None:
            resp = make_response(redirect(f"{g.url_prefix}/{slug}/edit"))
            resp.set_cookie(
                f"page_token_{slug}",
                query_token,
                httponly=True,
                samesite="Lax",
                max_age=30 * 24 * 3600,
            )
            return resp

    token = request.cookies.get(f"page_token_{slug}", "")
    token_valid = (
        bool(token)
        and page_meta is not None
        and page_meta["user_id"] is None
        and verify_page_secret(slug, token) is not None
    )

    if not can_edit(page_meta) and not token_valid:
        return redirect(f"{g.url_prefix}/{slug}")

    if request.method == "GET":
        row = get_page(page_meta["id"]) if page_meta else None
        content = row["content"] if row else ""
        title = get_title(content) or ""
        content = get_body(content)
        return render_template(
            "edit.html",
            slug=slug,
            title=title,
            content=content,
            is_new=page_meta is None,
            is_subdomain=subdomain_user is not None,
        )

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()[:MAX_CONTENT_LENGTH]

    if title:
        content = f"# {title}\n\n{content}"

    is_new = page_meta is None
    subdomain_user_id = subdomain_user["id"] if subdomain_user else None
    # Preserve existing visibility on edit; default to "listed" for new pages
    visibility = page_meta["visibility"] if page_meta else "listed"
    slug = save_page(slug, content, visibility, subdomain_user_id)

    if is_new:
        new_page_meta = get_page_meta(slug, subdomain_user_id)
        if new_page_meta and session.get("user_id") and not subdomain_user_id:
            claim_page(new_page_meta["id"], session["user_id"])
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
    elif title and is_random_slug(slug):
        effective_user_id = subdomain_user_id or session.get("user_id")
        if effective_user_id:
            nice_slug = slugify(title)
            reserved = RESERVED_SLUGS if not subdomain_user else set()
            if (
                nice_slug
                and nice_slug not in reserved
                and not get_page_meta(nice_slug, effective_user_id)
            ):
                rename_page(page_meta["id"], nice_slug)
                slug = nice_slug

    resp = make_response(redirect(f"{g.url_prefix}/{slug}"))
    if is_new and not (subdomain_user_id or session.get("user_id")):
        new_meta = get_page_meta(slug, subdomain_user_id) if not new_page_meta else new_page_meta
        if new_meta:
            secret = create_page_secret(new_meta["id"])
            resp.set_cookie(
                f"page_token_{slug}",
                secret,
                httponly=True,
                samesite="Lax",
                max_age=30 * 24 * 3600,
            )
    return resp


@bp.route("/<slug>/claim", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def claim_page_route(slug):
    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    # Only allow claiming if the visitor has a valid page token cookie
    token = request.cookies.get(f"page_token_{slug}", "")
    if not token or verify_page_secret(slug, token) is None:
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

    send_verification(email, "claim")
    return redirect(f"/{slug}/claim/verify")


@bp.route("/<slug>/claim/verify", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def claim_verify(slug):
    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    email = (
        (request.form.get("email") or session.get("claim_email") or "").strip().lower()
    )
    if not email:
        return redirect(f"/{slug}/claim")

    session_email = session.get("claim_email")
    form_email = (request.form.get("email") or "").strip().lower()
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
    update_page_visibility(page_meta["id"], "listed")

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
    return redirect(f"/@{username}/{slug}")


@bp.route("/<slug>/claim/setup", methods=["GET", "POST"])
def claim_setup(slug):
    if not session.get("claim_verified") or not session.get("user_id"):
        return redirect(f"/{slug}/claim")

    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    if request.method == "GET":
        return render_template("claim_setup.html", slug=slug)

    name = request.form.get("name", "").strip()[:100]
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
@limiter.limit("5 per 5 minutes", methods=["POST"])
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
    user = get_user(user_id) if user_id else None
    if user and user.get("username"):
        return redirect(profile_url(user["username"]))
    return redirect(base_url("/"))


@bp.route("/<slug>/visibility", methods=["POST"])
@limiter.limit("30 per minute", methods=["POST"])
def update_visibility(slug):
    page_meta = find_page(slug)
    if not page_meta:
        abort(404)

    user_id = session.get("user_id")
    if not page_meta["user_id"] or page_meta["user_id"] != user_id:
        abort(403)

    visibility = request.form.get("visibility", "listed")
    if visibility not in VISIBILITY_OPTIONS:
        visibility = "listed"

    update_page_visibility(page_meta["id"], visibility)

    if request.headers.get("X-Requested-With") == "fetch":
        return "", 204

    return redirect(f"{g.url_prefix}/{slug}")


@bp.route("/<slug>/export")
def export_page_route(slug):
    page_meta = find_page(slug)
    if not page_meta:
        abort(404)
    if not can_edit(page_meta):
        return redirect(f"{g.url_prefix}/{slug}")

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
