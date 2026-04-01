import json

from flask import Blueprint, Response, jsonify, request

from db import (
    check_subdomain_available,
    create_page_secret,
    create_site as db_create_site,
    delete_page,
    delete_site as db_delete_site,
    get_default_site,
    get_page,
    get_page_meta,
    get_pages_for_site,
    get_pages_for_user,
    get_revision_count,
    get_revisions_paginated,
    get_site as db_get_site,
    get_site_by_subdomain,
    get_sites_for_user,
    get_user_by_username,
    save_page,
    update_page_visibility,
    update_site as db_update_site,
)
from routes import SITE_VISIBILITY_OPTIONS, VISIBILITY_OPTIONS
from routes.api import _require_auth, _serialize_page
from utils import (
    RESERVED_SUBDOMAINS,
    generate_slug,
    get_title,
    slugify,
    valid_subdomain,
    MAX_CONTENT_LENGTH,
)

mcp_bp = Blueprint("mcp", __name__)

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "Jottit", "version": "1.0.0"}

SITE_PARAM = {
    "type": "string",
    "description": "Subdomain of the wiki to target. Defaults to your default wiki if omitted.",
}

TOOLS = [
    {
        "name": "list_pages",
        "description": "List all pages owned by the authenticated user. Returns each page's slug, title, visibility, and last updated timestamp.",
        "inputSchema": {
            "type": "object",
            "properties": {"site": SITE_PARAM},
        },
    },
    {
        "name": "get_page",
        "description": "Get a Jottit page by its slug. Returns the page's title, content (markdown), visibility, and last updated timestamp.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "The page slug"},
                "site": SITE_PARAM,
            },
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
                    "enum": ["private", "unlisted", "listed", "pinned"],
                    "default": "private",
                },
                "site": SITE_PARAM,
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
                    "enum": ["private", "unlisted", "listed", "pinned"],
                },
                "site": SITE_PARAM,
            },
            "required": ["slug"],
        },
    },
    {
        "name": "delete_page",
        "description": "Permanently delete a Jottit page. This cannot be undone.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "The page slug"},
                "site": SITE_PARAM,
            },
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
                "site": SITE_PARAM,
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
    {
        "name": "list_sites",
        "description": "List all wikis (sites) owned by the authenticated user.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_site",
        "description": "Get a wiki by its subdomain.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subdomain": {"type": "string", "description": "The wiki subdomain"},
            },
            "required": ["subdomain"],
        },
    },
    {
        "name": "create_site",
        "description": "Create a new wiki.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subdomain": {"type": "string", "description": "The wiki subdomain"},
                "title": {"type": "string", "description": "Wiki title"},
                "visibility": {
                    "type": "string",
                    "enum": ["private", "public", "open"],
                },
                "license": {"type": "string", "description": "License for the wiki"},
            },
            "required": ["subdomain"],
        },
    },
    {
        "name": "update_site",
        "description": "Update a wiki's settings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subdomain": {
                    "type": "string",
                    "description": "The wiki subdomain to update",
                },
                "title": {"type": "string", "description": "New title"},
                "visibility": {
                    "type": "string",
                    "enum": ["private", "public", "open"],
                },
                "license": {"type": "string", "description": "New license"},
                "home_page_slug": {
                    "type": "string",
                    "description": "Slug of the home page",
                },
                "new_subdomain": {
                    "type": "string",
                    "description": "New subdomain to rename to",
                },
            },
            "required": ["subdomain"],
        },
    },
    {
        "name": "delete_site",
        "description": "Permanently delete a wiki and all its pages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subdomain": {
                    "type": "string",
                    "description": "The wiki subdomain to delete",
                },
            },
            "required": ["subdomain"],
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


def _resolve_site(args, user_id):
    subdomain = args.get("site")
    if subdomain:
        site = get_site_by_subdomain(subdomain)
        if not site:
            return None, f"Error: site '{subdomain}' not found"
        if site["user_id"] != user_id:
            return None, f"Error: site '{subdomain}' not found"
        return site, None
    site = get_default_site(user_id)
    if not site:
        return None, None
    return site, None


def _serialize_site(site):
    return {
        "subdomain": site["subdomain"],
        "title": site["title"],
        "visibility": site["visibility"],
        "license": site["license"],
        "home_page_slug": site["home_page_slug"],
        "created_at": site["created_at"].isoformat(),
        "updated_at": site["updated_at"].isoformat(),
    }


def _call_tool(name, args, user):
    user_id = user["id"] if user else None

    if name == "list_pages":
        if not user:
            return _text_result("Error: authentication required")
        site, err = _resolve_site(args, user_id)
        if err:
            return _text_result(err)
        if site:
            pages = get_pages_for_site(site["id"])
        else:
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
        site, err = _resolve_site(args, user_id)
        if err:
            return _text_result(err)
        site_id = site["id"] if site else None
        meta = get_page_meta(slug, user_id, site_id=site_id)
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
            site, err = _resolve_site(args, user_id)
            if err:
                return _text_result(err)
            site_id = site["id"] if site else None

            visibility = args.get("visibility", "private")
            if visibility not in VISIBILITY_OPTIONS:
                return _text_result(
                    f"Error: visibility must be one of: {', '.join(VISIBILITY_OPTIONS)}"
                )

            slug = save_page(
                slug,
                content,
                visibility,
                user_id,
                source="mcp",
                ai_assisted=True,
                site_id=site_id,
            )

            meta = get_page_meta(slug, user_id, site_id=site_id)
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
        site, err = _resolve_site(args, user_id)
        if err:
            return _text_result(err)
        site_id = site["id"] if site else None

        meta = get_page_meta(slug, user_id, site_id=site_id)
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
            site_id=site_id,
        )

        meta = get_page_meta(slug, user_id, site_id=site_id)
        page_data = get_page(meta["id"])
        return _text_result(json.dumps(_serialize_page(meta, page_data), indent=2))

    if name == "delete_page":
        if not user:
            return _text_result("Error: authentication required")
        slug = args.get("slug", "")
        site, err = _resolve_site(args, user_id)
        if err:
            return _text_result(err)
        site_id = site["id"] if site else None
        meta = get_page_meta(slug, user_id, site_id=site_id)
        if not meta:
            return _text_result(f"Error: page '{slug}' not found")
        delete_page(meta["id"])
        return _text_result(json.dumps({"ok": True}))

    if name == "get_revisions":
        slug = args.get("slug", "")
        site, err = _resolve_site(args, user_id) if user else (None, None)
        if err:
            return _text_result(err)
        site_id = site["id"] if site else None
        meta = get_page_meta(slug, user_id, site_id=site_id)
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

    if name == "list_sites":
        if not user:
            return _text_result("Error: authentication required")
        sites = get_sites_for_user(user_id)
        result = [_serialize_site(s) for s in sites]
        return _text_result(json.dumps({"sites": result}, indent=2))

    if name == "get_site":
        if not user:
            return _text_result("Error: authentication required")
        subdomain = args.get("subdomain", "")
        site = get_site_by_subdomain(subdomain)
        if not site or site["user_id"] != user_id:
            return _text_result(f"Error: site '{subdomain}' not found")
        return _text_result(json.dumps(_serialize_site(site), indent=2))

    if name == "create_site":
        if not user:
            return _text_result("Error: authentication required")
        subdomain = args.get("subdomain", "").strip().lower()
        if not subdomain:
            return _text_result("Error: subdomain is required")
        if not valid_subdomain(subdomain):
            return _text_result("Error: invalid subdomain format")
        if subdomain in RESERVED_SUBDOMAINS:
            return _text_result("Error: subdomain is reserved")
        if not check_subdomain_available(subdomain):
            return _text_result("Error: subdomain is already taken")

        visibility = args.get("visibility", "public")
        if visibility not in SITE_VISIBILITY_OPTIONS:
            return _text_result(
                f"Error: visibility must be one of: {', '.join(SITE_VISIBILITY_OPTIONS)}"
            )

        site_id = db_create_site(
            user_id,
            subdomain,
            title=args.get("title"),
            visibility=visibility,
            license=args.get("license"),
        )
        site = db_get_site(site_id)
        return _text_result(json.dumps(_serialize_site(site), indent=2))

    if name == "update_site":
        if not user:
            return _text_result("Error: authentication required")
        subdomain = args.get("subdomain", "")
        site = get_site_by_subdomain(subdomain)
        if not site or site["user_id"] != user_id:
            return _text_result(f"Error: site '{subdomain}' not found")

        updates = {}
        if "title" in args:
            updates["title"] = args["title"]
        if "license" in args:
            updates["license"] = args["license"]
        if "home_page_slug" in args:
            updates["home_page_slug"] = args["home_page_slug"]
        if "visibility" in args:
            if args["visibility"] not in SITE_VISIBILITY_OPTIONS:
                return _text_result(
                    f"Error: visibility must be one of: {', '.join(SITE_VISIBILITY_OPTIONS)}"
                )
            updates["visibility"] = args["visibility"]
        if "new_subdomain" in args:
            new_sub = args["new_subdomain"].strip().lower()
            if not valid_subdomain(new_sub):
                return _text_result("Error: invalid subdomain format")
            if new_sub in RESERVED_SUBDOMAINS:
                return _text_result("Error: subdomain is reserved")
            if new_sub != subdomain and not check_subdomain_available(new_sub):
                return _text_result("Error: subdomain is already taken")
            updates["subdomain"] = new_sub

        if updates:
            db_update_site(site["id"], **updates)

        site = db_get_site(site["id"])
        return _text_result(json.dumps(_serialize_site(site), indent=2))

    if name == "delete_site":
        if not user:
            return _text_result("Error: authentication required")
        subdomain = args.get("subdomain", "")
        site = get_site_by_subdomain(subdomain)
        if not site or site["user_id"] != user_id:
            return _text_result(f"Error: site '{subdomain}' not found")
        db_delete_site(site["id"])
        return _text_result(json.dumps({"ok": True}))

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
