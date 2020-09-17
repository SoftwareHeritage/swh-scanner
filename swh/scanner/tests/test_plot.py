# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from swh.scanner.plot import (
    build_hierarchical_df,
    compute_max_depth,
    generate_df_from_dirs,
)


def test_max_depth(temp_folder, example_dirs):
    root = temp_folder["root"]
    max_depth = compute_max_depth(example_dirs, root)
    assert max_depth == 2


def test_generate_df_from_dirs(temp_folder, example_dirs):
    root = temp_folder["root"]
    max_depth = compute_max_depth(example_dirs, root)
    metrics_columns = ["contents", "known"]
    levels_columns = ["lev" + str(i) for i in range(max_depth)]
    df_columns = levels_columns + metrics_columns

    actual_df = generate_df_from_dirs(example_dirs, df_columns, root, max_depth)

    # assert root is empty
    assert actual_df["lev0"][0] == ""
    assert actual_df["lev1"][0] == ""

    # assert subdir has correct contents information
    assert actual_df["contents"][1] == 2
    assert actual_df["known"][1] == 2

    # assert subsubdir has correct level information
    assert actual_df["lev0"][2] == "subdir0"
    assert actual_df["lev1"][2] == "subdir0/subsubdir"


def test_build_hierarchical_df(temp_folder, example_dirs):
    root = temp_folder["root"]
    max_depth = compute_max_depth(example_dirs, root)
    metrics_columns = ["contents", "known"]
    levels_columns = ["lev" + str(i) for i in range(max_depth)]
    df_columns = levels_columns + metrics_columns

    actual_df = generate_df_from_dirs(example_dirs, df_columns, root, max_depth)

    actual_result = build_hierarchical_df(
        actual_df, levels_columns, metrics_columns, root
    )

    assert actual_result["parent"][1] == "subdir0"
    assert actual_result["contents"][1] == 2
    assert actual_result["id"][5] == root
    assert actual_result["known"][5] == 75
