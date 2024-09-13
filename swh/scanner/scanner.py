# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import requests.status_codes

from swh.model.cli import model_of_dir
from swh.model.from_disk import Directory
from swh.web.client.client import DEFAULT_RETRY_REASONS, WebAPIClient

from .data import (
    MerkleNodeInfo,
    add_provenance,
    get_ignore_patterns_templates,
    get_vcs_ignore_patterns,
    init_merkle_node_info,
    parse_ignore_patterns_template,
)
from .output import get_output_class
from .policy import RandomDirSamplingPriority


class Progress:
    """default no-op Progress class"""

    class Step(enum.Enum):
        DISK_SCAN = enum.auto()
        KNOWN_DISCOVERY = enum.auto()
        PROVENANCE = enum.auto()

    def __init__(self, step: Step, total: Optional[int] = None, **kwargs):
        pass

    def increment(self, count=1):
        pass

    def update(self, current_count, total=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass


def get_webapi_client(config: Dict[str, Any]):
    api_url = config["web-api"]["url"]
    kwargs = {}
    # TODO: Better retrieve realm and client id directly from the oidc client?
    if "keycloak" in config:
        realm_name = config["keycloak"].get("realm_name")
        client_id = config["keycloak"].get("client_id")
        if (
            realm_name
            and client_id
            and "keycloak_tokens" in config
            and config["keycloak_tokens"][realm_name][client_id]
        ):
            auth_token = config["keycloak_tokens"][realm_name][client_id]
            kwargs["bearer_token"] = auth_token

    retry_status = DEFAULT_RETRY_REASONS | {
        requests.status_codes.codes.GATEWAY_TIMEOUT,
        requests.status_codes.codes.SERVICE_UNAVAILABLE,
    }

    client = WebAPIClient(
        api_url=api_url,
        retry_status=retry_status,
        **kwargs,
    )
    return client


def run(
    config: Dict[str, Any],
    policy,
    source_tree: Directory,
    nodes_data: MerkleNodeInfo,
    provenance: bool,
    progress_class: Type[Progress] = Progress,
) -> WebAPIClient:
    """Scan a given source code according to the policy given in input."""
    client = get_webapi_client(config)

    # always start with finding what is known. The other option will need this
    # information anyway. Fetching "known" status is efficicient and relatively
    # cheap. In addition is "context free"¹ and can fetch in any order. So we
    # start with this step in all cases.
    #
    # [1] the best answer for "known" does not changes depending of the status
    # of the files and directory around it. This is not free for "oring" for
    # example.
    with progress_class(
        step=Progress.Step.KNOWN_DISCOVERY,
        total=len(nodes_data),
        web_client=client,
    ) as progress:

        def callback(*args, **kwargs):
            progress.increment()

        policy.run(client, update_info=callback)
    if provenance:
        with progress_class(
            step=Progress.Step.PROVENANCE,
            total=len(nodes_data),
            web_client=client,
        ) as progress:
            add_provenance(
                source_tree, nodes_data, client, update_progress=progress.update
            )
    return client


COMMON_EXCLUDE_PATTERNS: List[bytes] = [
    b".bzr",
    b".coverage",
    b"*.egg-info",
    b".eggs",
    b".git",
    b".hg",
    b".mypy_cache",
    b"__pycache__",
    b".svn",
    b".tox",
]
COMMON_EXCLUDE_PATTERNS.extend([b"*/" + p for p in COMMON_EXCLUDE_PATTERNS])


def scan(
    config: Dict[str, Any],
    root_path: str,
    out_fmt: str,
    interactive: bool,
    provenance: bool,
    debug_http: bool,
    progress_class: Type[Progress],
):
    """Scan a source code project to discover files and directories already
    present in the archive"""
    exclude_patterns = config["scanner"]["exclude"]
    exclude_templates = config["scanner"]["exclude_templates"]
    disable_global_patterns = config["scanner"]["disable_global_patterns"]
    disable_vcs_patterns = config["scanner"]["disable_vcs_patterns"]

    converted_patterns = [pattern.encode() for pattern in exclude_patterns]

    if exclude_templates is not None:
        templates = get_ignore_patterns_templates()
        for template in exclude_templates:
            converted_patterns.extend(
                parse_ignore_patterns_template(templates[template])
            )

    if not disable_global_patterns:
        converted_patterns.extend(COMMON_EXCLUDE_PATTERNS)
    if not disable_vcs_patterns:
        vcs_ignore_patterns = get_vcs_ignore_patterns(Path(root_path))
        converted_patterns.extend(vcs_ignore_patterns)

    with progress_class(step=Progress.Step.DISK_SCAN) as progress:
        dir_update_info = progress.increment
        source_tree = model_of_dir(
            root_path.encode(),
            converted_patterns,
            update_info=dir_update_info,
        )

    nodes_data = MerkleNodeInfo()
    init_merkle_node_info(source_tree, nodes_data, provenance)

    policy = RandomDirSamplingPriority(
        source_tree,
        nodes_data,
    )
    web_client = run(
        config,
        policy,
        source_tree,
        nodes_data,
        provenance,
        progress_class=progress_class,
    )

    get_output_class(out_fmt)(
        root_path, nodes_data, source_tree, config, web_client
    ).show()

    config["debug_http"] = debug_http
    if interactive:
        get_output_class("interactive")(
            root_path, nodes_data, source_tree, config, web_client
        ).show()
