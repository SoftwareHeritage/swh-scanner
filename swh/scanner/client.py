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
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from swh.model.swhids import CoreSWHID

from .exceptions import error_response

logger = logging.getLogger(__name__)

# Maximum number of SWHIDs that can be requested by a single call to the
# Web API endpoint /known/
QUERY_LIMIT = 1000
MAX_RETRY = 10

KNOWN_EP = "known/"
GRAPH_RANDOMWALK_EP = "graph/randomwalk/"


def _get_chunk(swhids):
    """slice a list of `swhids` into smaller list of size QUERY_LIMIT"""
    for i in range(0, len(swhids), QUERY_LIMIT):
        yield swhids[i : i + QUERY_LIMIT]


def _parse_limit_header(response) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """parse the X-RateLimit Headers if any"""
    limit = response.headers.get("X-RateLimit-Limit")
    if limit is not None:
        limit = int(limit)
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is not None:
        remaining = int(remaining)
    reset = response.headers.get("X-RateLimit-Reset")
    if reset is not None:
        reset = int(reset)
    return (limit, remaining, reset)


class Client:
    """Manage requests to the Software Heritage Web API."""

    def __init__(
        self,
        api_url: str,
        session: aiohttp.ClientSession,
    ):
        self._sleep = 0
        self.api_url = api_url
        self.session = session
        self._known_endpoint = self.api_url + KNOWN_EP

    async def get_origin(self, swhid: CoreSWHID) -> Optional[Any]:
        """Walk the compressed graph to discover the origin of a given swhid"""
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
        requests = []

        swh_ids = [str(swhid) for swhid in swhids]

        if len(swhids) <= QUERY_LIMIT:
            return await self._make_request(swh_ids)
        else:
            for swhids_chunk in _get_chunk(swh_ids):
                task = asyncio.create_task(self._make_request(swhids_chunk))
                requests.append(task)

            res = await asyncio.gather(*requests)
            # concatenate list of dictionaries
            return dict(itertools.chain.from_iterable(e.items() for e in res))

    def _mark_success(self, limit=None, remaining=None, reset=None):
        """call when a request is successfully made, this will adjust the rate

        The extra argument can be used to transmit the X-RateLimit information
        from the server.  This will be used to adjust the request rate"""
        is_dbg = logger.isEnabledFor(logging.DEBUG)
        self._sleep = 0
        factor = 0
        current = time.time()
        if is_dbg:
            dbg_msg = f"HTTP GOOD {current:.2f}:"
        if limit is None or remaining is None or reset is None:
            if is_dbg:
                dbg_msg += " no rate limit data;"
        else:
            time_windows = reset - current
            if is_dbg:
                dbg_msg += f" requests={remaining}/{limit}"
                dbg_msg += f" reset-in={time_windows:.2f}"
            if time_windows > 0:
                used_up = remaining / limit
                if remaining <= 0:
                    # no more credit, we can sit up and wait.
                    #
                    # XXX we should warn the user. This can get very long.
                    self._sleep = time_windows
                    factor = -1
                elif 0.6 < used_up:
                    # let us not limit the first flight of request.
                    factor = 0
                else:
                    # the deeper we consume the credit the higher is the rate
                    # limiting, let's put a brake on our current rate the lower we get
                    #
                    # (The factor range from 1 to 1000)
                    factor = (0.4 + used_up) ** -1.5
                if factor >= 0:
                    self._sleep = ((time_windows / remaining)) * factor
        if is_dbg:
            dbg_msg += f"; sleep={self._sleep:.3f}"
            logger.debug(dbg_msg)

    def _mark_failure(self, limit=None, remaining=None, reset=None):
        """call when a request failed, this will reduce the request rate.

        The extra argument can be used to transmit the X-RateLimit information
        from the server.  This will be used to adjust the request rate"""
        is_dbg = logger.isEnabledFor(logging.DEBUG)
        current = time.time()
        if is_dbg:
            dbg_msg = f"HTTP BAD  {current:.2f}:"
        time_set = False
        if remaining is None or reset is None:
            if is_dbg:
                dbg_msg += " no rate limit data"
        else:
            wait_for = reset - current
            if is_dbg:
                dbg_msg += f" requests={remaining}/{limit}"
                dbg_msg += f" reset-in={wait_for:.2f}"
            if remaining <= 0:
                # Add some margin to please the rate limiting code
                wait_for *= 1.1
                if wait_for > 0 and wait_for >= self._sleep:
                    self._sleep = wait_for
                    time_set = True
        if not time_set:
            if self._sleep <= 0:
                self._sleep = 1
            else:
                self._sleep *= 2
        if is_dbg:
            dbg_msg += "; sleep={self._sleep:.3f}"
            logger.debug(dbg_msg)

    async def _make_request(self, swhids):
        endpoint = self._known_endpoint

        data = None

        retry = MAX_RETRY

        while data is None:
            # slow the pace of request if needed
            if self._sleep > 0:
                time.sleep(self._sleep)
            async with self.session.post(endpoint, json=swhids) as resp:
                rate_limit = _parse_limit_header(resp)
                if resp.status == 200:
                    try:
                        # inform of success before the await
                        self._mark_success(*rate_limit)
                        data = await resp.json()
                    except aiohttp.client_exceptions.ClientConnectionError:
                        raise
                    else:
                        break
                self._mark_failure(*rate_limit)
                retry -= 1
                if retry <= 0 or resp.status == 413:  # 413: Payload Too Large
                    error_response(resp.reason, resp.status, endpoint)
        return data
