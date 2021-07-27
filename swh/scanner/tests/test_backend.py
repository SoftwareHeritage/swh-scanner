# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from swh.scanner.backend import create_app
from swh.scanner.db import Db
from swh.scanner.policy import QUERY_LIMIT

from .data import present_swhids


def test_backend_endpoint_all_present(tmp_path, live_server, test_swhids_sample):
    tmp_dbfile = tmp_path / "tmp_db.sqlite"
    db = Db(tmp_dbfile)
    cur = db.conn.cursor()
    db.create_from(test_swhids_sample, QUERY_LIMIT, cur)

    app = create_app(db)

    with app.test_client() as test_client:
        res = test_client.post("/api/1/known/", json=present_swhids)

        for swhid, attr in res.json.items():
            assert attr["known"]


def test_backend_endpoint_one_not_present(tmp_path, live_server, test_swhids_sample):
    tmp_dbfile = tmp_path / "tmp_db.sqlite"
    not_present_swhid = "swh:1:cnt:fa8eacf43d8646129ae8adfa1648f9307d999999"
    swhids = present_swhids + [not_present_swhid]

    db = Db(tmp_dbfile)
    cur = db.conn.cursor()
    db.create_from(test_swhids_sample, QUERY_LIMIT, cur)

    app = create_app(db)

    with app.test_client() as test_client:
        res = test_client.post("/api/1/known/", json=swhids)

        for swhid, attr in res.json.items():
            if swhid != not_present_swhid:
                assert attr["known"]
            else:
                assert not attr["known"]


def test_backend_large_payload_exc(tmp_path, live_server, test_swhids_sample):
    tmp_dbfile = tmp_path / "tmp_db.sqlite"
    swhid = "swh:1:cnt:fa8eacf43d8646129ae8adfa1648f9307d999999"
    # the backend supports up to 1000 SWHID requests
    swhids = [swhid for n in range(1001)]
    db = Db(tmp_dbfile)
    cur = db.conn.cursor()
    db.create_from(test_swhids_sample, QUERY_LIMIT, cur)

    app = create_app(db)

    with app.test_client() as test_client:
        res = test_client.post("/api/1/known/", json=swhids)
        assert res.status_code != 200
