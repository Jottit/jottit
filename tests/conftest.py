import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import db as db_module
import psycopg
import pytest

from app import app as flask_app
from routes import limiter

limiter.enabled = False

TEST_DB = "jottit_test"


@pytest.fixture(autouse=True)
def test_db():
    conn = psycopg.connect("dbname=postgres", autocommit=True)
    conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.execute(f"CREATE DATABASE {TEST_DB}")
    conn.close()

    db_module.DATABASE = f"dbname={TEST_DB}"
    db_module.reset_pool()

    with db_module.get_db() as conn:
        with open("schema.sql") as f:
            conn.execute(f.read())
        conn.commit()

    db_module.run_migrations()

    yield

    db_module.reset_pool()
    db_module.DATABASE = "dbname=jottit_dev"

    conn = psycopg.connect("dbname=postgres", autocommit=True)
    conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.close()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["SESSION_COOKIE_DOMAIN"] = ".localhost"
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.test_client() as client:
        yield client


def create_user_with_username(client, email, username, slug):
    from db import (
        assign_page_to_site,
        claim_page,
        create_site,
        find_or_create_user,
        get_page_meta,
        save_page,
        set_user_username,
    )

    user_id = find_or_create_user(email)
    set_user_username(user_id, username)
    site_id = create_site(user_id, username)
    save_page(slug, "# Test\n\nContent", "listed", site_id=site_id)
    page_meta = get_page_meta(slug, site_id=site_id)
    claim_page(page_meta["id"], user_id)
    return user_id
