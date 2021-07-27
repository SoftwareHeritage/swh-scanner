# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from swh.scanner.db import Db
from swh.scanner.policy import QUERY_LIMIT

from .data import present_swhids


def test_db_create_from(tmp_path, test_swhids_sample):
    tmp_dbfile = tmp_path / "tmp_db.sqlite"

    db = Db(tmp_dbfile)
    cur = db.conn.cursor()
    db.create_from(test_swhids_sample, QUERY_LIMIT, cur)

    for swhid in present_swhids:
        cur = db.conn.cursor()
        assert db.known(swhid, cur)


def test_db_create_from_one_not_present(tmp_path, test_swhids_sample):
    not_present_swhid = "swh:1:cnt:fa8eacf43d8646129ae8adfa1648f9307d999999"
    swhids = present_swhids + [not_present_swhid]

    tmp_dbfile = tmp_path / "tmp_db.sqlite"

    db = Db(tmp_dbfile)
    cur = db.conn.cursor()
    db.create_from(test_swhids_sample, QUERY_LIMIT, cur)

    for swhid in swhids:
        cur = db.conn.cursor()
        if swhid != not_present_swhid:
            assert db.known(swhid, cur)
        else:
            assert not db.known(swhid, cur)
