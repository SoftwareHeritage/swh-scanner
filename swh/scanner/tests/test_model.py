# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import pytest

from swh.scanner.exceptions import InvalidDirectoryPath


def test_tree_add_node(example_tree, temp_folder):
    avail_paths = temp_folder["paths"].keys()

    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, False)

    for path, node in example_tree.children.items():
        assert path in avail_paths
        if node.children:
            for subpath, subnode in node.children.items():
                assert subpath in avail_paths


def test_to_json_no_one_present(example_tree, temp_folder):
    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, False)

    result = example_tree.toDict()

    assert len(result) == 6

    for _, node_info in result.items():
        assert node_info["known"] is False


def test_get_json_tree_all_present(example_tree, temp_folder):
    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, True)

    result = example_tree.toDict()

    assert len(result) == 6

    for _, node_info in result.items():
        assert node_info["known"] is True


def test_get_json_tree_only_one_present(example_tree, temp_folder):
    root = temp_folder["root"]
    filesample_path = temp_folder["filesample"]

    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, True if path == filesample_path else False)

    result = example_tree.toDict()

    assert len(result) == 6

    for path, node_attr in result.items():
        if path == str(root) + "/subdir0/filesample.txt":
            assert node_attr["known"] is True
        else:
            assert node_attr["known"] is False


def test_get_directories_info(example_tree, temp_folder):
    root_path = temp_folder["root"]
    filesample_path = temp_folder["filesample"]
    filesample2_path = temp_folder["filesample2"]
    subdir_path = temp_folder["subdir"].relative_to(root_path)
    subsubdir_path = temp_folder["subsubdir"].relative_to(root_path)

    for path, swhid in temp_folder["paths"].items():
        if path == filesample_path or path == filesample2_path:
            example_tree.addNode(path, swhid, True)
        else:
            example_tree.addNode(path, swhid, False)

    directories = example_tree.getDirectoriesInfo(example_tree.path)

    assert subsubdir_path not in directories
    assert directories[subdir_path] == (2, 2)


def test_get_files_from_dir(example_tree, temp_folder):
    subdir_path = temp_folder["subdir"]

    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, True)

    files = example_tree.getFilesFromDir(subdir_path)
    assert len(files) == 2


def test_get_files_source_path(example_tree, temp_folder):
    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, True)

    files = example_tree.getFilesFromDir(example_tree.path)
    assert len(files) == 1


def test_get_files_from_dir_raise_exception(example_tree, temp_folder):
    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, True)

    with pytest.raises(InvalidDirectoryPath):
        example_tree.getFilesFromDir("test/")
