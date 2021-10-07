# Copyright (C) 2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

"""
Minimal async web client for the Software Heritage Web API.

This module could be removed when
`T2635 <https://forge.softwareheritage.org/T2635>` is implemented.
"""

import asyncio
import itertools
from typing import Any, Dict, List, Optional

import aiohttp

from swh.model.swhids import CoreSWHID

from .exceptions import error_response

# Maximum number of SWHIDs that can be requested by a single call to the
# Web API endpoint /known/
QUERY_LIMIT = 1000

KNOWN_EP = "known/"
GRAPH_RANDOMWALK_EP = "graph/randomwalk/"


class Client:
    """Manage requests to the Software Heritage Web API.
    """

    def __init__(self, api_url: str, session: aiohttp.ClientSession):
        self.api_url = api_url
        self.session = session

    async def get_origin(self, swhid: CoreSWHID) -> Optional[Any]:
        """Walk the compressed graph to discover the origin of a given swhid
        """
        endpoint = (
            f"{self.api_url}{GRAPH_RANDOMWALK_EP}{str(swhid)}/ori/?direction="
            f"backward&limit=-1&resolve_origins=true"
        )
        res = None
        async with self.session.get(endpoint) as resp:
            if resp.status == 200:
                res = await resp.text()
                res = res.rstrip()
                return res
            if resp.status != 404:
                error_response(resp.reason, resp.status, endpoint)

        return res

    async def known(self, swhids: List[CoreSWHID]) -> Dict[str, Dict[str, bool]]:
        """API Request to get information about the SoftWare Heritage persistent
        IDentifiers (SWHIDs) given in input.

        Args:
            swhids: a list of CoreSWHID instances
            api_url: url for the API request

        Returns:
            A dictionary with:

            key:
                string SWHID searched
            value:
                value['known'] = True if the SWHID is found
                value['known'] = False if the SWHID is not found

        """
        endpoint = self.api_url + KNOWN_EP
        requests = []

        def get_chunk(swhids):
            for i in range(0, len(swhids), QUERY_LIMIT):
                yield swhids[i : i + QUERY_LIMIT]

        async def make_request(swhids):
            swhids = [str(swhid) for swhid in swhids]
            async with self.session.post(endpoint, json=swhids) as resp:
                if resp.status != 200:
                    error_response(resp.reason, resp.status, endpoint)

                return await resp.json()

        if len(swhids) > QUERY_LIMIT:
            for swhids_chunk in get_chunk(swhids):
                requests.append(asyncio.create_task(make_request(swhids_chunk)))

            res = await asyncio.gather(*requests)
            # concatenate list of dictionaries
            return dict(itertools.chain.from_iterable(e.items() for e in res))
        else:
            return await make_request(swhids)
