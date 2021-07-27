# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import Flask, request

from .db import Db
from .exceptions import LargePayloadExc
from .policy import QUERY_LIMIT


def create_app(db: Db):
    """Backend for swh-scanner, implementing the /known endpoint of the
    Software Heritage Web API"""
    app = Flask(__name__)

    @app.route("/api/1/known/", methods=["POST"])
    def known():
        swhids = request.get_json()

        if len(swhids) > QUERY_LIMIT:
            raise LargePayloadExc(
                f"The maximum number of SWHIDs this endpoint can receive is"
                f"{QUERY_LIMIT}"
            )

        cur = db.conn.cursor()
        res = {swhid: {"known": db.known(swhid, cur)} for swhid in swhids}
        cur.close()

        return res

    return app


def run(host: str, port: int, db: Db):
    """Serve the local database"""
    app = create_app(db)
    app.run(host, port, debug=True)
