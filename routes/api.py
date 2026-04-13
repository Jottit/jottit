import hashlib

from flask import Blueprint, jsonify, request

from db import (
    claim_page_with_secret,
    create_page_secret,
    delete_page,
    get_page,
    get_page_meta,
    get_pages_for_user,
    get_revision_count,
    get_revisions_paginated,
    get_user_by_token_hash,
    get_user_by_username,
    save_page,
    update_page_visibility,
    verify_page_secret,
)
from routes import VISIBILITY_OPTIONS
from utils import (
    build_conventions,
    generate_slug,
    get_title,
    is_special_slug,
    slugify,
    MAX_CONTENT_LENGTH,
)

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


def _serialize_page(meta, page_data):
    return {
        "slug": meta["slug"],
        "title": get_title(page_data["content"]) or "",
        "content": page_data["content"],
        "visibility": meta["visibility"],
        "updated_at": page_data["created_at"].isoformat(),
    }


@api_bp.route("/agent-setup")
def agent_setup():
    user = _require_auth()
    if not user:
        return _error(
            "Unauthorized — include your API token as: Authorization: Bearer YOUR_TOKEN",
            401,
        )
    base_url = request.url_root.rstrip("/")
    username = user.get("username", "")
    pages = get_pages_for_user(user["id"])
    return jsonify(
        {
            "welcome": f"You are connected to Jottit as @{username}.",
            "philosophy": (
                "Jottit turns markdown into beautiful, shareable web pages. "
                "When someone shares an insight worth keeping, your job is to "
                "capture it as a well-structured page. Think of yourself as a "
                "writing partner, not an API client."
            ),
            "workflow": {
                "when_to_create": (
                    "When the user shares an insight, idea, or piece of thinking "
                    "that deserves to exist as its own page. Don't create pages "
                    "for trivial exchanges."
                ),
                "when_to_update": (
                    "When the user refines or adds to an existing topic. Check "
                    "list_pages first to avoid duplicates."
                ),
                "default_visibility": "private",
                "titling": (
                    "Every page starts with a markdown H1 (# Title). Use clear, "
                    "descriptive titles. The title becomes the page's identity."
                ),
                "content_style": (
                    "Write in clean markdown. The output will be rendered with "
                    "beautiful typography. No need for HTML."
                ),
            },
            "conventions": build_conventions(pages),
            "about": "Jottit is a markdown publishing tool. Pages are written in markdown and get a beautiful URL.",
            "api_base": f"{base_url}/api/v1",
            "your_profile": f"{base_url}/@{username}",
            "endpoints": {
                "list_pages": {
                    "method": "GET",
                    "path": "/pages",
                    "description": "List all your pages. Returns slug, title, visibility, and updated_at.",
                },
                "create_page": {
                    "method": "POST",
                    "path": "/pages",
                    "description": "Create a new page.",
                    "body": {
                        "content": "# Title\\n\\nMarkdown content here.",
                        "slug": "(optional)",
                        "visibility": "(optional: private, unlisted, listed, pinned)",
                    },
                },
                "get_page": {
                    "method": "GET",
                    "path": "/pages/{slug}",
                    "description": "Get a page by slug. Returns title, content (markdown), visibility, and updated_at.",
                },
                "update_page": {
                    "method": "PUT",
                    "path": "/pages/{slug}",
                    "description": "Update a page. Send content and/or visibility.",
                    "body": {
                        "content": "(optional) full markdown",
                        "visibility": "(optional)",
                    },
                },
            },
            "auth": "Include your token in every request: Authorization: Bearer YOUR_TOKEN",
            "content_format": "All content is markdown. Start with '# Title' on the first line.",
            "default_visibility": "New pages are private by default. Change to 'listed' to show on your profile.",
            "try_it": f"To verify this works, call GET {base_url}/api/v1/pages to list your pages.",
        }
    )


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
    pages = get_pages_for_user(profile["id"])
    public_pages = [
        {
            "slug": p["slug"],
            "title": get_title(p["content"]) or "",
            "visibility": p["visibility"],
            "updated_at": p["updated_at"].isoformat(),
        }
        for p in pages
        if p["visibility"] in ("listed", "pinned") and not is_special_slug(p["slug"])
    ]
    return jsonify(
        {
            "username": profile.get("username"),
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "avatar": profile.get("avatar"),
            "pages": public_pages,
        }
    )


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
                if not is_special_slug(p["slug"])
            ],
            "conventions": build_conventions(pages),
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
        )

        meta = get_page_meta(slug, user["id"])
        page_data = get_page(meta["id"])
        return jsonify(_serialize_page(meta, page_data)), 201

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
    page_secret = request.headers.get("X-Page-Secret", "")

    if not user and not page_secret:
        return _error("Unauthorized", 401)

    if user:
        meta = get_page_meta(slug, user["id"])
    else:
        meta = verify_page_secret(slug, page_secret)

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

    user_id = user["id"] if user else None
    save_page(
        slug,
        content,
        current_visibility,
        user_id,
        source=_get_source(),
        ai_assisted=ai_assisted,
    )

    meta = get_page_meta(slug, user_id)
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
