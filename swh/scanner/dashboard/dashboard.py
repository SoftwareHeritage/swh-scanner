# Copyright (C) 2020-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from swh.model.from_disk import Directory

from ..data import MerkleNodeInfo, get_content_from


def generate_table_body(
    dir_path: bytes, source_tree: Directory, nodes_data: MerkleNodeInfo
):
    """
    Generate the data_table from the path taken from the chart.

    For each file builds the html table rows showing the known status, a local link to
    the file and the relative SoftWare Heritage persistent IDentifier (SWHID).
    """
    contents = get_content_from(dir_path, source_tree, nodes_data)
    data = []
    for cnt, attr in contents.items():
        file_path = Path(cnt.decode())
        file_name = file_path.parts[len(file_path.parts) - 1]
        full_file_path = Path(Path(dir_path.decode()), file_path)
        data.append(
            html.Tr(
                [
                    html.Td("✔" if attr["known"] else ""),
                    html.Td(html.A(file_name, href="file://" + str(full_file_path))),
                    html.Td(attr["swhid"]),
                ]
            )
        )

    return [html.Tbody(data)]


def generate_sunburst_view(graph_obj: go):
    """Generate the sunburst view from a graph object.

    It's made of a sunburst chart and a details table.
    Clicking an area of the chart display the details of known files in a table.
    The table is updated through the global `update_files_table` callback.
    """
    fig = go.Figure()
    fig.add_trace(go.Sunburst(graph_obj))
    fig.update_layout(
        minreducedheight=400,
        height=600,
    )
    return [
        dbc.Row(
            [
                html.H2("Sunburst Chart", className="display-6"),
                html.P(
                    "Click a chart area to display details of known files",
                    className="lead",
                ),
                html.Hr(),
            ]
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dcc.Graph(figure=fig, id="sunburst_chart"),
                    ],
                    width=6,
                ),
                dbc.Col(
                    [
                        html.H3(id="directory_title"),
                        dbc.Table(
                            id="files_table",
                            hover=True,
                            responsive=True,
                            striped=True,
                        ),
                    ],
                    width=6,
                ),
            ]
        ),
    ]


def run_app(
    graph_obj: go, root_path: str, source_tree: Directory, nodes_data: MerkleNodeInfo
):
    external_stylesheets = [dbc.themes.MATERIA]
    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    app.title = "Swh Scanner"
    app.layout = dbc.Container(
        [
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.Img(
                                            src=dash.get_asset_url("swh-logo.svg"),
                                            height="48px",
                                        )
                                    ],
                                    width=3,
                                ),
                                dbc.Col(
                                    [html.H1("SWH Scanner", className="display-6")],
                                    width=9,
                                ),
                            ],
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        [
                            html.H1(f"Results for {root_path}", className="display-6"),
                        ],
                        width=9,
                    ),
                ],
                className="p-4 bg-light",
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Tabs(
                        [
                            dbc.Tab(
                                generate_sunburst_view(graph_obj),
                                label="Sunburst chart",
                            ),
                        ]
                    )
                ),
                className="p-4",
            ),
        ],
        fluid=True,
    )

    @app.callback(
        [Output("files_table", "children"), Output("directory_title", "children")],
        [Input("sunburst_chart", "clickData")],
    )
    def update_files_table(click_data):
        """
        Callback that takes the input (directory path) from the chart and
        update the `files_table` children with the relative files.
        """
        table_header = [
            html.Thead(
                html.Tr([html.Th("KNOWN"), html.Th("FILE NAME"), html.Th("SWHID")])
            )
        ]

        if click_data is not None:
            full_path = click_data["points"][0]["label"]
            return (
                table_header
                + generate_table_body(full_path.encode(), source_tree, nodes_data),
                full_path,
            )
        else:
            return (table_header, "")

    app.run_server(debug=True, use_reloader=True)
