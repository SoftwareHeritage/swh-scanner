# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path

import dash
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objects as go

from ..model import Tree


def generate_table_body(dir_path: Path, source: Tree):
    """
    Generate the data_table from the path taken from the chart.

    For each file builds the html table rows showing the known status, a local link to
    the file and the relative SoftWare Heritage persistent IDentifier (SWHID).
    """
    data = []
    for file_info in source.getFilesFromDir(dir_path):
        for file_path, attr in file_info.items():
            file_path = Path(file_path)
            file_name = file_path.parts[len(file_path.parts) - 1]
            data.append(
                html.Tr(
                    [
                        html.Td("✔" if attr["known"] else ""),
                        html.Td(
                            html.A(file_name, href="file://" + str(file_path.resolve()))
                        ),
                        html.Td(attr["swhid"]),
                    ]
                )
            )

    return [html.Tbody(data)]


def run_app(graph_obj: go, source: Tree):
    app = dash.Dash(__name__)
    fig = go.Figure().add_trace(graph_obj)

    fig.update_layout(height=800,)

    table_header = [
        html.Thead(html.Tr([html.Th("KNOWN"), html.Th("FILE NAME"), html.Th("SWHID")]))
    ]

    app.layout = html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [dcc.Graph(id="sunburst_chart", figure=fig),], className="col",
                    ),
                    html.Div(
                        [
                            html.H3(id="directory_title"),
                            dbc.Table(
                                id="files_table",
                                hover=True,
                                responsive=True,
                                striped=True,
                            ),
                        ],
                        className="col",
                    ),
                ],
                className="row",
            ),
        ]
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
        if click_data is not None:
            raw_path = click_data["points"][0]["label"]
            full_path = (
                source.path.joinpath(raw_path)
                if raw_path != str(source.path)
                else Path(raw_path)
            )
            return table_header + generate_table_body(full_path, source), str(full_path)
        else:
            return "", ""

    app.run_server(debug=True, use_reloader=True)
