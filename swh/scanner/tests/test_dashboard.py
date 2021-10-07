# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import dash_html_components as html

from swh.model.swhids import CoreSWHID, ObjectType
from swh.scanner.dashboard.dashboard import generate_table_body
from swh.scanner.data import MerkleNodeInfo


def test_generate_table_body(source_tree):
    chart_path = b"/bar/barfoo"
    dir_path = source_tree[b"/bar/barfoo"].data["path"].decode()
    nodes_data = MerkleNodeInfo()
    # CoreSWHID of 'another-quote.org'
    known_cnt_swhid = CoreSWHID(
        object_type=ObjectType.CONTENT,
        object_id=b"\x136\x93\xb1%\xba\xd2\xb4\xac1\x855\xb8I\x01\xeb\xb1\xf6\xb68",
    )
    nodes_data[known_cnt_swhid] = {"known": True}

    generated_body = generate_table_body(chart_path, source_tree, nodes_data)

    expected_body = [
        html.Tbody(
            [
                html.Tr(
                    [
                        html.Td("✔"),
                        html.Td(
                            html.A(
                                children="another-quote.org",
                                href=f"file://{dir_path}/another-quote.org",
                            )
                        ),
                        html.Td("swh:1:cnt:133693b125bad2b4ac318535b84901ebb1f6b638"),
                    ]
                ),
            ]
        )
    ]

    # workaround: dash_html_component.__eq__ checks for object identity only
    assert str(generated_body) == str(expected_body)
