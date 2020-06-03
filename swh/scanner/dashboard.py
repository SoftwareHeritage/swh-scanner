# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from .model import Tree

import plotly.graph_objects as go
import dash
import dash_core_components as dcc
import dash_html_components as html


def run_app(graph_obj: go, source: Tree):
    app = dash.Dash(__name__)
    fig = go.Figure().add_trace(graph_obj)

    fig.update_layout(height=800,)

    app.layout = html.Div(
        [html.Div([html.Div([dcc.Graph(id="sunburst_chart", figure=fig),]),]),]
    )

    app.run_server(debug=True, use_reloader=False)
