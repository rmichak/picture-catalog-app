from __future__ import annotations

from app.photolib.dedupe import FileRecord, classify


def _rec(
    audit_id: int,
    name: str,
    sha: str,
    *,
    phash: str | None = None,
    mtime: float = 1000.0,
    has_year: bool = False,
    path: str | None = None,
) -> FileRecord:
    return FileRecord(
        audit_id=audit_id,
        path=path or f"/src/{name}",
        name=name,
        sha256=sha,
        phash=phash,
        size_bytes=100,
        mtime_ts=mtime,
        has_year_in_path=has_year,
    )


def test_unique_files_are_singletons() -> None:
    r1 = _rec(1, "a.jpg", "aaa")
    r2 = _rec(2, "b.jpg", "bbb")
    groups, singletons = classify([r1, r2])
    assert groups == []
    assert {r.audit_id for r in singletons} == {1, 2}


def test_exact_dup_picks_earliest_mtime() -> None:
    r1 = _rec(1, "img.jpg", "sha1", mtime=2000)
    r2 = _rec(2, "img.jpg", "sha1", mtime=1000)
    r3 = _rec(3, "img.jpg", "sha1", mtime=3000)
    groups, singletons = classify([r1, r2, r3])
    assert len(groups) == 1
    g = groups[0]
    assert g.layer == "exact"
    assert g.canonical.audit_id == 2
    assert {d.audit_id for d in g.duplicates} == {1, 3}
    assert {r.audit_id for r in singletons} == {2}


def test_filename_pattern_dup() -> None:
    base = _rec(1, "vacation.jpg", "sha-base", mtime=1000)
    paren = _rec(2, "vacation (1).jpg", "sha-paren", mtime=2000)
    copy = _rec(3, "vacation copy.jpg", "sha-copy", mtime=3000)
    copy2 = _rec(4, "vacation copy 2.jpg", "sha-copy2", mtime=4000)
    groups, singletons = classify([base, paren, copy, copy2])
    assert len(groups) == 1
    g = groups[0]
    assert g.layer == "filename"
    assert g.canonical.audit_id == 1
    assert {d.audit_id for d in g.duplicates} == {2, 3, 4}
    assert singletons == [base]


def test_filename_suffix_without_base_stays_singleton() -> None:
    only_suffix = _rec(1, "vacation (1).jpg", "sha-x")
    groups, singletons = classify([only_suffix])
    assert groups == []
    assert singletons == [only_suffix]


def test_perceptual_groups_close_phashes() -> None:
    a = _rec(1, "a.jpg", "sha-a", phash="00000000" + "00000000")
    b = _rec(2, "b.jpg", "sha-b", phash="00000001" + "00000000")
    c = _rec(3, "c.jpg", "sha-c", phash="ffffffff" + "ffffffff")
    groups, singletons = classify([a, b, c])
    perceptual = [g for g in groups if g.layer == "perceptual"]
    assert len(perceptual) == 1
    in_group = {perceptual[0].canonical.audit_id, *(d.audit_id for d in perceptual[0].duplicates)}
    assert in_group == {1, 2}
    assert {r.audit_id for r in singletons} == {3}


def test_canonical_prefers_year_in_path() -> None:
    no_year = _rec(1, "img.jpg", "sha", mtime=1000, has_year=False)
    with_year = _rec(
        2, "img.jpg", "sha", mtime=2000, has_year=True, path="/Camera Uploads/2018/img.jpg"
    )
    groups, _ = classify([no_year, with_year])
    assert groups[0].canonical.audit_id == 2


def test_layer_order_exact_before_filename() -> None:
    """Two files matching both exact-sha AND filename-pattern only count as exact."""
    a = _rec(1, "img.jpg", "same", mtime=1000)
    b = _rec(2, "img (1).jpg", "same", mtime=2000)
    groups, _ = classify([a, b])
    assert len(groups) == 1
    assert groups[0].layer == "exact"
