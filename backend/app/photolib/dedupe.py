from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from app.photolib.hashing import hamming

# Matches " (1)", " copy", " copy 2", " 2" before extension.
_SUFFIX_PATTERN = re.compile(
    r"^(?P<base>.+?)(?:\s*\(\d+\)|\s+copy(?:\s*\d+)?|\s+\d+)(?P<ext>\.[^.]+)$",
    re.IGNORECASE,
)

PERCEPTUAL_DISTANCE_THRESHOLD = 6


@dataclass(frozen=True)
class FileRecord:
    """One entry in the dedupe input set. Frozen so multiprocessing workers can pass it cleanly."""

    audit_id: int
    path: str
    name: str
    sha256: str
    phash: str | None
    size_bytes: int
    mtime_ts: float
    has_year_in_path: bool


@dataclass
class DupGroup:
    group_id: str
    layer: str  # "exact" | "filename" | "perceptual"
    canonical: FileRecord
    duplicates: list[FileRecord]


def classify(records: Iterable[FileRecord]) -> tuple[list[DupGroup], list[FileRecord]]:
    """Return (groups, singletons). Each record appears in exactly one place."""
    records = list(records)
    groups: list[DupGroup] = []

    after_layer1, exact_groups = _layer_exact(records)
    groups.extend(exact_groups)

    after_layer2, filename_groups = _layer_filename(after_layer1)
    groups.extend(filename_groups)

    after_layer3, perceptual_groups = _layer_perceptual(after_layer2)
    groups.extend(perceptual_groups)

    return groups, after_layer3


def _layer_exact(records: list[FileRecord]) -> tuple[list[FileRecord], list[DupGroup]]:
    by_sha: dict[str, list[FileRecord]] = defaultdict(list)
    for r in records:
        by_sha[r.sha256].append(r)
    groups: list[DupGroup] = []
    survivors: list[FileRecord] = []
    for sha, items in by_sha.items():
        if len(items) == 1:
            survivors.append(items[0])
            continue
        canonical = _pick_canonical(items)
        dups = [r for r in items if r is not canonical]
        groups.append(
            DupGroup(group_id=f"sha:{sha[:12]}", layer="exact", canonical=canonical, duplicates=dups)
        )
        survivors.append(canonical)
    return survivors, groups


def _layer_filename(records: list[FileRecord]) -> tuple[list[FileRecord], list[DupGroup]]:
    by_base: dict[str, list[FileRecord]] = defaultdict(list)
    suffix_records: list[tuple[FileRecord, str]] = []
    for r in records:
        m = _SUFFIX_PATTERN.match(r.name)
        if m:
            base = (m["base"] + m["ext"]).lower()
            suffix_records.append((r, base))
        else:
            by_base[r.name.lower()].append(r)
    groups: list[DupGroup] = []
    consumed: set[int] = set()
    for r, base in suffix_records:
        candidates = by_base.get(base, [])
        if not candidates:
            continue
        canonical = _pick_canonical(candidates)
        gid = f"name:{base}"
        existing = next((g for g in groups if g.group_id == gid), None)
        if existing is None:
            groups.append(
                DupGroup(group_id=gid, layer="filename", canonical=canonical, duplicates=[r])
            )
        else:
            existing.duplicates.append(r)
        consumed.add(r.audit_id)
    survivors = [r for r in records if r.audit_id not in consumed]
    return survivors, groups


def _layer_perceptual(records: list[FileRecord]) -> tuple[list[FileRecord], list[DupGroup]]:
    """Group photos with phash within hamming distance threshold via union-find."""
    photos = [r for r in records if r.phash]
    others = [r for r in records if not r.phash]
    if not photos:
        return others, []

    parent = list(range(len(photos)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # O(n^2). Acceptable up to ~10K. For 80K, swap in BK-tree or LSH later.
    for i in range(len(photos)):
        for j in range(i + 1, len(photos)):
            if hamming(photos[i].phash, photos[j].phash) <= PERCEPTUAL_DISTANCE_THRESHOLD:  # type: ignore[arg-type]
                union(i, j)

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(len(photos)):
        clusters[find(i)].append(i)

    groups: list[DupGroup] = []
    in_group: set[int] = set()
    for n, members in enumerate(clusters.values(), start=1):
        if len(members) < 2:
            continue
        items = [photos[i] for i in members]
        canonical = _pick_canonical(items)
        dups = [r for r in items if r is not canonical]
        groups.append(
            DupGroup(
                group_id=f"phash:g{n:05d}", layer="perceptual", canonical=canonical, duplicates=dups
            )
        )
        in_group.update(r.audit_id for r in items)

    survivors = others + [r for r in photos if r.audit_id not in in_group]
    return survivors, groups


def _pick_canonical(items: list[FileRecord]) -> FileRecord:
    """Tiebreaks: has_year_in_path > earliest mtime > shortest name > path lexicographic."""
    return min(
        items,
        key=lambda r: (
            not r.has_year_in_path,
            r.mtime_ts,
            len(r.name),
            r.path,
        ),
    )
