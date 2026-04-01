import hashlib

from flask import Blueprint, jsonify, request

from db import (
    check_subdomain_available,
    claim_page_with_secret,
    create_page_secret,
    create_site,
    delete_page,
    delete_site,
    get_default_site,
    get_page,
    get_page_meta,
    get_pages_for_site,
    get_pages_for_user,
    get_revision_count,
    get_revisions_paginated,
    get_site,
    get_site_by_subdomain,
    get_sites_for_user,
    get_user_by_token_hash,
    get_user_by_username,
    save_page,
    update_page_visibility,
    update_site,
    verify_page_secret,
)
from routes import SITE_VISIBILITY_OPTIONS, VISIBILITY_OPTIONS
from utils import generate_slug, get_title, slugify, valid_subdomain, RESERVED_SUBDOMAINS, MAX_CONTENT_LENGTH

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _require_auth():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or len(auth) == 7:
        return None
    token_hash = hashlib.sha256(auth[7:].encode()).hexdigest()
    return get_user_by_token_hash(token_hash)


def _get_source():
    source = request.headers.get("X-Jottit-Source", "").lower()
    if source in ("mcp", "cli"):
        return source
    return "api"


def _error(message, status):
    return jsonify({"error": message}), status


def _serialize_page(meta, page_data, site=None):
    result = {
        "slug": meta["slug"],
        "title": get_title(page_data["content"]) or "",
        "content": page_data["content"],
        "visibility": meta["visibility"],
        "updated_at": page_data["created_at"].isoformat(),
    }
    if site:
        result["site"] = site["subdomain"]
    return result


def _serialize_site(site):
    return {
        "subdomain": site["subdomain"],
        "title": site.get("title") or "",
        "license": site.get("license") or "",
        "visibility": site["visibility"],
        "home_page_slug": site.get("home_page_slug") or "",
        "created_at": site["created_at"].isoformat(),
        "updated_at": site["updated_at"].isoformat(),
    }


def _resolve_site(user, subdomain=None):
    """Resolve a site for the user. If subdomain given, look it up; otherwise use default."""
    if subdomain:
        site = get_site_by_subdomain(subdomain)
        if not site or site["user_id"] != user["id"]:
            return None
        return site
    return get_default_site(user["id"])


# --- User endpoints ---


@api_bp.route("/user")
def get_current_user():
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    return jsonify(
        {
            "username": user.get("username"),
            "name": user.get("name"),
            "bio": user.get("bio"),
            "avatar": user.get("avatar"),
        }
    )


@api_bp.route("/users/<username>")
def get_user_profile(username):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    profile = get_user_by_username(username)
    if not profile:
        return _error("User not found", 404)
    sites = get_sites_for_user(profile["id"])
    public_sites = [
        _serialize_site(s) for s in sites if s["visibility"] != "private"
    ]
    return jsonify(
        {
            "username": profile.get("username"),
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "avatar": profile.get("avatar"),
            "sites": public_sites,
        }
    )


# --- Site endpoints ---


@api_bp.route("/sites")
def list_sites():
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    sites = get_sites_for_user(user["id"])
    return jsonify({"sites": [_serialize_site(s) for s in sites]})


@api_bp.route("/sites", methods=["POST"])
def create_site_route():
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)

    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON", 400)

    subdomain = data.get("subdomain", "").strip().lower()
    if not subdomain:
        return _error("Subdomain is required", 400)
    if not valid_subdomain(subdomain):
        return _error("Subdomain must be lowercase letters, numbers, and hyphens only", 400)
    if subdomain in RESERVED_SUBDOMAINS:
        return _error("That subdomain is reserved", 400)
    if not check_subdomain_available(subdomain):
        return _error("That subdomain is already taken", 409)

    title = data.get("title", "").strip() or None
    visibility = data.get("visibility", "public")
    if visibility not in SITE_VISIBILITY_OPTIONS:
        return _error(f"Visibility must be one of: {', '.join(SITE_VISIBILITY_OPTIONS)}", 400)
    license = data.get("license", "").strip() or None

    site_id = create_site(user["id"], subdomain, title=title, visibility=visibility, license=license)
    site = get_site(site_id)
    return jsonify(_serialize_site(site)), 201


@api_bp.route("/sites/<subdomain>")
def get_site_route(subdomain):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = get_site_by_subdomain(subdomain)
    if not site or site["user_id"] != user["id"]:
        return _error("Site not found", 404)
    return jsonify(_serialize_site(site))


@api_bp.route("/sites/<subdomain>", methods=["PUT"])
def update_site_route(subdomain):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = get_site_by_subdomain(subdomain)
    if not site or site["user_id"] != user["id"]:
        return _error("Site not found", 404)

    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON", 400)

    kwargs = {}
    if "title" in data:
        kwargs["title"] = data["title"].strip() or None
    if "license" in data:
        kwargs["license"] = data["license"].strip() or None
    if "visibility" in data:
        if data["visibility"] not in SITE_VISIBILITY_OPTIONS:
            return _error(f"Visibility must be one of: {', '.join(SITE_VISIBILITY_OPTIONS)}", 400)
        kwargs["visibility"] = data["visibility"]
    if "home_page_slug" in data:
        kwargs["home_page_slug"] = data["home_page_slug"].strip() or None
    if "subdomain" in data:
        new_sub = data["subdomain"].strip().lower()
        if new_sub != subdomain:
            if not valid_subdomain(new_sub):
                return _error("Subdomain must be lowercase letters, numbers, and hyphens only", 400)
            if new_sub in RESERVED_SUBDOMAINS:
                return _error("That subdomain is reserved", 400)
            if not check_subdomain_available(new_sub):
                return _error("That subdomain is already taken", 409)
            kwargs["subdomain"] = new_sub

    if kwargs:
        update_site(site["id"], **kwargs)
    site = get_site(site["id"])
    return jsonify(_serialize_site(site))


@api_bp.route("/sites/<subdomain>", methods=["DELETE"])
def delete_site_route(subdomain):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = get_site_by_subdomain(subdomain)
    if not site or site["user_id"] != user["id"]:
        return _error("Site not found", 404)
    delete_site(site["id"])
    return jsonify({"ok": True})


# --- Page endpoints (nested under sites) ---


@api_bp.route("/sites/<subdomain>/pages")
def list_site_pages(subdomain):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = _resolve_site(user, subdomain)
    if not site:
        return _error("Site not found", 404)
    pages = get_pages_for_site(site["id"])
    return jsonify(
        {
            "pages": [
                {
                    "slug": p["slug"],
                    "title": get_title(p["content"]) or "",
                    "visibility": p["visibility"],
                    "updated_at": p["updated_at"].isoformat(),
                }
                for p in pages
            ],
        }
    )


@api_bp.route("/sites/<subdomain>/pages", methods=["POST"])
def create_site_page(subdomain):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = _resolve_site(user, subdomain)
    if not site:
        return _error("Site not found", 404)

    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON", 400)

    content = data.get("content", "").strip()
    if not content:
        return _error("Content is required", 400)
    if len(content) > MAX_CONTENT_LENGTH:
        return _error(f"Content exceeds maximum length of {MAX_CONTENT_LENGTH} characters", 400)

    ai_assisted = data.get("ai_assisted", False)
    slug = slugify(data.get("slug", ""))
    if not slug:
        slug = slugify(get_title(content) or "")
    if not slug:
        slug = generate_slug()

    visibility = data.get("visibility", "private")
    if visibility not in VISIBILITY_OPTIONS:
        return _error(f"Visibility must be one of: {', '.join(VISIBILITY_OPTIONS)}", 400)

    slug = save_page(slug, content, visibility, user["id"], source=_get_source(), ai_assisted=ai_assisted, site_id=site["id"])
    meta = get_page_meta(slug, site_id=site["id"])
    page_data = get_page(meta["id"])
    return jsonify(_serialize_page(meta, page_data, site)), 201


@api_bp.route("/sites/<subdomain>/pages/<slug>")
def get_site_page(subdomain, slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = _resolve_site(user, subdomain)
    if not site:
        return _error("Site not found", 404)
    meta = get_page_meta(slug, site_id=site["id"])
    if not meta:
        return _error("Page not found", 404)
    page_data = get_page(meta["id"])
    return jsonify(_serialize_page(meta, page_data, site))


@api_bp.route("/sites/<subdomain>/pages/<slug>", methods=["PUT"])
def update_site_page(subdomain, slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = _resolve_site(user, subdomain)
    if not site:
        return _error("Site not found", 404)
    meta = get_page_meta(slug, site_id=site["id"])
    if not meta:
        return _error("Page not found", 404)

    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON", 400)

    page_data = get_page(meta["id"])
    content = data.get("content", page_data["content"]).strip()
    if not content:
        return _error("Content cannot be empty", 400)
    if len(content) > MAX_CONTENT_LENGTH:
        return _error(f"Content exceeds maximum length of {MAX_CONTENT_LENGTH} characters", 400)

    ai_assisted = data.get("ai_assisted", False)
    visibility = data.get("visibility")
    if visibility is not None:
        if visibility not in VISIBILITY_OPTIONS:
            return _error(f"Visibility must be one of: {', '.join(VISIBILITY_OPTIONS)}", 400)
        update_page_visibility(meta["id"], visibility)
    current_visibility = visibility or meta["visibility"]

    save_page(slug, content, current_visibility, user["id"], source=_get_source(), ai_assisted=ai_assisted, site_id=site["id"])
    meta = get_page_meta(slug, site_id=site["id"])
    page_data = get_page(meta["id"])
    return jsonify(_serialize_page(meta, page_data, site))


@api_bp.route("/sites/<subdomain>/pages/<slug>", methods=["DELETE"])
def delete_site_page(subdomain, slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = _resolve_site(user, subdomain)
    if not site:
        return _error("Site not found", 404)
    meta = get_page_meta(slug, site_id=site["id"])
    if not meta:
        return _error("Page not found", 404)
    delete_page(meta["id"])
    return jsonify({"ok": True})


@api_bp.route("/sites/<subdomain>/pages/<slug>/revisions")
def list_site_page_revisions(subdomain, slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    site = _resolve_site(user, subdomain)
    if not site:
        return _error("Site not found", 404)
    meta = get_page_meta(slug, site_id=site["id"])
    if not meta:
        return _error("Page not found", 404)

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)
    revisions = get_revisions_paginated(meta["id"], page=page, per_page=per_page)
    total = get_revision_count(meta["id"])
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return jsonify(
        {
            "revisions": [
                {
                    "revision": r["revision"],
                    "created_at": r["created_at"].isoformat(),
                    "word_count": r["word_count"],
                    "source": r["source"],
                    "ai_assisted": r["ai_assisted"],
                }
                for r in revisions
            ],
            "page": page,
            "total_pages": total_pages,
        }
    )


# --- Backward-compatible page endpoints (default site) ---


@api_bp.route("/pages")
def list_pages():
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)
    pages = get_pages_for_user(user["id"])
    return jsonify(
        {
            "pages": [
                {
                    "slug": p["slug"],
                    "title": get_title(p["content"]) or "",
                    "visibility": p["visibility"],
                    "updated_at": p["updated_at"].isoformat(),
                }
                for p in pages
            ],
        }
    )


@api_bp.route("/pages", methods=["POST"])
def create_page():
    user = _require_auth()

    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON", 400)

    content = data.get("content", "").strip()
    if not content:
        return _error("Content is required", 400)
    if len(content) > MAX_CONTENT_LENGTH:
        return _error(
            f"Content exceeds maximum length of {MAX_CONTENT_LENGTH} characters", 400
        )

    ai_assisted = data.get("ai_assisted", False)

    if user:
        slug = slugify(data.get("slug", ""))
        if not slug:
            slug = slugify(get_title(content) or "")
        if not slug:
            slug = generate_slug()
    else:
        slug = slugify(data.get("slug", "")) or generate_slug()

    if user:
        site = _resolve_site(user, data.get("site"))
        visibility = data.get("visibility", "private")
        if visibility not in VISIBILITY_OPTIONS:
            return _error(
                f"Visibility must be one of: {', '.join(VISIBILITY_OPTIONS)}", 400
            )

        slug = save_page(
            slug,
            content,
            visibility,
            user["id"],
            source=_get_source(),
            ai_assisted=ai_assisted,
            site_id=site["id"] if site else None,
        )

        meta = get_page_meta(slug, user["id"])
        page_data = get_page(meta["id"])
        return jsonify(_serialize_page(meta, page_data, site)), 201

    # Unauthenticated: create unclaimed page
    slug = save_page(
        slug,
        content,
        "unlisted",
        None,
        source=_get_source(),
        ai_assisted=ai_assisted,
    )

    meta = get_page_meta(slug)
    page_data = get_page(meta["id"])
    secret = create_page_secret(meta["id"])
    result = _serialize_page(meta, page_data)
    result["page_secret"] = secret
    return jsonify(result), 201


@api_bp.route("/pages/<slug>")
def get_page_by_slug(slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)

    meta = get_page_meta(slug, user["id"])
    if not meta:
        return _error("Page not found", 404)

    page_data = get_page(meta["id"])
    return jsonify(_serialize_page(meta, page_data))


@api_bp.route("/pages/<slug>", methods=["PUT"])
def update_page(slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)

    meta = get_page_meta(slug, user["id"])
    if not meta:
        return _error("Page not found", 404)

    data = request.get_json(silent=True)
    if not data:
        return _error("Request body must be JSON", 400)

    page_data = get_page(meta["id"])
    content = data.get("content", page_data["content"]).strip()
    if not content:
        return _error("Content cannot be empty", 400)
    if len(content) > MAX_CONTENT_LENGTH:
        return _error(
            f"Content exceeds maximum length of {MAX_CONTENT_LENGTH} characters", 400
        )

    ai_assisted = data.get("ai_assisted", False)

    visibility = data.get("visibility")
    if visibility is not None:
        if visibility not in VISIBILITY_OPTIONS:
            return _error(
                f"Visibility must be one of: {', '.join(VISIBILITY_OPTIONS)}", 400
            )
        update_page_visibility(meta["id"], visibility)
    current_visibility = visibility or meta["visibility"]

    save_page(
        slug,
        content,
        current_visibility,
        user["id"],
        source=_get_source(),
        ai_assisted=ai_assisted,
    )

    meta = get_page_meta(slug, user["id"])
    page_data = get_page(meta["id"])
    return jsonify(_serialize_page(meta, page_data))


@api_bp.route("/pages/<slug>/claim", methods=["POST"])
def claim_page_by_slug(slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)

    page_secret = request.headers.get("X-Page-Secret", "")
    if not page_secret:
        return _error("Page secret is required", 400)

    page_meta = verify_page_secret(slug, page_secret)
    if not page_meta:
        return _error("Invalid page secret or page already claimed", 403)

    if not claim_page_with_secret(page_meta["id"], user["id"]):
        return _error("Page already claimed", 409)

    meta = get_page_meta(slug, user["id"])
    page_data = get_page(meta["id"])
    return jsonify(_serialize_page(meta, page_data))


@api_bp.route("/pages/<slug>", methods=["DELETE"])
def delete_page_by_slug(slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)

    meta = get_page_meta(slug, user["id"])
    if not meta:
        return _error("Page not found", 404)

    delete_page(meta["id"])
    return jsonify({"ok": True})


@api_bp.route("/pages/<slug>/revisions")
def list_revisions(slug):
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)

    meta = get_page_meta(slug, user["id"])
    if not meta:
        return _error("Page not found", 404)

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)

    revisions = get_revisions_paginated(meta["id"], page=page, per_page=per_page)
    total = get_revision_count(meta["id"])
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return jsonify(
        {
            "revisions": [
                {
                    "revision": r["revision"],
                    "created_at": r["created_at"].isoformat(),
                    "word_count": r["word_count"],
                    "source": r["source"],
                    "ai_assisted": r["ai_assisted"],
                }
                for r in revisions
            ],
            "page": page,
            "total_pages": total_pages,
        }
    )
