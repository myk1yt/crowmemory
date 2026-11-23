"""migrate_from_v1.py - v1.5 value_bank.json -> v2 crow.db migrator (S10).

Non-destructive: reads the v1.5 JSON bank, never touches v1 files. Imports
each entry through CrowDB.ingest with its stored register/importance/polarity
(polarity = sign(stored polarity_net or stored polarity, default +) x stored
importance as magnitude), then restores stored timestamps/ingest_count.

Also seeds <home>/system_prompt.md from the v1 repo copy (audit spec §6.1):
byte-identical copy, only when the target does not already exist, unless
--force-prompt (a forced overwrite is backed up to .bak.<timestamp> first).

Re-run guard: after a clean apply (errors == 0) the migrator writes
<home>/.migrated_v1.json = {"src_sha256": sha256(abspath + size + mtime_ns of
the source bank), "processed": n, "inserted": n, "merged": n, "applied_at": ts}.
A later apply whose source fingerprint still matches and whose <home>/crow.db
exists returns at once with "skipped_fingerprint_match": true and touches no
memory row, which is what an installer re-run needs: re-ingesting an already
migrated bank merges every row again and ratchets importance and polarity_net.
--force-migrate bypasses the guard. The guard never short-circuits prompt
seeding, so --force-prompt still works on a guarded re-run.

Report counts: processed (entries that passed the junk/invalid filters),
inserted, merged, rejected, skipped_junk, skipped_invalid, errors, plus a
"prompt" block (src/dst/would_copy/copied/skipped_exists/error) and a
"fingerprint" block (the stored or newly written .migrated_v1.json, else
null). Legacy "migrated" stays equal to processed. Each processed row ends in
exactly one of inserted / merged / rejected, so processed == inserted +
merged + rejected holds only when errors == 0: a row that raised before its
outcome was counted stays in processed with no outcome bucket, and a row that
raised during the timestamp restore is counted both in its outcome bucket and
in errors. skipped_junk and skipped_invalid are counted outside processed.
In --dry-run nothing is written: inserted/merged/rejected stay 0, the prompt
block only reports would_copy, and the guard is not consulted.

CLI:
    python core/migrate_from_v1.py --dry-run [--src-json PATH] [--home PATH]
    python core/migrate_from_v1.py --apply  [--src-json PATH] [--home PATH]
                                   [--keep-junk] [--src-prompt PATH]
                                   [--force-prompt] [--force-migrate]
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time

try:
    from crow_db import CrowDB, REGISTERS
    from crow_sanitize import scrub_text
except ImportError:
    from .crow_db import CrowDB, REGISTERS
    from .crow_sanitize import scrub_text

JUNK_KEYS = {"k", "test key", "test", "hello"}
JUNK_VALUE_MARKERS = ("[CHECKPOINT]", "Whiteboard state:", "Dep analysis:")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(_REPO_ROOT, "memory", "value_bank.json")
DEFAULT_SRC_PROMPT = os.path.join(_REPO_ROOT, "memory", "system_prompt.md")


def _is_junk(entry: dict) -> bool:
    key = str(entry.get("key", "")).strip().lower()
    if key in JUNK_KEYS:
        return True
    value = str(entry.get("value", ""))
    return any(marker in value for marker in JUNK_VALUE_MARKERS)


def _entry_polarity(entry: dict) -> float:
    """Contract S10: sign(polarity_net or stored polarity) x importance."""
    raw = entry.get("polarity_net", entry.get("polarity"))
    sign = 1.0
    if raw is not None:
        try:
            sign = 1.0 if float(raw) >= 0 else -1.0
        except (TypeError, ValueError):
            sign = 1.0
    try:
        magnitude = abs(float(entry.get("importance", 1.0)))
    except (TypeError, ValueError):
        magnitude = 1.0
    return sign * magnitude


def _resolve_home(home: str | os.PathLike | None) -> str:
    if home is None:
        home = os.environ.get("CROW_HOME") or os.path.join(
            os.path.expanduser("~"), ".crow-memory")
    return os.fspath(home)


FINGERPRINT_NAME = ".migrated_v1.json"


def fingerprint_path(home: str | os.PathLike | None) -> str:
    return os.path.join(_resolve_home(home), FINGERPRINT_NAME)


def source_fingerprint(src_json: str | os.PathLike) -> str:
    """sha256 over the source bank's file CONTENT (R2-2).

    Content, not metadata: a restored, copied or cloud-synced bank with the
    same bytes must keep matching, or every restore re-runs the migration and
    ratchets importance/polarity_net (CR-1). mtime is never part of the digest;
    it is recorded separately as informational metadata.
    """
    return hashlib.sha256(_source_bytes(src_json)).hexdigest()


def _source_bytes(src_json: str | os.PathLike) -> bytes:
    """Read the source bank once, as bytes (the caller hashes and parses it)."""
    with open(os.fspath(src_json), "rb") as f:
        return f.read()


def read_fingerprint(home: str | os.PathLike | None) -> dict | None:
    """Stored .migrated_v1.json as a dict, or None when absent/unreadable."""
    try:
        with open(fingerprint_path(home), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_fingerprint(home: str | os.PathLike | None, src_sha256: str,
                      report: dict, src_mtime: float | None = None) -> dict:
    """Atomically record the applied source + outcome counts.

    ``src_mtime`` is informational only: it is never compared, so it can never
    re-trigger a migration on its own (R2-2).
    """
    payload = {"src_sha256": src_sha256,
               "src_mtime": src_mtime,
               "processed": report["processed"],
               "inserted": report["inserted"],
               "merged": report["merged"],
               "applied_at": time.time()}
    path = fingerprint_path(home)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return payload


def _migrate_system_prompt(src_prompt: str | os.PathLike | None,
                           home: str | os.PathLike | None,
                           apply: bool, force_prompt: bool,
                           report: dict) -> None:
    """Seed <home>/system_prompt.md from the v1 repo copy (audit spec §6.1).

    Byte-identical copy, only when the target does not already exist, unless
    force_prompt. A forced overwrite is backed up to .bak.<timestamp> first.
    Never raises: failures land in report["prompt"]["error"].
    """
    prompt = report["prompt"]
    src = os.fspath(src_prompt) if src_prompt else DEFAULT_SRC_PROMPT
    dst_dir = _resolve_home(home)
    dst = os.path.join(dst_dir, "system_prompt.md")
    prompt["src"], prompt["dst"] = src, dst
    try:
        if not os.path.isfile(src):
            return
        target_exists = os.path.exists(dst)
        prompt["would_copy"] = force_prompt or not target_exists
        if not apply:
            return
        if target_exists and not force_prompt:
            prompt["skipped_exists"] = True
            return
        os.makedirs(dst_dir, exist_ok=True)
        if target_exists:  # forced overwrite: back up the live file first
            shutil.copy2(dst, dst + ".bak." + time.strftime("%Y%m%d_%H%M%S"))
        shutil.copyfile(src, dst)  # byte-identical
        prompt["copied"] = True
    except OSError as exc:
        prompt["error"] = str(exc)[:200]


def migrate(src_json: str | os.PathLike, home: str | os.PathLike | None,
            apply: bool, scrub_junk: bool = True,
            src_prompt: str | os.PathLike | None = None,
            force_prompt: bool = False,
            force_migrate: bool = False) -> dict:
    src_json = os.fspath(src_json)
    report = {"migrated": 0, "processed": 0, "inserted": 0, "merged": 0,
              "rejected": 0, "skipped_junk": 0, "skipped_invalid": 0,
              "errors": 0, "per_register": {}, "dry_run": not apply,
              "skipped_fingerprint_match": False, "fingerprint": None,
              "prompt": {"src": None, "dst": None, "would_copy": False,
                         "copied": False, "skipped_exists": False,
                         "error": None}}

    src_sha256 = None
    src_mtime = None
    raw_bytes = None
    try:
        src_mtime = os.stat(os.fspath(src_json)).st_mtime
    except OSError:
        pass
    try:
        # one read: the same bytes are hashed and then parsed (R2-2)
        raw_bytes = _source_bytes(src_json)
        src_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    except OSError:
        pass
    stored = read_fingerprint(home)
    report["fingerprint"] = stored
    if (apply and not force_migrate and src_sha256
            and isinstance(stored, dict)
            and stored.get("src_sha256") == src_sha256
            and os.path.exists(os.path.join(_resolve_home(home), "crow.db"))):
        # The same bank was already applied into this home: re-ingesting it
        # would merge every row again and ratchet importance/polarity_net.
        report["skipped_fingerprint_match"] = True
        _migrate_system_prompt(src_prompt, home, apply, force_prompt, report)
        return report

    if raw_bytes is not None:
        bank = json.loads(raw_bytes.decode("utf-8"))
    else:
        with open(src_json, encoding="utf-8") as f:
            bank = json.load(f)
    if isinstance(bank, dict):
        bank = bank.get("entries") or bank.get("items") or []

    db = None
    try:
        if apply:
            db = CrowDB(home)
        for entry in bank:
            try:
                if scrub_junk and _is_junk(entry):
                    report["skipped_junk"] += 1
                    continue
                register = str(entry.get("register", ""))
                key = scrub_text(str(entry.get("key", "")))
                value = scrub_text(str(entry.get("value", "")))
                if register not in REGISTERS or not key or not value:
                    report["skipped_invalid"] += 1
                    continue
                report["per_register"][register] = \
                    report["per_register"].get(register, 0) + 1
                report["processed"] += 1
                if not apply:
                    continue
                res = db.ingest(key, value, register,
                                polarity=_entry_polarity(entry),
                                project=entry.get("project"))
                status = res.get("status")
                if status == "rejected":
                    report["rejected"] += 1
                    continue
                # count the row exactly once, right after ingest succeeds;
                # a later timestamp-restore fault only bumps "errors"
                if status == "merged":
                    report["merged"] += 1
                else:
                    report["inserted"] += 1
                # preserve v1 timestamps / ingest_count where available
                ts = entry.get("timestamp")
                count = entry.get("ingest_count")
                params, sets = [], []
                try:
                    if ts is not None:
                        ts_f = float(ts)
                        sets.append("created_at = ?")
                        params.append(ts_f)
                        sets.append("updated_at = ?")
                        params.append(ts_f)
                except (TypeError, ValueError):
                    pass
                try:
                    if count is not None:
                        sets.append("ingest_count = MAX(ingest_count, ?)")
                        params.append(int(count))
                except (TypeError, ValueError):
                    pass
                if sets:
                    db.conn.execute(
                        f"UPDATE memories SET {', '.join(sets)} "
                        "WHERE entry_uid = ?", (*params,
                                                res["entry_uid"]))
            except Exception as exc:  # per-entry fault isolation
                report["errors"] += 1
                report.setdefault("error_detail", []).append(str(exc)[:200])
        if db is not None:
            db.conn.commit()
        # legacy total key: migrated == processed (entries that passed the
        # junk/invalid filters, whether they inserted, merged or rejected)
        report["migrated"] = report["processed"]
        _migrate_system_prompt(src_prompt, home, apply, force_prompt, report)
        # A fingerprint only records a clean apply; with errors > 0 the next
        # run must stay unguarded so the failed rows can be retried.
        if apply and src_sha256 and report["errors"] == 0:
            try:
                report["fingerprint"] = write_fingerprint(home, src_sha256,
                                                          report, src_mtime)
            except OSError as exc:  # a guard write must not fail the migration
                report.setdefault("error_detail", []).append(
                    "fingerprint: " + str(exc)[:200])
    finally:
        if db is not None:
            db.close()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Crow Memory v1.5 value_bank.json to v2 crow.db")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="print per-register counts only; no writes")
    mode.add_argument("--apply", action="store_true",
                      help="write into the v2 home (default ~/.crow-memory)")
    parser.add_argument("--src-json", default=DEFAULT_SRC,
                        help=f"source value_bank.json (default: {DEFAULT_SRC})")
    parser.add_argument("--home", default=None,
                        help="target CROW_HOME (default: env CROW_HOME or "
                             "~/.crow-memory)")
    parser.add_argument("--keep-junk", action="store_true",
                        help="do not filter junk keys/values")
    parser.add_argument("--src-prompt", default=DEFAULT_SRC_PROMPT,
                        help=f"source system_prompt.md (default: "
                             f"{DEFAULT_SRC_PROMPT})")
    parser.add_argument("--force-prompt", action="store_true",
                        help="overwrite an existing <home>/system_prompt.md "
                             "(default: never overwrite; the overwritten file "
                             "is backed up to .bak.<timestamp>)")
    parser.add_argument("--force-migrate", action="store_true",
                        help="re-apply the bank even when the source "
                             "fingerprint in <home>/.migrated_v1.json still "
                             "matches (default: skip, so a re-run cannot "
                             "merge and re-weight already migrated rows)")
    args = parser.parse_args(argv)

    if not os.path.exists(args.src_json):
        print(json.dumps({"status": "error",
                          "message": f"src not found: {args.src_json}"}))
        return 2
    report = migrate(args.src_json, args.home, apply=args.apply,
                     scrub_junk=not args.keep_junk,
                     src_prompt=args.src_prompt,
                     force_prompt=args.force_prompt,
                     force_migrate=args.force_migrate)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
