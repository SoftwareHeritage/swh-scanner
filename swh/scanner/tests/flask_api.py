# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import Flask, request

from swh.web.common.exc import LargePayloadExc

from .data import present_swhids


def create_app():
    app = Flask(__name__)

    @app.route("/known/", methods=["POST"])
    def known():
        swhids = request.get_json()

        if len(swhids) > 900:
            raise LargePayloadExc(
                "The maximum number of SWHIDs this endpoint can receive is 900"
            )

        res = {swhid: {"known": False} for swhid in swhids}
        for swhid in swhids:
            if swhid in present_swhids:
                res[swhid]["known"] = True

        return res

    return app
