# Copyright (C) 2020-2021 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from functools import partial
from typing import Any, Callable, Dict, Iterable, List, Optional

from swh.model.cli import model_of_dir
from swh.model.from_disk import Directory
from swh.web.client.client import WebAPIClient

from .data import (
    MerkleNodeInfo,
    add_origin,
    get_ignore_patterns_templates,
    get_vcs_ignore_patterns,
    init_merkle_node_info,
    parse_ignore_patterns_template,
)
from .output import get_output_class
from .policy import RandomDirSamplingPriority


def run(
    config: Dict[str, Any],
    policy,
    source_tree: Directory,
    nodes_data: MerkleNodeInfo,
    extra_info: set,
) -> None:
    """Scan a given source code according to the policy given in input."""
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

    client = WebAPIClient(api_url=api_url, **kwargs)
    for info in extra_info:
        if info == "known":
            policy.run(client)
        elif info == "origin":
            add_origin(source_tree, nodes_data, client)
        else:
            raise Exception(f"The information '{info}' cannot be retrieved")


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
    exclude_templates: Iterable[str],
    exclude_patterns: Iterable[str],
    out_fmt: str,
    interactive: bool,
    extra_info: set,
    disable_global_patterns: bool,
    disable_vcs_patterns: bool,
    progress_callback: Optional[Callable[[Any], None]] = None,
):
    """Scan a source code project to discover files and directories already
    present in the archive"""

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
        vcs_ignore_patterns = get_vcs_ignore_patterns()
        converted_patterns.extend(vcs_ignore_patterns)

    dir_update_info = None
    if progress_callback is not None:
        dir_update_info = partial(progress_callback, "Directory.from_disk")

    source_tree = model_of_dir(
        root_path.encode(),
        converted_patterns,
        update_info=dir_update_info,
    )

    nodes_data = MerkleNodeInfo()
    extra_info.add("known")
    init_merkle_node_info(source_tree, nodes_data, extra_info)
    discovery_update_info = None
    if progress_callback is not None:
        discovery_update_info = partial(progress_callback, "Policy.discovery")

    policy = RandomDirSamplingPriority(
        source_tree,
        nodes_data,
        update_info=discovery_update_info,
    )

    run(config, policy, source_tree, nodes_data, extra_info)

    if interactive:
        out_fmt = "interactive"

    get_output_class(out_fmt)(root_path, nodes_data, source_tree).show()
