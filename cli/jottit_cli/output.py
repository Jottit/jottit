import json
import sys

from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


class Formatter:
    def __init__(self, use_json=False, quiet=False):
        self.use_json = use_json
        self.quiet = quiet

    def success(self, data, breadcrumbs=None, message=None, quiet_value=None):
        if self.use_json:
            envelope = {"ok": True, "data": data}
            if breadcrumbs:
                envelope["breadcrumbs"] = breadcrumbs
            print(json.dumps(envelope, indent=2))
        elif self.quiet:
            if quiet_value is not None:
                print(quiet_value)
        else:
            if message:
                console.print(message)

    def error(self, message, breadcrumbs=None):
        if self.use_json:
            envelope = {"ok": False, "error": message}
            if breadcrumbs:
                envelope["breadcrumbs"] = breadcrumbs
            print(json.dumps(envelope, indent=2))
            sys.exit(1)
        elif self.quiet:
            err_console.print(message)
            sys.exit(1)
        else:
            err_console.print(f"[red]Error:[/red] {message}")
            sys.exit(1)

    def table(self, rows, columns, data_list=None, breadcrumbs=None, quiet_key=None):
        if self.use_json:
            envelope = {"ok": True, "data": data_list or []}
            if breadcrumbs:
                envelope["breadcrumbs"] = breadcrumbs
            print(json.dumps(envelope, indent=2))
        elif self.quiet:
            for row in rows:
                print(row.get(quiet_key, "")) if isinstance(row, dict) else print(row[0])
        else:
            t = Table(show_header=True, show_edge=False, pad_edge=False)
            for col in columns:
                t.add_column(col)
            for row in rows:
                if isinstance(row, dict):
                    t.add_row(*[str(row.get(c.lower(), "")) for c in columns])
                else:
                    t.add_row(*[str(v) for v in row])
            console.print(t)
