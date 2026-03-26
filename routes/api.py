import hashlib

from flask import Blueprint, jsonify, request

from db import (
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
)
from utils import generate_slug, get_title, slugify, MAX_CONTENT_LENGTH

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

VISIBILITY_OPTIONS = ("private", "unlisted", "listed", "pinned")


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
        if p["visibility"] in ("listed", "pinned")
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
            ],
        }
    )


@api_bp.route("/pages", methods=["POST"])
def create_page():
    user = _require_auth()
    if not user:
        return _error("Unauthorized", 401)

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

    slug = slugify(data.get("slug", ""))
    if not slug:
        slug = slugify(get_title(content) or "")
    if not slug:
        slug = generate_slug()

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
