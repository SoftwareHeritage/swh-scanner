# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


def test_tree_add_node(example_tree, temp_folder):
    avail_paths = temp_folder['paths'].keys()

    for path, pid in temp_folder['paths'].items():
        example_tree.addNode(path, pid)

    for path, node in example_tree.children.items():
        assert path in avail_paths
        if node.children:
            for subpath, subnode in node.children.items():
                assert subpath in avail_paths


def test_get_json_tree_all_not_present(example_tree, temp_folder):
    for path, pid in temp_folder['paths'].items():
        example_tree.addNode(path)

    json_tree = example_tree.getTree()

    assert len(json_tree) == 0


def test_get_json_tree_all_present(example_tree, temp_folder):
    for path, pid in temp_folder['paths'].items():
        example_tree.addNode(path, pid)

    tree_dict = example_tree.getTree()

    assert len(tree_dict) == 3
    # since subdir have a pid, it can't have a children path
    assert tree_dict['subdir0'] is not dict


def test_get_json_tree_only_one_present(example_tree, temp_folder):
    filesample_path = temp_folder['filesample']

    for path, pid in temp_folder['paths'].items():
        if path == filesample_path:
            example_tree.addNode(path, pid)
        else:
            example_tree.addNode(path)

    tree_dict = example_tree.getTree()

    assert len(tree_dict) == 1
    assert tree_dict['subdir0']['filesample.txt']


def test_get_directories_info(example_tree, temp_folder):
    root_path = temp_folder['root']
    filesample_path = temp_folder['filesample']
    filesample2_path = temp_folder['filesample2']
    subdir_path = temp_folder['subdir'].relative_to(root_path)
    subsubdir_path = temp_folder['subsubdir'].relative_to(root_path)

    for path, pid in temp_folder['paths'].items():
        if path == filesample_path or path == filesample2_path:
            example_tree.addNode(path, pid)
        else:
            example_tree.addNode(path)

    directories = example_tree.getDirectoriesInfo(example_tree.path)

    assert subsubdir_path not in directories
    assert directories[subdir_path] == (2, 2)
