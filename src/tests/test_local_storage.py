from pathlib import Path

import pytest

from src.core.local_storage import (
    ensure_upload_tree,
    resolve_under_upload_root,
    resolve_upload_root,
    validate_upload_root_config,
)


def test_validate_upload_root_rejects_url():
    with pytest.raises(ValueError):
        validate_upload_root_config("s3://bucket/uploads")


def test_resolve_under_upload_root_blocks_traversal(tmp_path: Path):
    root = tmp_path / "uploads"
    ensure_upload_tree(root)
    (root / "videos/files/a.mp4").write_bytes(b"x")
    p = resolve_under_upload_root(root, "videos/files/a.mp4")
    assert p.is_file()
    with pytest.raises(Exception):
        resolve_under_upload_root(root, "../etc/passwd")


def test_resolve_upload_root_relative(tmp_path: Path):
    p = resolve_upload_root(tmp_path, "uploads")
    assert p == (tmp_path / "uploads").resolve()
