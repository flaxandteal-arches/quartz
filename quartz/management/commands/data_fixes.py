"""Run numbered data-fix scripts from scripts/data_fixes and record which have run."""

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

PROJECT_ROOT = Path(settings.APP_ROOT).parent
FIXES_DIR = PROJECT_ROOT / "scripts" / "data_fixes"
FIX_FILE = re.compile(r"^\d{4}_.+\.(sql|sh)$")
REINDEX_GRAPHS = re.compile(r"^(?:--|#)\s*reindex-graphs:\s*(.+)$", re.MULTILINE)
LOCK_ID = 74_210_001


class Command(BaseCommand):
    help = "List data fixes and whether this environment has applied them; --apply runs the pending ones."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Run pending fixes in order, then reindex")
        parser.add_argument(
            "--mark-applied",
            nargs="+",
            metavar="FIX",
            help="Record fixes as applied without running them: numbers (0001), file names, or 'all'",
        )

    def handle(self, *args, **options):
        # Listing stays read-only.
        if options["apply"] or options["mark_applied"]:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS quartz_data_fixes ("
                    " name text PRIMARY KEY, checksum text NOT NULL,"
                    " applied_at timestamptz NOT NULL DEFAULT now(), duration_seconds numeric,"
                    " reindexed_at timestamptz)"
                )
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
                if not cursor.fetchone()[0]:
                    raise CommandError("Another data_fixes run holds the lock on this database.")
            try:
                if options["mark_applied"]:
                    self.mark_applied(options["mark_applied"])
                else:
                    self.apply_pending()
                    self.reindex()
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])

        self.print_status()

    def fixes(self):
        return sorted(path for path in FIXES_DIR.iterdir() if FIX_FILE.match(path.name))

    def applied(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('quartz_data_fixes') IS NOT NULL")
            if not cursor.fetchone()[0]:
                return {}
            cursor.execute("SELECT name, checksum, applied_at, reindexed_at FROM quartz_data_fixes")
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def mark_applied(self, requested):
        fixes = self.fixes()
        if requested == ["all"]:
            chosen = fixes
        else:
            chosen = []
            for name in requested:
                matches = [path for path in fixes if path.name == name or path.name.startswith(f"{name}_")]
                if len(matches) != 1:
                    raise CommandError(f"No single data fix matches {name!r}.")
                chosen.append(matches[0])
        with connection.cursor() as cursor:
            for path in chosen:
                cursor.execute(
                    "INSERT INTO quartz_data_fixes (name, checksum, reindexed_at) VALUES (%s, %s, now())"
                    " ON CONFLICT (name) DO NOTHING",
                    [path.name, checksum(path)],
                )
                self.stdout.write(f"Marked {path.name} as applied (not run).")

    def apply_pending(self):
        applied = self.applied()
        for path in self.fixes():
            if path.name in applied:
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"--- Applying {path.name} ---"))
            started = time.monotonic()
            result = subprocess.run(command_for(path), cwd=PROJECT_ROOT, env=script_env())
            if result.returncode != 0:
                raise CommandError(
                    f"{path.name} failed (exit {result.returncode}); later fixes were not run. "
                    "Fix it and re-run --apply: scripts are re-runnable."
                )
            # Recorded before the reindex so an interrupted reindex resumes next --apply.
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO quartz_data_fixes (name, checksum, duration_seconds) VALUES (%s, %s, %s)",
                    [path.name, checksum(path), round(time.monotonic() - started, 1)],
                )

    def reindex(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM quartz_data_fixes WHERE reindexed_at IS NULL")
            unindexed = [row[0] for row in cursor.fetchall()]
        if not unindexed:
            return

        graphs = set()
        for path in self.fixes():
            if path.name in unindexed:
                graphs.update(reindex_graphs(path))
        # clear_index=False: the default empties the graphs' documents first.
        if "all" in graphs:
            self.stdout.write(self.style.MIGRATE_HEADING("--- Reindexing all resources in Elasticsearch ---"))
            call_command("es", "index_resources", clear_index=False, quiet=True)
        elif graphs:
            self.stdout.write(self.style.MIGRATE_HEADING(f"--- Reindexing graphs {', '.join(sorted(graphs))} ---"))
            call_command("es", "index_resources_by_type", resource_types=",".join(sorted(graphs)), clear_index=False, quiet=True)

        self.stdout.write(self.style.MIGRATE_HEADING("--- Rebuilding arches-search ---"))
        call_command("arches_search", "reindex_database")

        with connection.cursor() as cursor:
            cursor.execute("UPDATE quartz_data_fixes SET reindexed_at = now() WHERE name = ANY(%s)", [unindexed])

    def print_status(self):
        applied = self.applied()
        for path in self.fixes():
            if path.name not in applied:
                self.stdout.write(f"  [ ] {path.name}  pending")
                continue
            recorded_checksum, applied_at, reindexed_at = applied[path.name]
            line = f"  [X] {path.name}  applied {applied_at:%Y-%m-%d %H:%M}"
            if reindexed_at is None:
                line += self.style.WARNING("  (reindex unfinished: run --apply)")
            if recorded_checksum != checksum(path):
                line += self.style.WARNING("  (file changed since it was applied)")
            self.stdout.write(line)


def reindex_graphs(path):
    match = REINDEX_GRAPHS.search(path.read_text())
    if not match:
        return set()
    return {graph.strip() for graph in match.group(1).split(",") if graph.strip()}


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_for(path):
    if path.suffix == ".sh":
        return ["bash", str(path)]
    db = settings.DATABASES["default"]
    return [
        "psql", "-h", db["HOST"], "-p", str(db["PORT"]), "-U", db["USER"], "-d", db["NAME"],
        "-v", "ON_ERROR_STOP=1", "-v", "apply=1", "-f", str(path),
    ]


def script_env():
    db = settings.DATABASES["default"]
    env = dict(os.environ, PGPASSWORD=str(db["PASSWORD"]))
    # So .sh fixes' `python` is this interpreter.
    env["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", "")])
    return env
