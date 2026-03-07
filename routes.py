import io
import json
import os
import zipfile
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape


from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from db import (
    check_username_available,
    claim_page,
    create_verification_code,
    delete_page,
    find_or_create_user,
    get_export_pages,
    get_export_pages_for_user,
    get_feed_entries,
    get_page,
    get_page_meta,
    get_pages_for_user,
    get_revision,
    get_revision_count,
    get_revisions_paginated,
    get_user,
    get_user_by_username,
    rename_page,
    set_user_username,
    save_page,
    update_user_settings,
    verify_code,
)
from db import update_user_avatar
from storage import (
    ALLOWED_IMAGE_TYPES,
    crop_square,
    delete_image,
    upload_image,
    validate_image,
)
from mail import send_verification_email
from utils import (
    RESERVED_SLUGS,
    RESERVED_USERNAMES,
    generate_slug,
    get_body,
    get_description,
    get_title,
    process_wikilinks,
    render_markdown,
    slugify,
    valid_username,
)

limiter = Limiter(get_remote_address, storage_uri="memory://")

bp = Blueprint("routes", __name__)

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "jottit.localhost:8000")


def _get_subdomain():
    host = request.host
    if host.endswith("." + BASE_DOMAIN):
        return host[: -(len(BASE_DOMAIN) + 1)]
    return None


def _compute_initials(user):
    name = user.get("name")
    if name:
        words = name.split()
        return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper()
    username = user.get("username") or ""
    return username[:2].upper()


def _base_url(path=""):
    return f"{request.scheme}://{BASE_DOMAIN}{path}"


def _subdomain_url(username, path=""):
    return f"{request.scheme}://{username}.{BASE_DOMAIN}{path}"


@bp.before_request
def validate_session():
    user_id = session.get("user_id")
    if user_id and not get_user(user_id):
        session.pop("user_id", None)


@bp.before_request
def resolve_subdomain():
    subdomain = _get_subdomain()
    if subdomain == "www":
        return redirect(f"{request.scheme}://{BASE_DOMAIN}{request.full_path}", 301)
    if not subdomain:
        g.subdomain_user = None
        return
    user = get_user_by_username(subdomain)
    if not user:
        abort(404)
    g.subdomain_user = user


@bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    from flask import current_app

    return send_from_directory(
        os.path.join(current_app.instance_path, "uploads"), filename
    )


@bp.route("/robots.txt")
def robots():
    return "User-agent: *\nAllow: /\n", 200, {"Content-Type": "text/plain"}


@bp.route("/")
def home():
    subdomain_user = g.subdomain_user
    if subdomain_user:
        return subdomain_home(subdomain_user)

    signed_in = "user_id" in session
    pages = []
    owner_avatar_url = None
    owner_initials = None
    user = None
    if signed_in:
        user_id = session["user_id"]
        pages = get_pages_for_user(user_id)
        user = get_user(user_id)
        if user:
            owner_avatar_url = user.get("avatar")
            owner_initials = _compute_initials(user)
    profile_url = (
        _subdomain_url(user["username"])
        if user and user.get("username")
        else "/settings"
    )
    return render_template(
        "home.html",
        signed_in=signed_in,
        pages=pages[:3],
        has_more_pages=len(pages) > 3,
        owner_avatar_url=owner_avatar_url,
        owner_initials=owner_initials,
        profile_url=profile_url,
    )


def subdomain_home(user):
    pages = get_pages_for_user(user["id"])
    page_list = []
    for p in pages:
        if p["draft"]:
            continue
        title = get_title(p["content"]) if p["content"] else None
        body = get_body(p["content"]) if p["content"] else ""
        description = body[:130].rsplit(" ", 1)[0] + "..." if len(body) > 130 else body
        page_list.append(
            {
                "slug": p["slug"],
                "title": title or p["slug"],
                "description": description,
                "updated_at": p["updated_at"],
            }
        )
    site_title = user.get("name") or user.get("username")
    is_owner = session.get("user_id") == user["id"]
    owner_initials = None
    owner_avatar_url = None
    if is_owner:
        owner_initials = _compute_initials(user)
        owner_avatar_url = user.get("avatar")
    return render_template(
        "subdomain_home.html",
        user=user,
        pages=page_list,
        site_title=site_title,
        is_owner=is_owner,
        owner_initials=owner_initials,
        owner_avatar_url=owner_avatar_url,
        avatar_url=user.get("avatar"),
        bio=user.get("bio"),
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
    )


@bp.route("/about")
def about():
    if g.subdomain_user:
        return view_page("about")
    return render_template("about.html", signed_in="user_id" in session)


@bp.route("/talk")
def talk():
    if g.subdomain_user:
        return view_page("talk")
    return render_template("talk.html", signed_in="user_id" in session)


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
                "title": title or p["slug"],
                "draft": p["draft"],
            }
        )
    return render_template("pages.html", pages=page_list)


@bp.route("/new")
def new_page():
    slug = generate_slug()
    return redirect(f"/{slug}/edit")


def _is_creator(page_meta):
    created_pages = session.get("created_pages", [])
    return page_meta and page_meta["id"] in created_pages


def _can_edit(page_meta):
    if not page_meta:
        return True
    if page_meta["user_id"] is not None:
        return session.get("user_id") == page_meta["user_id"]
    return _is_creator(page_meta)


@bp.route("/<slug>/edit", methods=["GET", "POST"])
@limiter.limit("30 per hour", methods=["POST"])
def edit_page(slug):
    if slug in RESERVED_SLUGS:
        abort(404)

    subdomain_user = g.subdomain_user
    if subdomain_user:
        page_meta = get_page_meta(slug)
        if not page_meta or page_meta["user_id"] != subdomain_user["id"]:
            abort(404)
    else:
        page_meta = get_page_meta(slug)

    if not _can_edit(page_meta):
        return redirect(f"/{slug}")

    if request.method == "GET":
        row = get_page(slug) if page_meta else None
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
    save_page(slug, content, draft)

    if is_new:
        new_page_meta = get_page_meta(slug)
        if new_page_meta:
            created_pages = session.get("created_pages", [])
            created_pages.append(new_page_meta["id"])
            session["created_pages"] = created_pages

            if session.get("user_id"):
                claim_page(new_page_meta["id"], session["user_id"])
                # Generate a nice slug from the title
                if title:
                    nice_slug = slugify(title)
                    if (
                        nice_slug
                        and nice_slug != slug
                        and nice_slug not in RESERVED_SLUGS
                        and not get_page_meta(nice_slug)
                    ):
                        rename_page(slug, nice_slug)
                        slug = nice_slug

    if subdomain_user:
        return redirect(f"/{slug}")
    return redirect(f"/{slug}")


@bp.route("/<slug>/claim", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def claim_page_route(slug):
    page_meta = get_page_meta(slug)
    if not page_meta or page_meta["user_id"] is not None:
        return redirect(f"/{slug}")

    if not _is_creator(page_meta):
        return redirect(f"/{slug}")

    if request.method == "GET":
        return render_template("claim.html", slug=slug)

    email = request.form.get("email", "").strip().lower()
    username = request.form.get("username", "").strip().lower()

    if not email:
        return render_template("claim.html", slug=slug, error="Email is required.")
    if not username:
        return render_template(
            "claim.html", slug=slug, error="Username is required.", email=email
        )
    if not valid_username(username):
        return render_template(
            "claim.html",
            slug=slug,
            error="Username must be lowercase letters, numbers, and hyphens only.",
            email=email,
            username=username,
        )
    if username in RESERVED_USERNAMES:
        return render_template(
            "claim.html",
            slug=slug,
            error="That username is reserved.",
            email=email,
            username=username,
        )
    if not check_username_available(username):
        return render_template(
            "claim.html",
            slug=slug,
            error="That username is already taken.",
            email=email,
            username=username,
        )

    code = create_verification_code(email, "claim")
    send_verification_email(email, code)
    session["claim_email"] = email
    session["claim_username"] = username
    return render_template(
        "verify.html", slug=slug, email=email, action=f"/{slug}/claim/verify"
    )


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

    username = session.get("claim_username")
    if username:
        existing_user = get_user(user_id)
        if existing_user and not existing_user.get("username"):
            set_user_username(user_id, username)

    claim_page(page_meta["id"], user_id)
    session.pop("claim_email", None)
    session.pop("claim_username", None)
    session["user_id"] = user_id

    # Generate a nice slug from the page title
    row = get_page(slug)
    if row:
        title = get_title(row["content"])
        if title:
            nice_slug = slugify(title)
            if (
                nice_slug
                and nice_slug != slug
                and nice_slug not in RESERVED_SLUGS
                and not get_page_meta(nice_slug)
            ):
                rename_page(slug, nice_slug)
                slug = nice_slug

    user = get_user(user_id)
    if user and user.get("username"):
        return redirect(_subdomain_url(user["username"], f"/{slug}"))
    return redirect(f"/{slug}")


@bp.route("/signin", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def signin():
    if request.method == "GET":
        return render_template("signin.html")

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("signin.html", error="Email is required.")

    code = create_verification_code(email, "signin")
    send_verification_email(email, code)
    session["signin_email"] = email
    return render_template("verify.html", email=email, action="/signin/verify")


@bp.route("/signin/verify", methods=["GET", "POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def signin_verify():
    email = request.form.get("email") or session.get("signin_email")
    if not email:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("verify.html", email=email, action="/signin/verify")

    code = request.form.get("code", "").strip()
    if not verify_code(email, code, "signin"):
        return render_template(
            "verify.html",
            email=email,
            action="/signin/verify",
            error="Invalid or expired code.",
        )

    user_id = find_or_create_user(email)
    session.pop("signin_email", None)
    session["user_id"] = user_id
    return redirect("/")


@bp.route("/signout", methods=["POST"])
def signout():
    session.pop("user_id", None)
    return redirect("/")


def _require_user():
    user_id = session.get("user_id")
    if not user_id:
        return None, None
    user = get_user(user_id)
    if not user:
        return None, None
    return user_id, user


@bp.route("/settings")
def user_settings():
    user_id, user = _require_user()
    if not user:
        return redirect("/signin")

    back_url = _subdomain_url(user["username"]) if user.get("username") else "/"
    return render_template("settings.html", user=user, back_url=back_url)


@bp.route("/settings/profile", methods=["GET", "POST"])
def settings_profile():
    user_id, user = _require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_profile.html", user=user)

    name = request.form.get("name", "").strip()
    bio = request.form.get("bio", "").strip()

    update_user_settings(user_id, name, user.get("username") or "", bio)
    flash("Profile saved")
    return redirect("/settings/profile")


@bp.route("/settings/subdomain", methods=["GET", "POST"])
def settings_subdomain():
    user_id, user = _require_user()
    if not user:
        return redirect("/signin")

    if request.method == "GET":
        return render_template("settings_subdomain.html", user=user)

    username = request.form.get("username", "").strip().lower()

    error = None
    if username and username != user.get("username"):
        if not valid_username(username):
            error = "Username must be lowercase letters, numbers, and hyphens only."
        elif username in RESERVED_USERNAMES:
            error = "That username is reserved."
        elif not check_username_available(username):
            error = "That username is already taken."

    if error:
        return render_template(
            "settings_subdomain.html",
            user={**user, "username": username},
            error=error,
        )

    update_user_settings(
        user_id, user.get("name") or "", username, user.get("bio") or ""
    )
    flash("Subdomain saved")
    return redirect("/settings/subdomain")


@bp.route("/settings/export")
def settings_export():
    user_id, user = _require_user()
    if not user:
        return redirect("/signin")

    return render_template("settings_export.html")


@bp.route("/settings/avatar", methods=["POST"])
def settings_avatar():
    user_id, user = _require_user()
    if not user:
        return redirect("/signin")

    file = request.files.get("avatar")
    if not file:
        return redirect("/settings/profile")

    error = validate_image(file)
    if error:
        return render_template("settings_profile.html", user=user, error=f"{error}.")

    ext = ALLOWED_IMAGE_TYPES[file.content_type]
    fmt = file.content_type.split("/")[-1].upper()
    if fmt == "JPG":
        fmt = "JPEG"
    cropped = crop_square(file, fmt)
    key = f"{user_id}/avatar.{ext}"
    url = upload_image(key, cropped, file.content_type)
    update_user_avatar(user_id, url)
    flash("Avatar updated")
    return redirect("/settings/profile")


@bp.route("/settings/avatar/delete", methods=["POST"])
def settings_avatar_delete():
    user_id, user = _require_user()
    if not user:
        return redirect("/signin")

    if user.get("avatar"):
        url = user["avatar"]
        if url.startswith("/uploads/"):
            key = url.removeprefix("/uploads/")
        else:
            key = "/".join(url.split("/")[3:])
        if key:
            delete_image(key)
        update_user_avatar(user_id, None)
    flash("Avatar removed")
    return redirect("/settings/profile")


@bp.route("/<slug>/export")
def export_page_route(slug):
    page_meta = get_page_meta(slug)
    if not page_meta:
        abort(404)
    if not _can_edit(page_meta):
        return redirect(f"/{slug}")

    pages = get_export_pages(slug)
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


@bp.route("/<slug>/history")
def page_history(slug):
    subdomain_user = g.subdomain_user
    if subdomain_user:
        page_meta = get_page_meta(slug)
        if not page_meta or page_meta["user_id"] != subdomain_user["id"]:
            abort(404)

    total = get_revision_count(slug)
    if total == 0:
        abort(404)

    per_page = 6
    page = request.args.get("page", 1, type=int)
    total_pages = (total + per_page - 1) // per_page
    page = max(1, min(page, total_pages))

    revisions = get_revisions_paginated(slug, page, per_page)

    paginated = []
    for rev in revisions:
        word_count = rev["word_count"]
        prev_word_count = rev["prev_word_count"]
        delta = word_count - prev_word_count if prev_word_count is not None else None
        paginated.append(
            {
                "revision": rev["revision"],
                "created_at": rev["created_at"],
                "delta": delta,
            }
        )

    return render_template(
        "history.html",
        slug=slug,
        revisions=paginated,
        page=page,
        total_pages=total_pages,
        is_subdomain=subdomain_user is not None,
    )


@bp.route("/<slug>/history/<int:revision>")
def view_revision(slug, revision):
    subdomain_user = g.subdomain_user
    if subdomain_user:
        page_meta = get_page_meta(slug)
        if not page_meta or page_meta["user_id"] != subdomain_user["id"]:
            abort(404)

    row = get_revision(slug, revision)
    if not row:
        abort(404)

    html = render_markdown(process_wikilinks(row["content"]))
    return render_template(
        "revision.html",
        content=html,
        slug=slug,
        revision=row["revision"],
        created_at=row["created_at"],
        is_subdomain=subdomain_user is not None,
    )


def _build_feed_entries(slug):
    entries = get_feed_entries(slug)
    base_url = request.url_root.rstrip("/")
    page_url = f"{base_url}/{slug}"
    items = []
    for entry in entries:
        body = get_body(entry["content"])
        items.append(
            {
                "title": get_title(entry["content"]) or slug,
                "url": page_url,
                "body": body,
                "body_html": render_markdown(process_wikilinks(body)),
                "created_at": entry["created_at"],
            }
        )
    return items, page_url


@bp.route("/<slug>/feed.xml")
def rss_feed(slug):
    page_meta = get_page_meta(slug)
    if not page_meta:
        abort(404)

    items, page_url = _build_feed_entries(slug)
    page_title = get_title(get_page(slug)["content"]) if get_page(slug) else slug

    last_build_date = format_datetime(items[0]["created_at"]) if items else ""

    items_xml = []
    for item in items:
        cdata_body = item["body_html"].replace("]]>", "]]]]><![CDATA[>")
        items_xml.append(
            "    <item>\n"
            f"      <title>{xml_escape(item['title'])}</title>\n"
            f"      <link>{xml_escape(item['url'])}</link>\n"
            f"      <pubDate>{format_datetime(item['created_at'])}</pubDate>\n"
            f"      <description><![CDATA[{cdata_body}]]></description>\n"
            f"      <source:markdown>{xml_escape(item['body'])}</source:markdown>\n"
            f'      <guid isPermaLink="true">{xml_escape(item["url"])}</guid>\n'
            "    </item>"
        )

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:source="http://source.scripting.com/">',
        "  <channel>",
        f"    <title>{xml_escape(page_title)}</title>",
        f"    <link>{xml_escape(page_url)}</link>",
        "    <description></description>",
        f"    <lastBuildDate>{last_build_date}</lastBuildDate>",
    ]
    parts.extend(items_xml)
    parts.append("  </channel>")
    parts.append("</rss>")
    xml = "\n".join(parts)

    return Response(xml, content_type="application/rss+xml; charset=utf-8")


@bp.route("/<slug>/feed.json")
def json_feed(slug):
    page_meta = get_page_meta(slug)
    if not page_meta:
        abort(404)

    items, page_url = _build_feed_entries(slug)
    page_title = get_title(get_page(slug)["content"]) if get_page(slug) else slug

    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": page_title,
        "home_page_url": page_url,
        "feed_url": f"{page_url}/feed.json",
        "items": [
            {
                "id": item["url"],
                "url": item["url"],
                "title": item["title"],
                "content_html": item["body_html"],
                "date_published": item["created_at"].isoformat(),
                "_source_markdown": item["body"],
            }
            for item in items
        ],
    }

    return Response(
        json.dumps(feed), content_type="application/feed+json; charset=utf-8"
    )


@bp.route("/<slug>/delete", methods=["GET", "POST"])
def delete_page_route(slug):
    page_meta = get_page_meta(slug)
    if not page_meta:
        return redirect("/")

    user_id = session.get("user_id")
    if not page_meta["user_id"] or page_meta["user_id"] != user_id:
        return redirect(f"/{slug}")

    if request.method == "GET":
        page_title = None
        row = get_page(slug)
        if row:
            page_title = get_title(row["content"])
        return render_template(
            "delete_page.html", slug=slug, page_title=page_title or slug
        )

    confirmation = request.form.get("confirmation", "").strip()
    if confirmation != "delete":
        page_title = None
        row = get_page(slug)
        if row:
            page_title = get_title(row["content"])
        return render_template(
            "delete_page.html",
            slug=slug,
            page_title=page_title or slug,
            error='Please type "delete" to confirm.',
        )

    delete_page(slug)
    return redirect(_base_url("/"))


@bp.route("/<slug>")
def view_page(slug):
    subdomain_user = g.subdomain_user

    if subdomain_user:
        page_meta = get_page_meta(slug)
        if not page_meta or page_meta["user_id"] != subdomain_user["id"]:
            abort(404)
    else:
        page_meta = get_page_meta(slug)
        if page_meta and page_meta["user_id"] is not None:
            user = get_user(page_meta["user_id"])
            if user and user.get("username"):
                return redirect(_subdomain_url(user["username"], f"/{slug}"))

    if not page_meta:
        abort(404)

    row = get_page(slug)
    if not row:
        abort(404)

    unclaimed = page_meta["user_id"] is None
    is_owner = session.get("user_id") == page_meta["user_id"] and not unclaimed
    is_creator = _is_creator(page_meta)

    if row["draft"] and not is_owner and not is_creator:
        abort(404)

    show_actions = is_owner or is_creator

    page_title = get_title(row["content"])
    page_description = get_description(row["content"])
    content = process_wikilinks(row["content"])
    html = render_markdown(content)
    html = html.replace("<h1>", '<h1 class="p-name">', 1)

    site_title = None
    avatar_url = None
    bio = None
    if subdomain_user:
        site_title = subdomain_user.get("name") or subdomain_user.get("username")
        avatar_url = subdomain_user.get("avatar")
        bio = subdomain_user.get("bio")

    owner_initials = None
    owner_avatar_url = None
    if is_owner:
        user = get_user(session["user_id"])
        if user:
            owner_initials = _compute_initials(user)
            owner_avatar_url = user.get("avatar")

    return render_template(
        "page.html",
        content=html,
        draft=row["draft"],
        slug=slug,
        show_actions=show_actions,
        unclaimed=unclaimed and is_creator,
        is_owner=is_owner,
        owner_initials=owner_initials,
        owner_avatar_url=owner_avatar_url,
        avatar_url=avatar_url,
        bio=bio,
        updated_at=row["created_at"],
        page_title=page_title,
        page_description=page_description,
        site_title=site_title,
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
        has_history=get_revision_count(slug) > 1,
        is_subdomain=subdomain_user is not None,
    )
