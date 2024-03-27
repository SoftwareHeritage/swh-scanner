# Copyright (C) 2020-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path

from flask import Flask, render_template

from swh.model.from_disk import Directory

from ..data import MerkleNodeInfo, directory_content


def create_app(
    root_path: Path, source_tree: Directory, nodes_data: MerkleNodeInfo, summary
):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("./dashboard.html", root_path=root_path, summary=summary)

    @app.route("/results")
    def results():
        return render_template(
            "./results.html",
            root_path=root_path,
            source_tree=source_tree,
            nodes_data=nodes_data,
            directory_content=directory_content,
        )

    return app


def run_app(
    root_path: Path, source_tree: Directory, nodes_data: MerkleNodeInfo, summary
):
    app = create_app(root_path, source_tree, nodes_data, summary)
    app.run(debug=True)
