# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

"""
This module is an interface to interact with the local database
where the SWHIDs will be saved for the local API.

SWHIDs can be added directly from an input file.
"""

from io import TextIOWrapper
import logging
from pathlib import Path
import sqlite3
from typing import Iterable

from swh.core.utils import grouper
from swh.model.swhids import SWHID_RE

from .exceptions import DBError


class Db:
    """Local database interface"""

    def __init__(self, db_file: Path):
        self.db_file: Path = db_file
        self.conn: sqlite3.Connection = sqlite3.connect(
            db_file, check_same_thread=False
        )

    def close(self):
        """Close the connection to the database."""
        self.conn.close()

    def create_table(self, cur: sqlite3.Cursor):
        """Create the table where the SWHIDs will be stored."""
        cur.execute("""CREATE TABLE IF NOT EXISTS swhids (swhid text PRIMARY KEY)""")

    def add(self, swhids: Iterable[str], chunk_size: int, cur: sqlite3.Cursor):
        """Insert the SWHID inside the database."""
        for swhids_chunk in grouper(swhids, chunk_size):
            cur.executemany(
                """INSERT INTO swhids VALUES (?)""",
                [(swhid_chunk,) for swhid_chunk in swhids_chunk],
            )

    @staticmethod
    def iter_swhids(lines: Iterable[str]) -> Iterable[str]:
        lineno = 0
        for line in lines:
            lineno += 1
            swhid = line.rstrip()
            if SWHID_RE.match(swhid):
                yield swhid
            else:
                logging.error("ignoring invalid SWHID on line %d: %s", lineno, swhid)

    def create_from(
        self, input_file: TextIOWrapper, chunk_size: int, cur: sqlite3.Cursor
    ):
        """Create a new database with the SWHIDs present inside the input file."""
        try:
            self.create_table(cur)
            cur.execute("PRAGMA synchronous = OFF")
            cur.execute("PRAGMA journal_mode = OFF")
            self.add(self.iter_swhids(input_file), chunk_size, cur)
            cur.close()
            self.conn.commit()
        except sqlite3.Error as e:
            raise DBError(f"SQLite error: {e}")

    def known(self, swhid: str, cur: sqlite3.Cursor):
        """Check if a given SWHID is present or not inside the local database."""
        cur.execute("""SELECT 1 FROM swhids WHERE swhid=?""", (swhid,))
        res = cur.fetchone()

        return res is not None
