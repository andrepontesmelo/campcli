"""Migrate legacy ``profile.json`` to the DB-backed multi-profile system.

Called at daemon startup and before ``campcli profile *`` commands.
Reads the old JSON, creates a profile named ``default``, then deletes the file.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..domain.models import Profile
from ..domain.ports import ProfileRepo


def migrate_profile_json_to_db(
    profile_json_path: Path, profile_repo: ProfileRepo
) -> bool:
    """If ``profile.json`` exists and the DB has no profiles, read the JSON,
    create a profile named ``'default'`` with all fields, and delete the JSON.

    Returns ``True`` if migration occurred, ``False`` otherwise.
    Raises ``ValueError`` for malformed JSON.
    """
    if not profile_json_path.exists():
        return False

    existing = profile_repo.list_all()
    if existing:
        return False

    try:
        raw = json.loads(profile_json_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"profile.json is not valid JSON: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError("profile.json must be a JSON object")

    profile = profile_repo.create(
        Profile(
            name="default",
            max_horizon_months=raw.get("max_horizon_months", 3),
            max_drive_hours=raw.get("max_drive_hours", 3.0),
            min_start_date=raw.get("min_start_date"),
            rest_days_between_bookings=raw.get("rest_days_between_bookings", 14),
            enabled=True,
        )
    )

    # Atomicity: all child operations must succeed or the parent is rolled back.
    try:
        for pattern_str in raw.get("patterns", ["fri-sun"]):
            profile_repo.add_pattern("default", pattern_str)

        for entry in raw.get("allowed", []):
            park_query = entry.get("park", "")
            map_query = entry.get("map")
            profile_repo.add_park("default", park_query, map_query)

        for tg_id in raw.get("tg_allowed_ids", []):
            profile_repo.add_tg_id("default", tg_id)
    except Exception:
        profile_repo.delete("default")
        raise

    # Remove the legacy file — only reached after all child rows succeed.
    profile_json_path.unlink(missing_ok=True)
    return True
