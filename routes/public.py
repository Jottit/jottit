import json
import os
from collections import Counter
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

from flask import (
    Response,
    abort,
    current_app,
    g,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)

from db import (
    get_feed_entries,
    get_feed_entries_for_site,
    get_feed_entries_for_user,
    get_page,
    get_page_full,
    get_page_meta,
    get_pages_for_site,
    get_pages_for_user,
    get_public_pages,
    get_revision,
    get_revision_count,
    get_revisions_paginated,
    get_user,
    find_page_by_original_slug,
    find_page_owner_for_redirect,
    verify_page_secret,
)
from utils import (
    get_body,
    get_description,
    get_title,
    reading_time,
    render_bio,
    render_markdown,
)
from routes import (
    bp,
    BASE_DOMAIN,
    LICENSES,
    _set_profile_user,
    account_link_vars,
    compute_initials,
    find_page,
    has_page_token,
    can_edit,
    profile_url,
    subdomain_url,
)


@bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(
        os.path.join(current_app.instance_path, "uploads"), filename
    )


@bp.route("/install-cli")
def install_cli():
    return send_from_directory("static", "install-cli.sh", mimetype="text/plain")


_VISIBILITY_TABS = ("all", "private", "unlisted", "listed", "pinned")


@bp.route("/")
def home():
    site = getattr(g, "site", None)
    if site:
        return _site_home(site)

    if "user_id" not in session:
        return render_template("home.html", **account_link_vars())

    pages = get_pages_for_user(session["user_id"])
    all_items = [_build_page_item(p) for p in pages]

    counts = Counter(i["visibility"] for i in all_items)
    counts["all"] = len(all_items)

    tab = request.args.get("tab", "all")
    if tab not in _VISIBILITY_TABS:
        tab = "all"

    if tab == "all":
        page_list = all_items
    else:
        page_list = [i for i in all_items if i["visibility"] == tab]

    user = g.current_user
    display_name = (user.get("name") or user.get("username")) if user else None

    return render_template(
        "home.html",
        pages=page_list,
        tab=tab,
        counts=counts,
        display_name=display_name,
        **account_link_vars(),
    )


def _site_home(site):
    is_owner = session.get("user_id") == site["user_id"]

    if site["visibility"] == "private" and not is_owner:
        return render_template("site_private.html", base_url=f"{request.scheme}://{BASE_DOMAIN}"), 403

    user = g.subdomain_user

    # If home page is set, render it
    if site.get("home_page_id"):
        row = get_page_full(site["home_page_id"])
        if row:
            page_meta = get_page_meta(None, site_id=site["id"])
            # Find the actual page meta for this home page
            from db import get_db
            with get_db() as conn:
                page_meta = conn.execute(
                    "SELECT id, slug, user_id, site_id, visibility FROM pages WHERE id = %s",
                    (site["home_page_id"],),
                ).fetchone()
            if page_meta:
                return _render_page(page_meta, row, user, site, is_owner)

    # Otherwise show chronological feed
    if is_owner:
        pages = get_pages_for_site(site["id"])
        items = [_build_page_item(p) for p in pages]
    else:
        pages = get_pages_for_site(site["id"])
        items = [
            _build_page_item(p)
            for p in pages
            if p["visibility"] in ("listed", "pinned")
        ]

    pinned = [i for i in items if i.get("pinned")]
    listed = [i for i in items if not i.get("pinned")]
    page_list = pinned + listed

    site_title = user.get("name") or user.get("username")
    owner_initials = None
    owner_avatar_url = None
    profile_incomplete = False
    if is_owner:
        owner_initials = compute_initials(user)
        owner_avatar_url = user.get("avatar")
        if not user.get("avatar") and not user.get("bio"):
            profile_incomplete = True
    bio = user.get("bio")
    bio_html = render_bio(bio, g.url_prefix) if bio else ""
    license_info = LICENSES.get(site.get("license") or "")
    return render_template(
        "profile.html",
        user=user,
        pages=page_list,
        site_title=site_title,
        is_owner=is_owner,
        owner_initials=owner_initials,
        owner_avatar_url=owner_avatar_url,
        profile_incomplete=profile_incomplete,
        avatar_url=user.get("avatar"),
        bio_html=bio_html,
        license_info=license_info,
        profile_url=profile_url(user["username"]) if user.get("username") else None,
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
        is_subdomain=True,
    )


def _build_page_item(p):
    title = get_title(p["content"]) if p["content"] else None
    return {
        "slug": p["slug"],
        "title": title or "",
        "description": get_description(p["content"], max_length=350),
        "reading_time": reading_time(p["content"]),
        "updated_at": p["updated_at"],
        "visibility": p["visibility"],
        "pinned": p["visibility"] == "pinned",
    }


def subdomain_home(user):
    pages = get_pages_for_user(user["id"])
    pinned = []
    listed = []
    for p in pages:
        if p["visibility"] not in ("listed", "pinned"):
            continue
        item = _build_page_item(p)
        if p["visibility"] == "pinned":
            pinned.append(item)
        else:
            listed.append(item)
    page_list = pinned + listed

    site_title = user.get("name") or user.get("username")
    is_owner = session.get("user_id") == user["id"]
    owner_initials = None
    owner_avatar_url = None
    profile_incomplete = False
    if is_owner:
        owner_initials = compute_initials(user)
        owner_avatar_url = user.get("avatar")
        if not user.get("avatar") and not user.get("bio"):
            profile_incomplete = True
    bio = user.get("bio")
    bio_html = render_bio(bio, g.url_prefix) if bio else ""

    # Get license from the user's default site
    from db import get_default_site_for_user
    default_site = get_default_site_for_user(user["id"])
    license_key = default_site.get("license") if default_site else None

    return render_template(
        "profile.html",
        user=user,
        pages=page_list,
        site_title=site_title,
        is_owner=is_owner,
        owner_initials=owner_initials,
        owner_avatar_url=owner_avatar_url,
        profile_incomplete=profile_incomplete,
        avatar_url=user.get("avatar"),
        bio_html=bio_html,
        license_info=LICENSES.get(license_key or ""),
        profile_url=profile_url(user["username"]) if user.get("username") else None,
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
    )


# --- @username routes ---


@bp.route("/@<username>")
def profile_home(username):
    user = _set_profile_user(username)
    return subdomain_home(user)


@bp.route("/@<username>/<slug>")
def profile_view_page(username, slug):
    # 301 redirect to subdomain canonical URL
    return redirect(subdomain_url(username, f"/{slug}"), 301)


@bp.route("/@<username>/<slug>/history")
def profile_page_history(username, slug):
    return redirect(subdomain_url(username, f"/{slug}/history"), 301)


@bp.route("/@<username>/<slug>/history/<int:revision>")
def profile_view_revision(username, slug, revision):
    return redirect(subdomain_url(username, f"/{slug}/history/{revision}"), 301)


@bp.route("/@<username>/<slug>/feed.xml")
def profile_rss_feed(username, slug):
    return redirect(subdomain_url(username, f"/{slug}/feed.xml"), 301)


@bp.route("/@<username>/<slug>/feed.json")
def profile_json_feed(username, slug):
    return redirect(subdomain_url(username, f"/{slug}/feed.json"), 301)


@bp.route("/@<username>/feed.xml")
def profile_site_rss_feed(username):
    return redirect(subdomain_url(username, "/feed.xml"), 301)


@bp.route("/@<username>/feed.json")
def profile_site_json_feed(username):
    return redirect(subdomain_url(username, "/feed.json"), 301)


@bp.route("/about")
def about():
    return render_template("about.html", **account_link_vars())


@bp.route("/talk")
def talk():
    return render_template("talk.html", **account_link_vars())


def _render_page(page_meta, row, site_user, site, is_owner):
    """Render a page view, shared between subdomain and non-subdomain paths."""
    slug = page_meta["slug"]
    has_token = has_page_token(page_meta)
    unclaimed = page_meta["user_id"] is None and has_token

    if row["visibility"] == "private" and not is_owner and not has_token:
        abort(404)

    page_can_edit = can_edit(page_meta)
    show_actions = is_owner or (has_token and page_can_edit)

    page_title = get_title(row["content"])
    page_description = get_description(row["content"])
    html = render_markdown(row["content"])
    html = html.replace("<h1>", '<h1 class="p-name">', 1)

    content_title = ""
    content_body = html
    h1_end = html.find("</h1>")
    if html.lstrip().startswith("<h1") and h1_end != -1:
        split_pos = h1_end + len("</h1>")
        content_title = html[:split_pos]
        content_body = html[split_pos:].lstrip()

    site_title = None
    avatar_url = None
    bio_html = ""
    license_info = None
    if site_user:
        site_title = site_user.get("name") or site_user.get("username")
        avatar_url = site_user.get("avatar")
        bio = site_user.get("bio")
        bio_html = render_bio(bio, g.url_prefix) if bio else ""
        if site:
            license_info = LICENSES.get(site.get("license") or "")

    owner_initials = None
    owner_avatar_url = None
    profile_incomplete = False
    owner_profile_url = None
    if is_owner:
        user = g.current_user
        if user:
            owner_initials = compute_initials(user)
            owner_avatar_url = user.get("avatar")
            if not user.get("avatar") and not user.get("bio"):
                profile_incomplete = True
            if user.get("username"):
                owner_profile_url = profile_url(user["username"])

    resp = render_template(
        "page.html",
        content_title=content_title,
        content_body=content_body,
        slug=slug,
        show_actions=show_actions,
        unclaimed=unclaimed,
        is_owner=is_owner,
        owner_initials=owner_initials,
        owner_avatar_url=owner_avatar_url,
        profile_incomplete=profile_incomplete,
        profile_url=owner_profile_url,
        avatar_url=avatar_url,
        bio_html=bio_html,
        updated_at=row["created_at"],
        page_title=page_title,
        page_description=page_description,
        site_title=site_title,
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
        is_subdomain=getattr(g, "is_subdomain", False),
        license_info=license_info,
        visibility=page_meta["visibility"],
        reading_time=reading_time(row["content"]),
        ai_assisted=row.get("ai_assisted", False),
        page_source=row.get("source", "web"),
    )
    response = current_app.make_response(resp)
    if not is_owner and not show_actions and row["visibility"] != "private":
        response.headers["Cache-Control"] = "public, max-age=60"
    return response


@bp.route("/<slug>")
def view_page(slug):
    query_token = request.args.get("token", "")
    if query_token:
        page = verify_page_secret(slug, query_token)
        if page:
            resp = make_response(redirect(f"{g.url_prefix}/{slug}"))
            resp.set_cookie(
                f"page_token_{slug}",
                query_token,
                httponly=True,
                samesite="Lax",
                max_age=30 * 24 * 3600,
            )
            return resp

    site = getattr(g, "site", None)
    subdomain_user = g.subdomain_user

    if site:
        # Subdomain request: look up page within the site
        page_meta = get_page_meta(slug, site_id=site["id"])
        if not page_meta:
            original = find_page_by_original_slug(slug, site_id=site["id"])
            if original:
                return redirect(f"/{original['slug']}", 301)
            is_owner = session.get("user_id") == site["user_id"]
            if is_owner:
                return redirect(f"/{slug}/edit")
            abort(404)

        is_owner = (
            session.get("user_id") == page_meta["user_id"]
            and page_meta["user_id"] is not None
        )

        # Private site: non-owners can't see pages
        if site["visibility"] == "private" and not is_owner:
            abort(404)

        row = get_page_full(page_meta["id"])
        if not row:
            abort(404)

        return _render_page(page_meta, row, subdomain_user, site, is_owner)

    elif subdomain_user:
        page_meta = get_page_meta(slug, subdomain_user["id"])
        if not page_meta:
            original = find_page_by_original_slug(slug, subdomain_user["id"])
            if original:
                return redirect(f"{g.url_prefix}/{original['slug']}", 301)
            if session.get("user_id") == subdomain_user["id"]:
                return redirect(f"{g.url_prefix}/{slug}/edit")
            abort(404)
    else:
        if session.get("user_id"):
            page_meta = get_page_meta(slug, session["user_id"])
        else:
            page_meta = None
        if not page_meta:
            page_meta = get_page_meta(slug)
        if not page_meta:
            owner_user_id = find_page_owner_for_redirect(slug)
            if owner_user_id:
                user = get_user(owner_user_id)
                if user and user.get("username"):
                    return redirect(subdomain_url(user["username"], f"/{slug}"), 301)
            original = find_page_by_original_slug(slug)
            if original and original["slug"] != slug:
                if original["user_id"]:
                    owner = get_user(original["user_id"])
                    if owner and owner.get("username"):
                        return redirect(
                            subdomain_url(owner["username"], f"/{original['slug']}"),
                            301,
                        )
                return redirect(f"/{original['slug']}", 301)
            abort(404)
        if page_meta["user_id"] is not None:
            user = get_user(page_meta["user_id"])
            if user and user.get("username"):
                return redirect(subdomain_url(user["username"], f"/{slug}"), 301)

    if not page_meta:
        abort(404)

    row = get_page_full(page_meta["id"])
    if not row:
        abort(404)

    is_owner = (
        session.get("user_id") == page_meta["user_id"]
        and page_meta["user_id"] is not None
    )
    has_token = has_page_token(page_meta)
    unclaimed = page_meta["user_id"] is None and has_token

    if row["visibility"] == "private" and not is_owner and not has_token:
        abort(404)

    page_can_edit = can_edit(page_meta)
    show_actions = is_owner or (has_token and page_can_edit)

    page_title = get_title(row["content"])
    page_description = get_description(row["content"])
    html = render_markdown(row["content"])
    html = html.replace("<h1>", '<h1 class="p-name">', 1)

    content_title = ""
    content_body = html
    h1_end = html.find("</h1>")
    if html.lstrip().startswith("<h1") and h1_end != -1:
        split_pos = h1_end + len("</h1>")
        content_title = html[:split_pos]
        content_body = html[split_pos:].lstrip()

    site_title = None
    avatar_url = None
    bio_html = ""
    license_info = None
    if subdomain_user:
        site_title = subdomain_user.get("name") or subdomain_user.get("username")
        avatar_url = subdomain_user.get("avatar")
        bio = subdomain_user.get("bio")
        bio_html = render_bio(bio, g.url_prefix) if bio else ""

        from db import get_default_site_for_user
        default_site = get_default_site_for_user(subdomain_user["id"])
        if default_site:
            license_info = LICENSES.get(default_site.get("license") or "")

    owner_initials = None
    owner_avatar_url = None
    profile_incomplete = False
    owner_profile_url = None
    if is_owner:
        user = g.current_user
        if user:
            owner_initials = compute_initials(user)
            owner_avatar_url = user.get("avatar")
            if not user.get("avatar") and not user.get("bio"):
                profile_incomplete = True
            if user.get("username"):
                owner_profile_url = profile_url(user["username"])

    resp = render_template(
        "page.html",
        content_title=content_title,
        content_body=content_body,
        slug=slug,
        show_actions=show_actions,
        unclaimed=unclaimed,
        is_owner=is_owner,
        owner_initials=owner_initials,
        owner_avatar_url=owner_avatar_url,
        profile_incomplete=profile_incomplete,
        profile_url=owner_profile_url,
        avatar_url=avatar_url,
        bio_html=bio_html,
        updated_at=row["created_at"],
        page_title=page_title,
        page_description=page_description,
        site_title=site_title,
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
        is_subdomain=subdomain_user is not None,
        license_info=license_info,
        visibility=page_meta["visibility"],
        reading_time=reading_time(row["content"]),
        ai_assisted=row.get("ai_assisted", False),
        page_source=row.get("source", "web"),
    )
    response = current_app.make_response(resp)
    if not is_owner and not show_actions and row["visibility"] != "private":
        response.headers["Cache-Control"] = "public, max-age=60"
    return response


@bp.route("/<slug>/history")
def page_history(slug):
    page_meta = find_page(slug)
    if not page_meta:
        abort(404)

    total = get_revision_count(page_meta["id"])
    if total == 0:
        abort(404)

    per_page = 6
    page = request.args.get("page", 1, type=int)
    total_pages = (total + per_page - 1) // per_page
    page = max(1, min(page, total_pages))

    revisions = get_revisions_paginated(page_meta["id"], page, per_page)

    latest_revision = revisions[0]["revision"] if revisions and page == 1 else None
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
                "source": rev["source"],
                "ai_assisted": rev["ai_assisted"],
                "current": rev["revision"] == latest_revision,
            }
        )

    return render_template(
        "history.html",
        slug=slug,
        revisions=paginated,
        page=page,
        total_pages=total_pages,
        is_subdomain=getattr(g, "is_subdomain", False) or g.subdomain_user is not None,
    )


@bp.route("/<slug>/history/<int:revision>")
def view_revision(slug, revision):
    page_meta = find_page(slug)
    if not page_meta:
        abort(404)

    row = get_revision(page_meta["id"], revision)
    if not row:
        abort(404)

    html = render_markdown(row["content"])
    return render_template(
        "revision.html",
        content=html,
        slug=slug,
        revision=row["revision"],
        created_at=row["created_at"],
        source=row["source"],
        ai_assisted=row["ai_assisted"],
        is_subdomain=getattr(g, "is_subdomain", False) or g.subdomain_user is not None,
    )


# --- Feeds ---


def _build_site_feed_entries(user_id=None, site_id=None):
    if site_id:
        entries = get_feed_entries_for_site(site_id)
    else:
        entries = get_feed_entries_for_user(user_id)
    feed_base = f"{request.scheme}://{request.host}{g.url_prefix}"
    items = []
    for entry in entries:
        body = get_body(entry["content"])
        page_url = f"{feed_base}/{entry['slug']}"
        items.append(
            {
                "title": get_title(entry["content"]) or "",
                "url": page_url,
                "body": body,
                "body_html": render_markdown(body),
                "created_at": entry["created_at"],
            }
        )
    return items


def _build_feed_entries(page_id, slug):
    entries = get_feed_entries(page_id)
    feed_base = f"{request.scheme}://{request.host}{g.url_prefix}"
    page_url = f"{feed_base}/{slug}"
    items = []
    for entry in entries:
        body = get_body(entry["content"])
        items.append(
            {
                "title": get_title(entry["content"]) or "",
                "url": page_url,
                "body": body,
                "body_html": render_markdown(body),
                "created_at": entry["created_at"],
            }
        )
    return items, page_url


def _render_rss_items(items):
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
    return items_xml


@bp.route("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\nSitemap: https://{BASE_DOMAIN}/sitemap.xml\n"
    return body, 200, {"Content-Type": "text/plain"}


@bp.route("/sitemap.xml")
def sitemap():
    pages = get_public_pages()
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"  <url>\n"
        f"    <loc>https://{BASE_DOMAIN}/</loc>\n"
        f"    <changefreq>daily</changefreq>\n"
        f"    <priority>1.0</priority>\n"
        f"  </url>",
    ]
    for page in pages:
        subdomain = page.get("subdomain")
        if subdomain:
            loc = f"https://{subdomain}.{BASE_DOMAIN}/{page['slug']}"
        elif page["username"]:
            loc = f"https://{page['username']}.{BASE_DOMAIN}/{page['slug']}"
        else:
            loc = f"https://{BASE_DOMAIN}/{page['slug']}"
        lastmod = page["updated_at"].strftime("%Y-%m-%d")
        parts.append(
            f"  <url>\n"
            f"    <loc>{xml_escape(loc)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"  </url>"
        )
    parts.append("</urlset>")
    xml = "\n".join(parts)
    return Response(xml, content_type="application/xml; charset=utf-8")


@bp.route("/feed.xml")
def site_rss_feed():
    site = getattr(g, "site", None)
    user = g.subdomain_user
    if not site and not user:
        abort(404)

    site_title = user.get("name") or user.get("username") if user else ""
    if site:
        items = _build_site_feed_entries(site_id=site["id"])
    else:
        items = _build_site_feed_entries(user_id=user["id"])
    feed_base = f"{request.scheme}://{request.host}{g.url_prefix}"
    avatar_url = user.get("avatar") if user else None
    if avatar_url and avatar_url.startswith("/"):
        avatar_url = f"{request.scheme}://{BASE_DOMAIN}{avatar_url}"

    last_build_date = format_datetime(items[0]["created_at"]) if items else ""

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:source="http://source.scripting.com/">',
        "  <channel>",
        f"    <title>{xml_escape(site_title)}</title>",
        f"    <link>{xml_escape(feed_base)}</link>",
        "    <description></description>",
        f"    <lastBuildDate>{last_build_date}</lastBuildDate>",
    ]
    if avatar_url:
        parts.append("    <image>")
        parts.append(f"      <url>{xml_escape(avatar_url)}</url>")
        parts.append(f"      <title>{xml_escape(site_title)}</title>")
        parts.append(f"      <link>{xml_escape(feed_base)}</link>")
        parts.append("    </image>")
    parts.extend(_render_rss_items(items))
    parts.append("  </channel>")
    parts.append("</rss>")
    xml = "\n".join(parts)

    return Response(xml, content_type="application/rss+xml; charset=utf-8")


@bp.route("/feed.json")
def site_json_feed():
    site = getattr(g, "site", None)
    user = g.subdomain_user
    if not site and not user:
        abort(404)

    site_title = user.get("name") or user.get("username") if user else ""
    if site:
        items = _build_site_feed_entries(site_id=site["id"])
    else:
        items = _build_site_feed_entries(user_id=user["id"])
    feed_base = f"{request.scheme}://{request.host}{g.url_prefix}"
    avatar_url = user.get("avatar") if user else None
    if avatar_url and avatar_url.startswith("/"):
        avatar_url = f"{request.scheme}://{BASE_DOMAIN}{avatar_url}"

    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": site_title,
        "home_page_url": feed_base,
        "feed_url": f"{feed_base}/feed.json",
    }
    if avatar_url:
        feed["icon"] = avatar_url
    feed["items"] = [
        {
            "id": item["url"],
            "url": item["url"],
            "title": item["title"],
            "content_html": item["body_html"],
            "date_published": item["created_at"].isoformat(),
            "_source_markdown": item["body"],
        }
        for item in items
    ]

    return Response(
        json.dumps(feed), content_type="application/feed+json; charset=utf-8"
    )


@bp.route("/<slug>/feed.xml")
def rss_feed(slug):
    page_meta = find_page(slug)
    if not page_meta or page_meta["user_id"] is None:
        abort(404)

    items, page_url = _build_feed_entries(page_meta["id"], slug)
    row = get_page(page_meta["id"])
    page_title = (get_title(row["content"]) if row else None) or slug

    last_build_date = format_datetime(items[0]["created_at"]) if items else ""

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:source="http://source.scripting.com/">',
        "  <channel>",
        f"    <title>{xml_escape(page_title)}</title>",
        f"    <link>{xml_escape(page_url)}</link>",
        "    <description></description>",
        f"    <lastBuildDate>{last_build_date}</lastBuildDate>",
    ]
    parts.extend(_render_rss_items(items))
    parts.append("  </channel>")
    parts.append("</rss>")
    xml = "\n".join(parts)

    return Response(xml, content_type="application/rss+xml; charset=utf-8")


@bp.route("/<slug>/feed.json")
def json_feed(slug):
    page_meta = find_page(slug)
    if not page_meta or page_meta["user_id"] is None:
        abort(404)

    items, page_url = _build_feed_entries(page_meta["id"], slug)
    row = get_page(page_meta["id"])
    page_title = (get_title(row["content"]) if row else None) or slug

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
