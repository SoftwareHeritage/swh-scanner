# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import Flask, abort, request

from swh.scanner.exceptions import LargePayloadExc
from swh.scanner.policy import QUERY_LIMIT

from .data import fake_origin, unknown_swhids


def create_app(tmp_requests):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return "SWH scanner API"

    @app.route("/known/", methods=["POST"])
    def known():
        swhids = request.get_json()
        with open(tmp_requests, "a") as f:
            for swhid in swhids:
                f.write(swhid + "\n")

        if len(swhids) > QUERY_LIMIT:
            raise LargePayloadExc(
                f"The maximum number of SWHIDs this endpoint can receive is "
                f"{QUERY_LIMIT}"
            )

        res = {swhid: {"known": False} for swhid in swhids}
        for swhid in swhids:
            if swhid not in unknown_swhids:
                res[swhid]["known"] = True

        return res

    @app.route("/graph/randomwalk/<swhid>/ori/", methods=["GET"])
    def randomwalk(swhid):
        if swhid in fake_origin.keys():
            return fake_origin[swhid]
        else:
            abort(404)

    return app
