import json

from flask import Blueprint, Response, jsonify, request

from db import (
    create_page_secret,
    delete_page,
    get_page,
    get_page_meta,
    get_pages_for_user,
    get_revision_count,
    get_revisions_paginated,
    get_user_by_username,
    save_page,
    update_page_visibility,
)
from routes import VISIBILITY_OPTIONS
from routes.api import _require_auth, _serialize_page
from utils import generate_slug, get_title, slugify, MAX_CONTENT_LENGTH

mcp_bp = Blueprint("mcp", __name__)

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "Jottit", "version": "1.0.0"}

TOOLS = [
    {
        "name": "list_pages",
        "description": "List all pages owned by the authenticated user. Returns each page's slug, title, visibility, and last updated timestamp.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_page",
        "description": "Get a Jottit page by its slug. Returns the page's title, content (markdown), visibility, and last updated timestamp.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "The page slug"}},
            "required": ["slug"],
        },
    },
    {
        "name": "create_page",
        "description": "Create a new Jottit page. Content should be markdown — start with '# Title' on the first line. Slug is optional (auto-generated from title if omitted). Visibility can be 'private', 'unlisted', 'listed', or 'pinned'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Markdown content"},
                "slug": {
                    "type": "string",
                    "description": "URL slug (optional)",
                    "default": "",
                },
                "visibility": {
                    "type": "string",
                    "enum": ["unlisted", "listed", "pinned"],
                    "default": "unlisted",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "update_page",
        "description": "Update an existing Jottit page. All fields except slug are optional — only provided fields are changed. Content should be full markdown including the '# Title' line. Requires authentication.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "The page slug"},
                "content": {"type": "string", "description": "Markdown content"},
                "visibility": {
                    "type": "string",
                    "enum": ["unlisted", "listed", "pinned"],
                },
            },
            "required": ["slug"],
        },
    },
    {
        "name": "delete_page",
        "description": "Permanently delete a Jottit page. This cannot be undone.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "The page slug"}},
            "required": ["slug"],
        },
    },
    {
        "name": "get_revisions",
        "description": "List revision history for a page. Returns revision number, timestamp, word count, source (web/api/mcp), and whether it was AI-assisted. Newest revisions first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "The page slug"},
                "page": {"type": "integer", "default": 1},
                "per_page": {"type": "integer", "default": 20},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "get_user_profile",
        "description": "Get a Jottit user's public profile and their listed/pinned pages.",
        "inputSchema": {
            "type": "object",
            "properties": {"username": {"type": "string"}},
            "required": ["username"],
        },
    },
]


def _jsonrpc_error(id, code, message):
    return jsonify(
        {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
    )


def _jsonrpc_result(id, result):
    return jsonify({"jsonrpc": "2.0", "id": id, "result": result})


def _text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def _call_tool(name, args, user):
    user_id = user["id"] if user else None

    if name == "list_pages":
        if not user:
            return _text_result("Error: authentication required")
        pages = get_pages_for_user(user_id)
        result = [
            {
                "slug": p["slug"],
                "title": get_title(p["content"]) or "",
                "visibility": p["visibility"],
                "updated_at": p["updated_at"].isoformat(),
            }
            for p in pages
        ]
        return _text_result(json.dumps({"pages": result}, indent=2))

    if name == "get_page":
        if not user:
            return _text_result("Error: authentication required")
        slug = args.get("slug", "")
        meta = get_page_meta(slug, user_id)
        if not meta:
            return _text_result(f"Error: page '{slug}' not found")
        page_data = get_page(meta["id"])
        return _text_result(json.dumps(_serialize_page(meta, page_data), indent=2))

    if name == "create_page":
        content = args.get("content", "").strip()
        if not content:
            return _text_result("Error: content is required")
        if len(content) > MAX_CONTENT_LENGTH:
            return _text_result(
                f"Error: content exceeds {MAX_CONTENT_LENGTH} characters"
            )

        slug = slugify(args.get("slug", ""))
        if not slug:
            slug = slugify(get_title(content) or "")
        if not slug:
            slug = generate_slug()

        if user:
            visibility = args.get("visibility", "unlisted")
            if visibility not in VISIBILITY_OPTIONS:
                return _text_result(
                    f"Error: visibility must be one of: {', '.join(VISIBILITY_OPTIONS)}"
                )

            slug = save_page(
                slug, content, visibility, user_id, source="mcp", ai_assisted=True
            )

            meta = get_page_meta(slug, user_id)
            page_data = get_page(meta["id"])
            return _text_result(json.dumps(_serialize_page(meta, page_data), indent=2))

        # Unauthenticated: create unclaimed page
        slug = save_page(
            slug, content, "unlisted", None, source="mcp", ai_assisted=True
        )
        meta = get_page_meta(slug)
        page_data = get_page(meta["id"])
        secret = create_page_secret(meta["id"])
        result = _serialize_page(meta, page_data)
        result["page_secret"] = secret
        return _text_result(json.dumps(result, indent=2))

    if name == "update_page":
        if not user:
            return _text_result("Error: authentication required to update a page")
        slug = args.get("slug", "")

        meta = get_page_meta(slug, user_id)
        if not meta:
            return _text_result(f"Error: page '{slug}' not found")

        page_data = get_page(meta["id"])
        content = args.get("content", page_data["content"]).strip()
        if not content:
            return _text_result("Error: content cannot be empty")
        if len(content) > MAX_CONTENT_LENGTH:
            return _text_result(
                f"Error: content exceeds {MAX_CONTENT_LENGTH} characters"
            )

        visibility = args.get("visibility")
        if visibility is not None:
            if visibility not in VISIBILITY_OPTIONS:
                return _text_result(
                    f"Error: visibility must be one of: {', '.join(VISIBILITY_OPTIONS)}"
                )
            update_page_visibility(meta["id"], visibility)
        current_visibility = visibility or meta["visibility"]

        save_page(
            slug,
            content,
            current_visibility,
            user_id,
            source="mcp",
            ai_assisted=True,
        )

        meta = get_page_meta(slug, user_id)
        page_data = get_page(meta["id"])
        return _text_result(json.dumps(_serialize_page(meta, page_data), indent=2))

    if name == "delete_page":
        if not user:
            return _text_result("Error: authentication required")
        slug = args.get("slug", "")
        meta = get_page_meta(slug, user_id)
        if not meta:
            return _text_result(f"Error: page '{slug}' not found")
        delete_page(meta["id"])
        return _text_result(json.dumps({"ok": True}))

    if name == "get_revisions":
        slug = args.get("slug", "")
        meta = get_page_meta(slug, user_id)
        if not meta:
            return _text_result(f"Error: page '{slug}' not found")

        page_num = args.get("page", 1)
        per_page = min(args.get("per_page", 20), 100)
        revisions = get_revisions_paginated(
            meta["id"], page=page_num, per_page=per_page
        )
        total = get_revision_count(meta["id"])
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return _text_result(
            json.dumps(
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
                    "page": page_num,
                    "total_pages": total_pages,
                },
                indent=2,
            )
        )

    if name == "get_user_profile":
        username = args.get("username", "")
        profile = get_user_by_username(username)
        if not profile:
            return _text_result(f"Error: user '{username}' not found")
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
        return _text_result(
            json.dumps(
                {
                    "username": profile.get("username"),
                    "name": profile.get("name"),
                    "bio": profile.get("bio"),
                    "pages": public_pages,
                },
                indent=2,
            )
        )

    return _text_result(f"Error: unknown tool '{name}'")


@mcp_bp.route("/mcp", methods=["GET"])
def handle_mcp_sse():
    user = _require_auth()
    if not user:
        r = jsonify({"error": "Unauthorized"})
        r.status_code = 401
        r.headers["WWW-Authenticate"] = "Bearer"
        return r

    def stream():
        yield ": ok\n\n"

    return Response(stream(), content_type="text/event-stream")


@mcp_bp.route("/mcp", methods=["POST"])
def handle_mcp():
    user = _require_auth()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid JSON"}), 400

    msg_id = data.get("id")
    method = data.get("method", "")
    params = data.get("params", {})

    if method == "initialize":
        # No auth required for initialize
        return _jsonrpc_result(
            msg_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )

    if method == "notifications/initialized":
        return Response(status=204)

    if method == "ping":
        return _jsonrpc_result(msg_id, {})

    if method == "tools/list":
        return _jsonrpc_result(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        # create_page and update_page work without auth
        if name not in ("create_page", "update_page") and not user:
            r = jsonify({"error": "Unauthorized"})
            r.status_code = 401
            r.headers["WWW-Authenticate"] = "Bearer"
            return r
        result = _call_tool(name, args, user)
        return _jsonrpc_result(msg_id, result)

    # All other methods require auth
    if not user:
        r = jsonify({"error": "Unauthorized"})
        r.status_code = 401
        r.headers["WWW-Authenticate"] = "Bearer"
        return r

    return _jsonrpc_error(msg_id, -32601, f"Method not found: {method}")
