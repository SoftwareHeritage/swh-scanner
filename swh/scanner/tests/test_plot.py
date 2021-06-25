# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path

from swh.scanner.data import get_directory_data
from swh.scanner.plot import (
    build_hierarchical_df,
    compute_max_depth,
    generate_df_from_dirs,
)


def test_max_depth(source_tree, source_tree_dirs):
    dirs = [Path(dir_path) for dir_path in source_tree_dirs]
    max_depth = compute_max_depth(dirs)
    assert max_depth == 2


def test_generate_df_from_dirs(source_tree, source_tree_dirs, nodes_data):
    root = Path(source_tree.data["path"].decode())
    dirs = [Path(dir_path) for dir_path in source_tree_dirs]
    dirs_data = get_directory_data(root, source_tree, nodes_data)
    max_depth = compute_max_depth(dirs)
    metrics_columns = ["contents", "known"]
    levels_columns = ["lev" + str(i) for i in range(max_depth)]
    df_columns = levels_columns + metrics_columns

    actual_df = generate_df_from_dirs(dirs_data, df_columns, max_depth)

    expected_lev0_path = ["bar", "foo", "toexclude"]
    expected_lev1_path = ["bar/barfoo", "bar/barfoo2"]

    df_lev0 = actual_df["lev0"].tolist()
    df_lev1 = actual_df["lev1"].tolist()

    for path in expected_lev0_path:
        assert path in df_lev0

    for path in expected_lev1_path:
        assert path in df_lev1

    assert actual_df["contents"].sum() == 6
    assert actual_df["known"].sum() == 6


def test_build_hierarchical_df(source_tree, source_tree_dirs, nodes_data):
    root = Path(source_tree.data["path"].decode())
    dirs = [Path(dir_path) for dir_path in source_tree_dirs]
    dirs_data = get_directory_data(root, source_tree, nodes_data)
    max_depth = compute_max_depth(dirs)
    metrics_columns = ["contents", "known"]
    levels_columns = ["lev" + str(i) for i in range(max_depth)]
    df_columns = levels_columns + metrics_columns

    actual_df = generate_df_from_dirs(dirs_data, df_columns, max_depth)

    actual_result = build_hierarchical_df(
        actual_df, levels_columns, metrics_columns, root
    )

    assert actual_result["parent"][0] == "bar"
    assert actual_result["parent"][1] == "foo"
    assert actual_result["contents"][1] == 3
    assert actual_result["id"][8] == root
    assert actual_result["known"][8] == 100
