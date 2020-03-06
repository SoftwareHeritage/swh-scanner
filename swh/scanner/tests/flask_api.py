# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from flask import Flask, request

from .data import present_pids


def create_app():
    app = Flask(__name__)

    @app.route('/known/', methods=['POST'])
    def known():
        pids = request.get_json()
        res = {pid: {'known': False} for pid in pids}
        for pid in pids:
            if pid in present_pids:
                res[pid]['known'] = True

        return res

    return app
