import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".jottitrc"
PAGES_PATH = Path.home() / ".jottit" / "pages.json"
DEFAULT_BASE_URL = "https://jottit.org"


@dataclass
class Config:
    token: str | None = None
    base_url: str = DEFAULT_BASE_URL


def load_config(token_override=None, base_url_override=None):
    config = Config()

    if CONFIG_PATH.exists():
        text = CONFIG_PATH.read_text()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"(\w+)\s*=\s*(.+)", line)
            if m:
                key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
                if key == "token":
                    config.token = value
                elif key == "base_url":
                    config.base_url = value

    if os.environ.get("JOTTIT_TOKEN"):
        config.token = os.environ["JOTTIT_TOKEN"]
    if os.environ.get("JOTTIT_BASE_URL"):
        config.base_url = os.environ["JOTTIT_BASE_URL"]

    if token_override:
        config.token = token_override
    if base_url_override:
        config.base_url = base_url_override

    return config


def save_config(token, base_url=None):
    lines = [f"token = {token}"]
    if base_url and base_url != DEFAULT_BASE_URL:
        lines.append(f"base_url = {base_url}")
    CONFIG_PATH.write_text("\n".join(lines) + "\n")
    CONFIG_PATH.chmod(0o600)


def _load_pages():
    if PAGES_PATH.exists():
        return json.loads(PAGES_PATH.read_text())
    return {}


def _save_pages(pages):
    PAGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAGES_PATH.write_text(json.dumps(pages, indent=2) + "\n")
    PAGES_PATH.chmod(0o600)


def store_page_secret(slug, secret, url):
    pages = _load_pages()
    pages[slug] = {"secret": secret, "url": url}
    _save_pages(pages)


def get_page_secret(slug):
    pages = _load_pages()
    entry = pages.get(slug)
    return entry["secret"] if entry else None


def remove_page_secret(slug):
    pages = _load_pages()
    pages.pop(slug, None)
    _save_pages(pages)


def list_page_secrets():
    return _load_pages()
