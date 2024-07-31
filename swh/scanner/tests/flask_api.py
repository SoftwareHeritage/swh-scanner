# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import Flask, abort, request

from swh.model.swhids import CoreSWHID, QualifiedSWHID
from swh.scanner.exceptions import LargePayloadExc
from swh.web.client.client import KNOWN_QUERY_LIMIT

from .data import fake_origin, fake_release, fake_revision, unknown_swhids


def create_app(tmp_requests, tmp_accesses):
    app = Flask(__name__)
    app.config["SERVER_NAME"] = "localhost"
    app.config["DEBUG"] = True

    @app.route("/")
    def index():
        return "SWH scanner API"

    @app.route("/known/", methods=["POST"])
    def known():
        swhids = request.get_json()
        with open(tmp_requests, "a") as f:
            for swhid in swhids:
                f.write(swhid + "\n")

        with open(tmp_accesses, "a") as f:
            f.write(f"{len(swhids)}\n")

        if len(swhids) > KNOWN_QUERY_LIMIT:
            raise LargePayloadExc(
                f"The maximum number of SWHIDs this endpoint can receive is "
                f"{KNOWN_QUERY_LIMIT}"
            )

        res = {swhid: {"known": False} for swhid in swhids}
        for swhid in swhids:
            if swhid not in unknown_swhids:
                res[swhid]["known"] = True

        return res

    @app.route("/revision/<swhid>/", methods=["GET"])
    def dummy_revision(swhid):
        return {}

    @app.route("/release/<swhid>/", methods=["GET"])
    def dummy_release(swhid):
        return {}

    @app.route("/graph/leaves/<swhid>/", methods=["GET"])
    def find_leaves(swhid):
        try:
            target = request.args.get("return_types")
            if target == "ori":
                mapping = fake_origin
            elif target == "rel":
                mapping = fake_release
            elif target == "rev":
                mapping = fake_revision
            else:
                raise KeyError('no mapping to fake "%s" request' % target)
            if swhid in mapping:
                return mapping[swhid]
            else:
                abort(404)
        except Exception as exc:
            print(exc)
            raise

    @app.route("/provenance/whereare/", methods=["GET", "POST"])
    def whereare():
        swhids = request.get_json()
        result = []
        for source in swhids:
            anchor = fake_release.get(source)
            if anchor is None:
                anchor = fake_revision.get(source)
            if anchor is None:
                result.append(None)
            else:
                anchor_id = CoreSWHID.from_string(anchor)
                origin = fake_origin.get(source)
                swhid = CoreSWHID.from_string(source)
                provenance = QualifiedSWHID(
                    object_type=swhid.object_type,
                    object_id=swhid.object_id,
                    anchor=anchor_id,
                    origin=origin,
                )
                result.append(str(provenance))

        return result

    return app
