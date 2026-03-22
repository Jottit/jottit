import base64
import hashlib
import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, session

from db import (
    consume_oauth_code,
    create_api_token,
    create_oauth_client,
    create_oauth_code,
    create_verification_code,
    find_or_create_user,
    get_oauth_client,
    user_exists,
    verify_code,
)
from mail import send_verification_email
from routes import BASE_DOMAIN, limiter
from utils import valid_email

oauth_bp = Blueprint("oauth", __name__)


@oauth_bp.route("/.well-known/oauth-authorization-server")
def metadata():
    base = f"{request.scheme}://{BASE_DOMAIN}"
    return jsonify(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "registration_endpoint": f"{base}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }
    )


@oauth_bp.route("/oauth/register", methods=["POST"])
@limiter.limit("20 per hour")
def register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    redirect_uris = data.get("redirect_uris")
    if not redirect_uris or not isinstance(redirect_uris, list):
        return jsonify({"error": "redirect_uris is required"}), 400

    client_name = data.get("client_name", "")
    client_id = create_oauth_client(redirect_uris, client_name)

    return (
        jsonify(
            {
                "client_id": client_id,
                "redirect_uris": redirect_uris,
                "client_name": client_name,
            }
        ),
        201,
    )


@oauth_bp.route("/oauth/authorize", methods=["GET", "POST"])
@limiter.limit("10 per 10 minutes", methods=["POST"])
def authorize():
    if request.method == "GET":
        client_id = request.args.get("client_id", "")
        redirect_uri = request.args.get("redirect_uri", "")
        state = request.args.get("state", "")
        code_challenge = request.args.get("code_challenge", "")
        code_challenge_method = request.args.get("code_challenge_method", "")
        response_type = request.args.get("response_type", "")

        if response_type != "code":
            return jsonify({"error": "unsupported_response_type"}), 400
        if code_challenge_method != "S256":
            return (
                jsonify(
                    {"error": "invalid_request", "error_description": "S256 required"}
                ),
                400,
            )
        if not code_challenge:
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "error_description": "code_challenge required",
                    }
                ),
                400,
            )

        client = get_oauth_client(client_id)
        if not client:
            return jsonify({"error": "invalid_client"}), 400
        if redirect_uri not in client["redirect_uris"]:
            return jsonify({"error": "invalid_redirect_uri"}), 400

        session["oauth"] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "client_name": client["client_name"],
        }

        user_id = session.get("user_id")
        if user_id:
            return render_template(
                "oauth_authorize.html",
                client_name=client["client_name"] or "An application",
            )

        return render_template("oauth_signin.html")

    # POST — handle email submission, code verification, or consent
    oauth = session.get("oauth")
    if not oauth:
        return jsonify({"error": "invalid_request"}), 400

    action = request.form.get("action", "")

    if action == "approve":
        # Already signed in, user clicked approve
        user_id = session.get("user_id")
        if not user_id:
            return redirect(f"/oauth/authorize?{request.query_string.decode()}")
        return _issue_code_and_redirect(oauth, user_id)

    if action == "deny":
        uri = oauth["redirect_uri"]
        state = oauth["state"]
        session.pop("oauth", None)
        sep = "&" if "?" in uri else "?"
        return redirect(f"{uri}{sep}error=access_denied&state={state}")

    if action == "verify":
        # Code verification step
        email = (
            (request.form.get("email") or session.get("oauth_email", ""))
            .strip()
            .lower()
        )
        code = request.form.get("code", "").strip()
        if not email or not code:
            return render_template(
                "oauth_verify.html", email=email, error="Code is required."
            )

        if not verify_code(email, code, "oauth"):
            return render_template(
                "oauth_verify.html", email=email, error="Invalid or expired code."
            )

        user_id = find_or_create_user(email)
        session.pop("oauth_email", None)
        session["user_id"] = user_id
        return _issue_code_and_redirect(oauth, user_id)

    # Email submission step
    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("oauth_signin.html", error="Email is required.")
    if not valid_email(email):
        return render_template(
            "oauth_signin.html", error="Please enter a valid email address."
        )

    if not user_exists(email):
        return render_template("oauth_signin.html", not_found=True)

    verification_code = create_verification_code(email, "oauth")
    send_verification_email(email, verification_code)
    session["oauth_email"] = email
    return render_template("oauth_verify.html", email=email)


def _issue_code_and_redirect(oauth, user_id):
    code = create_oauth_code(
        oauth["client_id"],
        user_id,
        oauth["redirect_uri"],
        oauth["code_challenge"],
    )
    uri = oauth["redirect_uri"]
    state = oauth["state"]
    session.pop("oauth", None)
    sep = "&" if "?" in uri else "?"
    return redirect(f"{uri}{sep}code={code}&state={state}")


def _verify_pkce(code_verifier, code_challenge):
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, code_challenge)


@oauth_bp.route("/oauth/token", methods=["POST"])
@limiter.limit("20 per 10 minutes")
def token():
    grant_type = request.form.get("grant_type", "")
    if grant_type != "authorization_code":
        return jsonify({"error": "unsupported_grant_type"}), 400

    code = request.form.get("code", "")
    client_id = request.form.get("client_id", "")
    redirect_uri = request.form.get("redirect_uri", "")
    code_verifier = request.form.get("code_verifier", "")

    if not all([code, client_id, redirect_uri, code_verifier]):
        return jsonify({"error": "invalid_request"}), 400

    row = consume_oauth_code(code, client_id, redirect_uri)
    if not row:
        return jsonify({"error": "invalid_grant"}), 400

    if not _verify_pkce(code_verifier, row["code_challenge"]):
        return jsonify({"error": "invalid_grant"}), 400

    client = get_oauth_client(client_id)
    token_name = (
        f"oauth:{client['client_name']}"
        if client and client["client_name"]
        else "oauth"
    )
    access_token, _ = create_api_token(row["user_id"], token_name)

    return jsonify(
        {
            "access_token": access_token,
            "token_type": "Bearer",
        }
    )
