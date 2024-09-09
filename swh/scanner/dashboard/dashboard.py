# Copyright (C) 2020-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json
from pathlib import Path
import socket
from typing import Any, Dict, Optional
import webbrowser
import functools

from flask import Flask, get_template_attribute, jsonify, render_template
from flask.json.provider import DefaultJSONProvider
from markupsafe import escape

from swh.model.from_disk import Directory
from swh.model.swhids import CoreSWHID, ObjectType
from swh.web.client.client import WebAPIClient

from ..data import MerkleNodeInfo, _get_provenance_info


def open_browser_if_graphical(port):
    term_browsers = ("www-browser", "links", "elinks", "lynx", "w3m")
    if webbrowser.get().name not in term_browsers:
        webbrowser.open_new(f"http://127.0.0.1:{port}/")


class CustomJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(obj):
        if isinstance(obj, CoreSWHID):
            return str(obj)
        else:
            return DefaultJSONProvider.default(obj)


ANCHOR_CACHE_SIZE = 1024


def create_app(
    config: Dict[str, Any],
    root_path: Path,
    source_tree: Directory,
    nodes_data: MerkleNodeInfo,
    summary: Dict[str, Any],
    # some test does not use a webclient, so Optional
    web_client: Optional[WebAPIClient],
):
    flask_config = {
        "DEBUG": config["debug_http"],
    }
    # temporary to ease diff in MR
    client = web_client

    app = Flask(__name__)
    app.config.from_mapping(flask_config)
    app.jinja_env.add_extension("jinja2.ext.do")
    app.json_provider_class = CustomJSONProvider
    app.json = CustomJSONProvider(app)

    @app.route("/")
    def index():
        return render_template(
            "dashboard.html", root_path=root_path, summary=summary, config=config
        )

    @app.route("/results")
    def results():
        return render_template(
            "results.html",
            root_path=root_path,
            source_tree=source_tree,
            nodes_data=nodes_data,
            json=json,
            summary=summary,
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
        macro = get_template_attribute("partials/tree.html", "render_source_tree")
        # Render the html snippet
        html = macro(root_path, st, nodes_data, json, summary)
        res = {"path": escape(directory_path), "html": html}
        return jsonify(res)

    @functools.lru_cache(maxsize=ANCHOR_CACHE_SIZE)
    def revision_info(swhid: CoreSWHID):
        assert web_client is not None
        return web_client.revision(swhid)

    @functools.lru_cache(maxsize=ANCHOR_CACHE_SIZE)
    def release_info(swhid: CoreSWHID):
        assert web_client is not None
        return web_client.release(swhid)

    @app.route("/api/v1/provenance/<swhid>")
    def api_provenance_get(swhid: str = ""):
        """Given a swhid fetch provenance information"""
        assert client is not None

        if not swhid:
            return jsonify({})
        try:
            swhid_o = CoreSWHID.from_string(swhid)
            qualified_swhid = _get_provenance_info(client, swhid_o)
            if qualified_swhid is None:
                return jsonify({})

            info = qualified_swhid.qualifiers()
            anchor = qualified_swhid.anchor
            if anchor is not None:
                anchor_type = anchor.object_type
                if anchor_type == ObjectType.REVISION:
                    data = revision_info(anchor)
                    # Get the `show_revision` Jinja macro
                    macro = get_template_attribute(
                        "partials/provenance.html", "show_revision"
                    )
                    # Render the html snippet
                    info["revision"] = macro(data)
                elif anchor_type == ObjectType.RELEASE:
                    data = release_info(anchor)
                    # Get the `show_release` Jinja macro
                    macro = get_template_attribute(
                        "partials/provenance.html", "show_release"
                    )
                    # Render the html snippet
                    info["release"] = macro(data)

            return jsonify(info)
        except ValueError as e:
            return jsonify({"error": "Failed to decode JSON: {}".format(str(e))}), 500

    return app


def run_app(
    config: Dict[str, Any],
    root_path: Path,
    source_tree: Directory,
    nodes_data: MerkleNodeInfo,
    summary: Dict[str, Any],
    web_client: WebAPIClient,
):
    app = create_app(config, root_path, source_tree, nodes_data, summary, web_client)

    debug = config["debug_http"] or False

    retries = 0
    while True:
        retries += 1
        # Flask allows us to give `0` to get a free port, but we have no way
        # of getting the allocated port, which we need to open the browser.
        # So do it ourselves.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
        sock.close()
        # This will open multiple ones in case of a race, but we have no simple
        # alternative. This is already enough code.
        open_browser_if_graphical(port=port)
        try:
            app.run(debug=debug, port=port)
        except socket.error:
            if retries > 3:
                raise
            # This raced against another process after the `socket.close`, retry
