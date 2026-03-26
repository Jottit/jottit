import base64
import hashlib
import http.server
import secrets
import threading
import webbrowser
from urllib.parse import parse_qs, urlparse

import click
import httpx

from jottit_cli.config import load_config, save_config


def _generate_pkce():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code = None
    state = None

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        _CallbackHandler.code = qs.get("code", [None])[0]
        _CallbackHandler.state = qs.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Signed in! You can close this tab.</h2></body></html>"
        )

    def log_message(self, format, *args):
        pass


@click.command()
@click.option("--token", help="Manually set an API token (skip OAuth)")
@click.pass_context
def login(ctx, token):
    """Sign in to Jottit."""
    fmt = ctx.obj["formatter"]

    if token:
        save_config(token, ctx.obj.get("base_url_override"))
        fmt.success(
            data={"method": "token"},
            message="Token saved to ~/.jottitrc",
            breadcrumbs=[
                {"label": "Check auth", "command": "jottit whoami --json"},
            ],
        )
        return

    config = load_config(base_url_override=ctx.obj.get("base_url_override"))
    base = config.base_url.rstrip("/")
    http_client = httpx.Client(timeout=30)

    server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://localhost:{port}/callback"

    try:
        r = http_client.post(
            f"{base}/oauth/register",
            json={
                "redirect_uris": [redirect_uri],
                "client_name": "Jottit CLI",
            },
        )
    except httpx.ConnectError:
        fmt.error(f"Could not connect to {base}")
    except httpx.TimeoutException:
        fmt.error("Request timed out.")
    if r.status_code != 201:
        fmt.error("Failed to register OAuth client.")
    client_id = r.json()["client_id"]

    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    auth_url = (
        f"{base}/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
        f"&state={state}"
    )

    click.echo("Opening browser to sign in...")
    webbrowser.open(auth_url)

    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()
    server_thread.join(timeout=120)
    server.server_close()

    if not _CallbackHandler.code:
        fmt.error("Timed out waiting for authorization.")
    if _CallbackHandler.state != state:
        fmt.error("State mismatch. Possible CSRF attack.")

    r = http_client.post(
        f"{base}/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": _CallbackHandler.code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    if r.status_code != 200:
        fmt.error("Failed to exchange authorization code for token.")

    access_token = r.json()["access_token"]
    save_config(access_token, config.base_url)

    r = http_client.get(
        f"{base}/api/v1/user",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    )
    username = (
        r.json().get("username", "unknown") if r.status_code == 200 else "unknown"
    )

    fmt.success(
        data={"username": username},
        message=f"Signed in as {username}. Token saved to ~/.jottitrc",
        quiet_value=username,
        breadcrumbs=[
            {"label": "List pages", "command": "jottit list --json"},
            {"label": "Publish a page", "command": "jottit publish FILE --json"},
        ],
    )
