# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import dash_html_components as html

from swh.scanner.dashboard.dashboard import generate_table_body


def test_generate_table_body(example_tree, temp_folder):
    subdir_path = temp_folder["subdir"]

    for path, swhid in temp_folder["paths"].items():
        example_tree.addNode(path, swhid, True)

    generated_body = generate_table_body(subdir_path, example_tree)

    expected_body = [
        html.Tbody(
            [
                html.Tr(
                    [
                        html.Td("✔"),
                        html.Td(
                            html.A(
                                children="filesample.txt",
                                href=f"file://{subdir_path}/filesample.txt",
                            )
                        ),
                        html.Td("swh:1:cnt:e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"),
                    ]
                ),
                html.Tr(
                    [
                        html.Td("✔"),
                        html.Td(
                            html.A(
                                children="filesample2.txt",
                                href=f"file://{subdir_path}/filesample2.txt",
                            )
                        ),
                        html.Td("swh:1:cnt:e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"),
                    ]
                ),
            ]
        )
    ]

    # workaround: dash_html_component.__eq__ checks for object identity only
    assert str(generated_body) == str(expected_body)
