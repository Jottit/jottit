import sys

import click
import httpx

from jottit_cli.config import Config


class JottitClient:
    def __init__(self, config: Config):
        self.base_url = config.base_url.rstrip("/")
        self.has_token = bool(config.token)
        headers = {
            "X-Jottit-Source": "cli",
            "Accept": "application/json",
        }
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        self.client = httpx.Client(
            base_url=self.base_url + "/api/v1",
            headers=headers,
            timeout=30,
        )

    def _request(self, method, path, **kwargs):
        try:
            return getattr(self.client, method)(path, **kwargs)
        except httpx.ConnectError:
            click.echo(f"Error: Could not connect to {self.base_url}", err=True)
            sys.exit(1)
        except httpx.TimeoutException:
            click.echo("Error: Request timed out.", err=True)
            sys.exit(1)

    def get(self, path, **kwargs):
        return self._request("get", path, **kwargs)

    def post(self, path, **kwargs):
        return self._request("post", path, **kwargs)

    def put(self, path, **kwargs):
        return self._request("put", path, **kwargs)

    def delete(self, path, **kwargs):
        return self._request("delete", path, **kwargs)

    def page_url(self, slug, username=None, wiki_slug=None):
        if wiki_slug:
            # Build wiki subdomain URL
            from urllib.parse import urlparse
            parsed = urlparse(self.base_url)
            host = parsed.hostname or "jottit.org"
            port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
            return f"{parsed.scheme}://{wiki_slug}.{host}{port}/{slug}"
        if username:
            return f"{self.base_url}/@{username}/{slug}"
        return f"{self.base_url}/{slug}"

    def get_page_url(self, slug):
        r = self.get("/user")
        if r.status_code == 200:
            data = r.json()
            wikis = data.get("wikis", [])
            if wikis:
                return self.page_url(slug, wiki_slug=wikis[0]["slug"])
            username = data.get("username")
            return self.page_url(slug, username=username)
        return self.page_url(slug)
