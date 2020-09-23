#!/usr/bin/env python3
# Copyright (C) 2019-2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from io import open
from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()


def parse_requirements(name=None):
    if name:
        reqf = "requirements-%s.txt" % name
    else:
        reqf = "requirements.txt"

    requirements = []
    if not path.exists(reqf):
        return requirements

    with open(reqf) as f:
        for line in f.readlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            requirements.append(line)
    return requirements


# Edit this part to match your module.
# Full sample:
#   https://forge.softwareheritage.org/diffusion/DCORE/browse/master/setup.py
setup(
    name="swh.scanner",
    description="Software Heritage code scanner",
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires=">=3.7",
    author="Software Heritage developers",
    author_email="swh-devel@inria.fr",
    url="https://forge.softwareheritage.org/diffusion/DTSCN/",
    packages=find_packages(),  # packages's modules
    install_requires=parse_requirements() + parse_requirements("swh"),
    tests_require=parse_requirements("test"),
    setup_requires=["setuptools-scm"],
    use_scm_version=True,
    extras_require={"testing": parse_requirements("test")},
    include_package_data=True,
    entry_points="""
        [swh.cli.subcommands]
        scanner=swh.scanner.cli
    """,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
    ],
    project_urls={
        "Bug Reports": "https://forge.softwareheritage.org/maniphest",
        "Funding": "https://www.softwareheritage.org/donate",
        "Source": "https://forge.softwareheritage.org/source/swh-scanner",
        "Documentation": "https://docs.softwareheritage.org/devel/swh-scanner/",
    },
)
