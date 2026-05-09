from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.photolib.hashing import sha256_file
from app.photolib.move import (
    move_with_sidecar,
    no_date_target,
    organized_target,
    quarantine_target,
    resolve_collision,
    review_target,
)


def test_organized_target_year_month() -> None:
    root = Path("/dst")
    p = organized_target(root, datetime(2021, 8, 12, 17, 56), "img.jpg")
    assert p == Path("/dst/2021/08/img.jpg")


def test_quarantine_target_sanitizes_group_id() -> None:
    p = quarantine_target(Path("/dst"), "sha:abcdef123456", "x.jpg")
    assert p == Path("/dst/_duplicates/sha-abcdef123456/x.jpg")


def test_review_and_no_date_paths() -> None:
    assert review_target(Path("/d"), "phash:g00001", "x.jpg") == Path(
        "/d/_review-perceptual/phash-g00001/x.jpg"
    )
    assert no_date_target(Path("/d"), "x.jpg") == Path("/d/_no-date/x.jpg")


def test_resolve_collision_target_free(tmp_path: Path) -> None:
    target = tmp_path / "img.jpg"
    final, action = resolve_collision(target, "anything")
    assert final == target and action == "ok"


def test_resolve_collision_identical_skip(tmp_path: Path) -> None:
    target = tmp_path / "img.jpg"
    target.write_bytes(b"hello")
    sha = sha256_file(target)
    final, action = resolve_collision(target, sha)
    assert final == target and action == "skip-identical"


def test_resolve_collision_appends_when_different(tmp_path: Path) -> None:
    target = tmp_path / "img.jpg"
    target.write_bytes(b"hello")
    final, action = resolve_collision(target, "different-sha")
    assert action == "appended"
    assert final == tmp_path / "img__001.jpg"


def test_move_with_sidecar(tmp_path: Path) -> None:
    src = tmp_path / "src.jpg"
    src.write_bytes(b"data")
    dst = tmp_path / "out" / "dst.jpg"
    move_with_sidecar(src, dst, sidecar={"reason": "test", "n": 1})
    assert not src.exists()
    assert dst.read_bytes() == b"data"
    sidecar = dst.with_suffix(dst.suffix + ".reorg.json")
    assert json.loads(sidecar.read_text()) == {"reason": "test", "n": 1}


def test_move_creates_parents(tmp_path: Path) -> None:
    src = tmp_path / "a.jpg"
    src.write_bytes(b"x")
    dst = tmp_path / "deep" / "nested" / "dir" / "a.jpg"
    move_with_sidecar(src, dst)
    assert dst.read_bytes() == b"x"
