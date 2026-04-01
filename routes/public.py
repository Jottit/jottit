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
    get_default_site,
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
    get_sites_for_user,
    get_user,
    find_page_by_original_slug,
    find_page_owner_for_redirect,
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
    is_creator,
    can_edit,
    profile_url,
    site_url,
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
    current_site = getattr(g, "current_site", None)
    if current_site:
        return _site_home(current_site)

    if "user_id" not in session:
        return render_template("home.html", **account_link_vars())

    user_id = session["user_id"]
    sites = get_sites_for_user(user_id)

    # Site filter
    site_filter = request.args.get("site", "")
    active_site = None
    if site_filter:
        for s in sites:
            if s["subdomain"] == site_filter:
                active_site = s
                break

    if active_site:
        pages = get_pages_for_user(user_id, site_id=active_site["id"])
    else:
        pages = get_pages_for_user(user_id)
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

    site_items = [
        {
            "subdomain": s["subdomain"],
            "title": s.get("title") or s["subdomain"],
            "url": site_url(s["subdomain"]),
        }
        for s in sites
    ]

    return render_template(
        "home.html",
        pages=page_list,
        tab=tab,
        counts=counts,
        display_name=display_name,
        sites=site_items,
        active_site=site_filter,
        **account_link_vars(),
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


def _site_home(site):
    """Render the site root: home page if set, otherwise chronological feed."""
    user = g.subdomain_user
    is_owner = session.get("user_id") == site["user_id"]

    # Private site: only owner can see
    if site["visibility"] == "private" and not is_owner:
        return (
            render_template(
                "site_private.html",
                site=site,
                base_url=f"{request.scheme}://{BASE_DOMAIN}",
            ),
            403,
        )

    # If site has a home page, render it
    if site.get("home_page_slug"):
        page_meta = get_page_meta(site["home_page_slug"], site_id=site["id"])
        if page_meta:
            return view_page(site["home_page_slug"])

    # Otherwise show chronological feed of listed pages
    if is_owner:
        pages = get_pages_for_site(site["id"])
    else:
        pages = get_pages_for_site(site["id"])
        pages = [p for p in pages if p["visibility"] in ("listed", "pinned")]

    pinned = []
    listed = []
    for p in pages:
        item = _build_page_item(p)
        if p["visibility"] == "pinned":
            pinned.append(item)
        else:
            listed.append(item)
    page_list = pinned + listed

    site_title = site.get("title") or user.get("name") or user.get("username")
    owner_initials = None
    owner_avatar_url = None
    profile_incomplete = False
    if is_owner:
        owner_initials = compute_initials(user)
        owner_avatar_url = user.get("avatar")
        if not user.get("avatar") and not user.get("bio"):
            profile_incomplete = True
    bio = user.get("bio")
    bio_html = render_bio(bio, "") if bio else ""
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
        license_info=LICENSES.get(site.get("license") or ""),
        profile_url=profile_url(user["username"]) if user.get("username") else None,
        base_url=f"{request.scheme}://{BASE_DOMAIN}",
    )


def subdomain_home(user):
    """Legacy profile home — used by /@username route."""
    # Show directory of user's public sites
    sites = get_sites_for_user(user["id"])
    public_sites = [s for s in sites if s["visibility"] != "private"]

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
        # Owner sees all sites
        public_sites = sites
    bio = user.get("bio")
    bio_html = render_bio(bio, g.url_prefix) if bio else ""

    # Build site items for display
    site_items = []
    for s in public_sites:
        site_items.append(
            {
                "subdomain": s["subdomain"],
                "title": s.get("title") or s["subdomain"],
                "visibility": s["visibility"],
                "url": site_url(s["subdomain"]),
                "updated_at": s["updated_at"],
            }
        )

    return render_template(
        "profile.html",
        user=user,
        pages=[],
        sites=site_items,
        site_title=site_title,
        is_owner=is_owner,
        owner_initials=owner_initials,
        owner_avatar_url=owner_avatar_url,
        profile_incomplete=profile_incomplete,
        avatar_url=user.get("avatar"),
        bio_html=bio_html,
        license_info=LICENSES.get(
            (get_default_site(user["id"]) or {}).get("license") or ""
        ),
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
    """Backward compat: redirect /@username/slug to username.jottit.org/slug."""
    _set_profile_user(username)
    return redirect(site_url(username, f"/{slug}"), 301)


@bp.route("/@<username>/<slug>/history")
def profile_page_history(username, slug):
    """Backward compat: redirect to subdomain."""
    _set_profile_user(username)
    return redirect(site_url(username, f"/{slug}/history"), 301)


@bp.route("/@<username>/<slug>/history/<int:revision>")
def profile_view_revision(username, slug, revision):
    _set_profile_user(username)
    return redirect(site_url(username, f"/{slug}/history/{revision}"), 301)


@bp.route("/@<username>/<slug>/feed.xml")
def profile_rss_feed(username, slug):
    _set_profile_user(username)
    return redirect(site_url(username, f"/{slug}/feed.xml"), 301)


@bp.route("/@<username>/<slug>/feed.json")
def profile_json_feed(username, slug):
    _set_profile_user(username)
    return redirect(site_url(username, f"/{slug}/feed.json"), 301)


@bp.route("/@<username>/feed.xml")
def profile_site_rss_feed(username):
    _set_profile_user(username)
    return redirect(site_url(username, "/feed.xml"), 301)


@bp.route("/@<username>/feed.json")
def profile_site_json_feed(username):
    _set_profile_user(username)
    return redirect(site_url(username, "/feed.json"), 301)


@bp.route("/about")
def about():
    return render_template("about.html", **account_link_vars())


@bp.route("/talk")
def talk():
    return render_template("talk.html", **account_link_vars())


@bp.route("/<slug>")
def view_page(slug):
    query_token = request.args.get("token", "")
    if query_token:
        from db import verify_page_secret

        page = verify_page_secret(slug, query_token)
        if page:
            created_pages = session.get("created_pages", [])
            if page["id"] not in created_pages:
                created_pages.append(page["id"])
                session["created_pages"] = created_pages
            resp = make_response(redirect(f"{g.url_prefix}/{slug}"))
            resp.set_cookie(
                f"page_token_{slug}",
                query_token,
                httponly=True,
                samesite="Lax",
                max_age=30 * 24 * 3600,
            )
            return resp

    current_site = getattr(g, "current_site", None)
    subdomain_user = g.subdomain_user

    if current_site:
        # On a subdomain: look up page by site_id
        page_meta = get_page_meta(slug, site_id=current_site["id"])
        if not page_meta:
            original = find_page_by_original_slug(slug, site_id=current_site["id"])
            if original:
                return redirect(f"/{original['slug']}", 301)
            is_owner = session.get("user_id") == current_site["user_id"]
            if is_owner:
                return redirect(f"/{slug}/edit")
            abort(404)

        # Check site visibility
        is_owner = session.get("user_id") == current_site["user_id"]
        if current_site["visibility"] == "private" and not is_owner:
            return (
                render_template(
                    "site_private.html",
                    site=current_site,
                    base_url=f"{request.scheme}://{BASE_DOMAIN}",
                ),
                403,
            )

    elif subdomain_user:
        # Legacy /@username context (shouldn't normally reach here for page views)
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
                    return redirect(site_url(user["username"], f"/{slug}"))
            original = find_page_by_original_slug(slug)
            if original and original["slug"] != slug:
                if original["user_id"]:
                    owner = get_user(original["user_id"])
                    if owner and owner.get("username"):
                        return redirect(
                            site_url(owner["username"], f"/{original['slug']}"),
                            301,
                        )
                return redirect(f"/{original['slug']}", 301)
            abort(404)
        if page_meta["user_id"] is not None:
            user = get_user(page_meta["user_id"])
            if user and user.get("username"):
                return redirect(site_url(user["username"], f"/{slug}"))

    if not page_meta:
        abort(404)

    row = get_page_full(page_meta["id"])
    if not row:
        abort(404)

    unclaimed = page_meta["user_id"] is None
    # Only show claim banner if the visitor holds a valid page token cookie
    if unclaimed:
        from db import verify_page_secret

        _claim_token = request.cookies.get(f"page_token_{slug}", "")
        unclaimed = (
            bool(_claim_token) and verify_page_secret(slug, _claim_token) is not None
        )
    is_owner = (
        session.get("user_id") == page_meta["user_id"]
        and page_meta["user_id"] is not None
    )
    page_is_creator = is_creator(page_meta)

    if row["visibility"] == "private" and not is_owner and not page_is_creator:
        abort(404)

    page_can_edit = can_edit(page_meta)
    show_actions = is_owner or (page_is_creator and page_can_edit)

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
    if current_site:
        site_title = (
            current_site.get("title")
            or subdomain_user.get("name")
            or subdomain_user.get("username")
        )
        avatar_url = subdomain_user.get("avatar")
        bio = subdomain_user.get("bio")
        bio_html = render_bio(bio, "") if bio else ""
        license_info = LICENSES.get(current_site.get("license") or "")
    elif subdomain_user:
        site_title = subdomain_user.get("name") or subdomain_user.get("username")
        avatar_url = subdomain_user.get("avatar")
        bio = subdomain_user.get("bio")
        bio_html = render_bio(bio, g.url_prefix) if bio else ""
        site = get_default_site(subdomain_user["id"])
        license_info = LICENSES.get((site or {}).get("license") or "")

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
        is_subdomain=current_site is not None or subdomain_user is not None,
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
        is_subdomain=getattr(g, "current_site", None) is not None
        or g.subdomain_user is not None,
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
        is_subdomain=getattr(g, "current_site", None) is not None
        or g.subdomain_user is not None,
    )


# --- Feeds ---


def _get_feed_base():
    current_site = getattr(g, "current_site", None)
    if current_site:
        return site_url(current_site["subdomain"])
    return f"{request.scheme}://{BASE_DOMAIN}{g.url_prefix}"


def _build_site_feed_entries_for_site(site_id):
    entries = get_feed_entries_for_site(site_id)
    feed_base = _get_feed_base()
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


def _build_site_feed_entries(user_id):
    entries = get_feed_entries_for_user(user_id)
    feed_base = _get_feed_base()
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
    feed_base = _get_feed_base()
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
        if page.get("subdomain"):
            loc = f"https://{page['subdomain']}.{BASE_DOMAIN}/{page['slug']}"
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
    current_site = getattr(g, "current_site", None)
    user = g.subdomain_user
    if not current_site and not user:
        abort(404)

    if current_site:
        site_title = (
            current_site.get("title") or user.get("name") or user.get("username")
        )
        items = _build_site_feed_entries_for_site(current_site["id"])
    else:
        site_title = user.get("name") or user.get("username")
        items = _build_site_feed_entries(user["id"])

    feed_base = _get_feed_base()
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
    current_site = getattr(g, "current_site", None)
    user = g.subdomain_user
    if not current_site and not user:
        abort(404)

    if current_site:
        site_title = (
            current_site.get("title") or user.get("name") or user.get("username")
        )
        items = _build_site_feed_entries_for_site(current_site["id"])
    else:
        site_title = user.get("name") or user.get("username")
        items = _build_site_feed_entries(user["id"])

    feed_base = _get_feed_base()
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
