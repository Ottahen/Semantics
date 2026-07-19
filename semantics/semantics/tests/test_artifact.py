# Copyright (c) 2026, Semantics
# SPDX-License-Identifier: BSD-2-Clause
# See the LICENSE file in the project root for the full BSD 2-Clause text.

import json
import zipfile

import pytest

from pro.artifact import ArtifactBuilder, ArtifactManifest


def test_build_zip_contains_added_files(tmp_path):
    builder = ArtifactBuilder()
    builder.add_file("src/app.py", "print('hi')")
    builder.add_file("README.md", "# hi")
    zip_path = builder.build_zip(tmp_path / "out.zip")

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "src/app.py" in names
        assert "README.md" in names
        assert zf.read("src/app.py").decode() == "print('hi')"


def test_manifest_is_valid_json_in_zip(tmp_path):
    builder = ArtifactBuilder()
    builder.add_file("a.txt", "x")
    builder.add_manifest(ArtifactManifest(task="do a thing", files_changed=["a.txt"], model="claude-sonnet-4-6", tokens_used=42, duration_seconds=1.5))
    zip_path = builder.build_zip(tmp_path / "out.zip")

    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["task"] == "do a thing"
    assert manifest["files_changed"] == ["a.txt"]
    assert manifest["tokens_used"] == 42


def test_add_existing_file_copies_content(tmp_path):
    src = tmp_path / "existing.py"
    src.write_text("x = 1")
    builder = ArtifactBuilder()
    builder.add_existing_file(src, "renamed.py")
    zip_path = builder.build_zip(tmp_path / "out2.zip")

    with zipfile.ZipFile(zip_path) as zf:
        assert zf.read("renamed.py").decode() == "x = 1"


def test_builder_cannot_be_reused_after_build(tmp_path):
    builder = ArtifactBuilder()
    builder.add_file("a.txt", "x")
    builder.build_zip(tmp_path / "out3.zip")
    with pytest.raises(RuntimeError):
        builder.add_file("b.txt", "y")


def test_context_manager_cleans_up(tmp_path):
    with ArtifactBuilder() as builder:
        builder.add_file("a.txt", "x")
        temp_dir = builder.temp_dir
        assert temp_dir.exists()
    assert not temp_dir.exists()
