import importlib.util
import os

from db import (
    claim_page,
    find_or_create_user,
    get_db,
    get_page_meta,
    get_user,
    run_migrations,
    save_page,
    set_user_username,
)


def _load_backfill_migration():
    path = os.path.join(
        os.path.join(os.path.dirname(__file__), ".."),
        "migrations",
        "006_backfill_usernames.py",
    )
    spec = importlib.util.spec_from_file_location("backfill_usernames", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# SQL migrations are applied and tracked in schema_migrations (idempotent)
def test_migration_applies_and_tracks():
    migrations_dir = os.path.join(
        os.path.join(os.path.dirname(__file__), ".."), "migrations"
    )
    test_file = os.path.join(migrations_dir, "999_test_migration.sql")
    try:
        with open(test_file, "w") as f:
            f.write(
                "CREATE TABLE IF NOT EXISTS migration_test_table (id SERIAL PRIMARY KEY);"
            )

        run_migrations()

        with get_db() as conn:
            row = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'migration_test_table')"
            ).fetchone()
            assert list(row.values())[0] is True

            row = conn.execute(
                "SELECT filename FROM schema_migrations WHERE filename = '999_test_migration.sql'"
            ).fetchone()
            assert row is not None

        # Run again — should be a no-op
        run_migrations()

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM schema_migrations WHERE filename = '999_test_migration.sql'"
            ).fetchone()
            assert count["cnt"] == 1
    finally:
        os.unlink(test_file)


# A failed migration doesn't roll back previously applied ones
def test_migration_failure_does_not_affect_previous():
    migrations_dir = os.path.join(
        os.path.join(os.path.dirname(__file__), ".."), "migrations"
    )
    good_file = os.path.join(migrations_dir, "998_good.sql")
    bad_file = os.path.join(migrations_dir, "999_bad.sql")
    try:
        with open(good_file, "w") as f:
            f.write(
                "CREATE TABLE IF NOT EXISTS migration_good_table (id SERIAL PRIMARY KEY);"
            )
        with open(bad_file, "w") as f:
            f.write("INVALID SQL STATEMENT;")

        try:
            run_migrations()
        except Exception:
            pass

        with get_db() as conn:
            # Good migration should have been applied
            row = conn.execute(
                "SELECT filename FROM schema_migrations WHERE filename = '998_good.sql'"
            ).fetchone()
            assert row is not None

            # Bad migration should not be tracked
            row = conn.execute(
                "SELECT filename FROM schema_migrations WHERE filename = '999_bad.sql'"
            ).fetchone()
            assert row is None
    finally:
        for f in [good_file, bad_file]:
            if os.path.exists(f):
                os.unlink(f)


# Backfill migration generates usernames from email prefixes
def test_backfill_usernames_from_email():
    m = _load_backfill_migration()

    user_id = find_or_create_user("alice@example.com")
    with get_db() as conn:
        conn.execute("UPDATE users SET username = NULL WHERE id = %s", (user_id,))
        conn.commit()

    with get_db() as conn:
        m.migrate(conn)
        conn.commit()

    user = get_user(user_id)
    assert user["username"] == "alice"


# Backfill adds a suffix when the derived username is already taken
def test_backfill_usernames_with_suffix_if_taken():
    m = _load_backfill_migration()

    user1 = find_or_create_user("bob@example.com")
    set_user_username(user1, "bob")

    user2 = find_or_create_user("bob@other.com")
    with get_db() as conn:
        conn.execute("UPDATE users SET username = NULL WHERE id = %s", (user2,))
        conn.commit()

    with get_db() as conn:
        m.migrate(conn)
        conn.commit()

    user = get_user(user2)
    assert user["username"] is not None
    assert user["username"].startswith("bob-")
    assert user["username"] != "bob"


# After backfill, pages are accessible on the generated subdomain
def test_backfill_usernames_makes_page_accessible(client):
    m = _load_backfill_migration()

    user_id = find_or_create_user("legacy@example.com")
    save_page("mypage", "# Hello\n\nWorld", False)
    page_meta = get_page_meta("mypage")
    claim_page(page_meta["id"], user_id)

    with get_db() as conn:
        conn.execute("UPDATE users SET username = NULL WHERE id = %s", (user_id,))
        conn.commit()

    with get_db() as conn:
        m.migrate(conn)
        conn.commit()

    user = get_user(user_id)
    host = f"{user['username']}.jottit.localhost:8000"
    r = client.get("/mypage", headers={"Host": host})
    assert r.status_code == 200
