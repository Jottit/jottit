from jottit_cli.client import JottitClient
from jottit_cli.config import load_config


def get_client(ctx, require_auth=True):
    config = load_config(
        token_override=ctx.obj.get("token_override"),
        base_url_override=ctx.obj.get("base_url_override"),
    )
    fmt = ctx.obj["formatter"]
    if require_auth and not config.token:
        fmt.error(
            "Not authenticated. Run 'jottit login' or set JOTTIT_TOKEN.",
            breadcrumbs=[{"label": "Login", "command": "jottit login"}],
        )
    return JottitClient(config), fmt
