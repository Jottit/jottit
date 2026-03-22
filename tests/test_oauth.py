import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from db import find_or_create_user


def _pkce():
    verifier = "test-code-verifier-that-is-long-enough-for-pkce"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _register_client(client, redirect_uri="http://localhost:3000/callback"):
    r = client.post(
        "/oauth/register",
        json={
            "redirect_uris": [redirect_uri],
            "client_name": "Test App",
        },
    )
    assert r.status_code == 201
    return r.get_json()["client_id"]


def test_metadata(client):
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    data = r.get_json()
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "registration_endpoint" in data
    assert "S256" in data["code_challenge_methods_supported"]


def test_register_client(client):
    r = client.post(
        "/oauth/register",
        json={
            "redirect_uris": ["http://localhost:3000/callback"],
            "client_name": "My App",
        },
    )
    assert r.status_code == 201
    data = r.get_json()
    assert "client_id" in data
    assert data["client_name"] == "My App"


def test_register_requires_redirect_uris(client):
    r = client.post("/oauth/register", json={"client_name": "No URIs"})
    assert r.status_code == 400


def test_authorize_requires_valid_client(client):
    verifier, challenge = _pkce()
    r = client.get(
        "/oauth/authorize",
        query_string={
            "client_id": "nonexistent",
            "redirect_uri": "http://localhost:3000/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test",
        },
    )
    assert r.status_code == 400


def test_authorize_shows_signin_form(client):
    client_id = _register_client(client)
    verifier, challenge = _pkce()
    r = client.get(
        "/oauth/authorize",
        query_string={
            "client_id": client_id,
            "redirect_uri": "http://localhost:3000/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test",
        },
    )
    assert r.status_code == 200
    assert b"Sign in to authorize" in r.data


def test_authorize_shows_consent_when_signed_in(client):
    user_id = find_or_create_user("test@test.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client_id = _register_client(client)
    verifier, challenge = _pkce()
    r = client.get(
        "/oauth/authorize",
        query_string={
            "client_id": client_id,
            "redirect_uri": "http://localhost:3000/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test",
        },
    )
    assert r.status_code == 200
    assert b"Authorize" in r.data
    assert b"Test App" in r.data


def test_full_oauth_flow_with_signed_in_user(client):
    user_id = find_or_create_user("test@test.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client_id = _register_client(client)
    verifier, challenge = _pkce()
    redirect_uri = "http://localhost:3000/callback"

    # GET authorize to set session
    client.get(
        "/oauth/authorize",
        query_string={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "mystate",
        },
    )

    # Approve
    r = client.post(
        "/oauth/authorize", data={"action": "approve"}, follow_redirects=False
    )
    assert r.status_code == 302
    location = r.headers["Location"]
    assert location.startswith(redirect_uri)
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert "code" in params
    assert params["state"][0] == "mystate"

    # Exchange code for token
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": params["code"][0],
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"

    # Verify token works for API
    r = client.get(
        "/api/v1/pages", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert r.status_code == 200


def test_deny_redirects_with_error(client):
    user_id = find_or_create_user("test@test.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client_id = _register_client(client)
    verifier, challenge = _pkce()
    redirect_uri = "http://localhost:3000/callback"

    client.get(
        "/oauth/authorize",
        query_string={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "mystate",
        },
    )

    r = client.post("/oauth/authorize", data={"action": "deny"}, follow_redirects=False)
    assert r.status_code == 302
    assert "error=access_denied" in r.headers["Location"]


def test_wrong_pkce_verifier_fails(client):
    user_id = find_or_create_user("test@test.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client_id = _register_client(client)
    verifier, challenge = _pkce()
    redirect_uri = "http://localhost:3000/callback"

    client.get(
        "/oauth/authorize",
        query_string={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test",
        },
    )

    r = client.post(
        "/oauth/authorize", data={"action": "approve"}, follow_redirects=False
    )
    parsed = urlparse(r.headers["Location"])
    params = parse_qs(parsed.query)

    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": params["code"][0],
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": "wrong-verifier",
        },
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_grant"


def test_code_cannot_be_reused(client):
    user_id = find_or_create_user("test@test.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client_id = _register_client(client)
    verifier, challenge = _pkce()
    redirect_uri = "http://localhost:3000/callback"

    client.get(
        "/oauth/authorize",
        query_string={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test",
        },
    )

    r = client.post(
        "/oauth/authorize", data={"action": "approve"}, follow_redirects=False
    )
    parsed = urlparse(r.headers["Location"])
    code = parse_qs(parsed.query)["code"][0]

    # First use works
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert r.status_code == 200

    # Second use fails
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    assert r.status_code == 400
