#!/usr/bin/env python3
# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Set

import click

SEED_OPTIONS = ["-s 10", "-s 20", "-s 30"]


def get_scenario_cmd(algo, kb_url, kb_label, origin_info, extracted_repo_path):
    return [
        "swh",
        "scanner",
        "benchmark",
        "--algo",
        algo,
        "--api-url",
        kb_url,
        "--backend-name",
        kb_label,
        "--origin",
        origin_info["origin"],
        "--commit",
        origin_info["commit"],
        "--exclude",
        str(extracted_repo_path) + "/.git",
        str(extracted_repo_path),
    ]


def run_experiments(
    repo_path: str, temp_path: str, kb_state_file: str, algos: Set[str]
):
    """This function create a process for each experiment; one experiment is composed
    by: the repository we want to scan, the algorithms we need to test and different
    known-backends mapped in a "kb-state" file (given in input)
    """
    dirpath, dnames, _ = next(os.walk(temp_path))
    extracted_repo_path = Path(dirpath).joinpath(dnames[0])

    # get all the backends identifier and api URLs
    backends = {}
    with open(kb_state_file, "r") as kb_state_f:
        for kb in kb_state_f.readlines():
            if kb.startswith("#"):
                continue
            elems = kb.split(" ")
            backends[elems[0]] = elems[1]

    # get repository origin info from the "base_directory"
    info_path = repo_path[:-7] + "info.json"
    with open(info_path, "r") as json_file:
        origin_info = json.load(json_file)

    scenario_cmds = []

    for algo in algos:
        for kb_label, kb_url in backends.items():
            if algo == "random":
                for seed_opt in SEED_OPTIONS:
                    random_cmd = get_scenario_cmd(
                        algo, kb_url, kb_label, origin_info, str(extracted_repo_path)
                    )
                    scenario_cmds.append(random_cmd + [seed_opt])
            else:
                scenario_cmds.append(
                    get_scenario_cmd(
                        algo, kb_url, kb_label, origin_info, str(extracted_repo_path)
                    )
                )

    processes = [
        subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
        for cmd in scenario_cmds
    ]

    for proc in processes:
        proc.wait()


@click.command(
    help="""Run multiple benchmark from an input repository. The repository
            will be unpacked in the provided temporary path and tested with
            the input algorithms."""
)
@click.argument("repo_path", type=click.Path(exists=True), required=True)
@click.argument("temp_path", type=click.Path(exists=True), required=True)
@click.argument("kb_state", type=click.Path(exists=True), required=True)
@click.option(
    "-a",
    "--algo",
    "algos",
    multiple=True,
    required=True,
    type=click.Choice(
        ["stopngo", "file_priority", "directory_priority", "random", "algo_min"],
        case_sensitive=False,
    ),
    metavar="ALGORITHM_NAME",
    help="The algorithm name for the benchmark.",
)
def main(repo_path, temp_path, kb_state, algos):
    logging.basicConfig(
        filename="experiments.log",
        format="%(asctime)s %(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
    )
    try:
        repo_id = Path(repo_path).parts[-1].split(".")[0]
        with TemporaryDirectory(prefix=repo_id + "_", dir=temp_path) as tmp_dir:
            subprocess.run(
                ["tar", "xf", repo_path, "-C", tmp_dir, "--strip-components=1"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=sys.stderr,
            )
            run_experiments(repo_path, temp_path, kb_state, set(algos))
    except Exception as e:
        logging.exception(e)
    except IOError as ioerror:
        logging.exception(ioerror)


if __name__ == "__main__":
    main()
