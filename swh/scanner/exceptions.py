# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


class InvalidObjectType(TypeError):
    pass


class InvalidDirectoryPath(Exception):
    pass


class APIError(Exception):
    def __str__(self):
        return '"%s"' % self.args


def error_response(reason: str, status_code: int, api_url: str):
    error_msg = f"{status_code} {reason}: '{api_url}'"
    raise APIError(error_msg)
