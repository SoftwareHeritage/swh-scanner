# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path

import pytest

from swh.model.exceptions import ValidationError
from swh.scanner.data import (
    MerkleNodeInfo,
    directory_content,
    get_directory_data,
    has_dirs,
)


def test_merkle_node_data_wrong_args():
    nodes_data = MerkleNodeInfo()

    with pytest.raises(ValidationError):
        nodes_data["wrong key"] = {"known": True}

    with pytest.raises(ValidationError):
        nodes_data["swh:1:dir:17d207da3804cc60a77cba58e76c3b2f767cb112"] = "wrong value"


def test_get_directory_data(source_tree, nodes_data):
    root = Path(source_tree.data["path"].decode())
    dirs_data = get_directory_data(root, source_tree, nodes_data)

    assert len(dirs_data) == 5


def test_directory_content(source_tree, nodes_data):
    foo_dir = source_tree[b"foo"]
    foo_content = directory_content(foo_dir, nodes_data)
    assert foo_content[0] == 3
    assert foo_content[1] == 3


def test_has_dirs(source_tree):
    assert has_dirs(source_tree)
