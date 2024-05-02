# Copyright (C) 2020-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path

from flask import Flask, get_template_attribute, jsonify, render_template
from markupsafe import escape

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

    @app.route("/api/v1/html-tree/<path:directory_path>")
    def api_html_tree_get(directory_path=None):
        """Given a directory path get its HTML tree representation"""
        if directory_path is None:
            return jsonify({})

        def get_source_tree(directory_path):
            """Return the source_tree object of the directory name"""
            try:
                return source_tree[directory_path.encode()]
            except KeyError:
                return None

        # Get the source tree object for this path
        st = get_source_tree(directory_path)
        # Get the `render_source_tree` Jinja macro
        macro = get_template_attribute("./partials/tree.html", "render_source_tree")
        # Render the html snippet
        html = macro(root_path, st, nodes_data, directory_content)
        res = {"path": escape(directory_path), "html": html}
        return jsonify(res)

    return app


def run_app(
    root_path: Path, source_tree: Directory, nodes_data: MerkleNodeInfo, summary
):
    app = create_app(root_path, source_tree, nodes_data, summary)
    debug = False

    app.run(debug=debug)
