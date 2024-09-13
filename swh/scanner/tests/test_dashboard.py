# Copyright (C) 2020-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from pathlib import Path
from typing import Dict, Iterator, Set, Union

from bs4 import BeautifulSoup, Tag
from flask.app import App
from flask.testing import FlaskClient
import pytest

from swh.model.from_disk import Directory
from swh.scanner.dashboard.dashboard import create_app
from swh.scanner.data import MerkleNodeInfo

EXPECTED_DATA_ATTRIBUTES = [
    "id",
    "class",
    "data-name",
    "data-swhid",
    "data-type",
    "data-fpath",
    "data-rpath",
    "data-known",
]


@pytest.fixture
def summary() -> Dict[str, Union[int, Set]]:
    return {
        "total_files": 10,
        "known_files": 5,
        "known_files_percent": 50,
        "total_directories": 2,
        "full_known_directories": set("fake_directory"),
        "full_known_directories_percent": 50,
        "partially_known_directories": set(),
        "partially_known_directories_percent": 0,
    }


@pytest.fixture
def app(
    test_sample_folder: Path,
    source_tree: Directory,
    nodes_data: MerkleNodeInfo,
    summary: Dict,
) -> Iterator[App]:
    yield create_app(
        config={"debug_http": False, "no_web_browse": True},
        root_path=str(test_sample_folder),
        source_tree=source_tree,
        nodes_data=nodes_data,
        summary=summary,
        web_client=None,
    )


@pytest.fixture
def client(app: App) -> FlaskClient:
    app.config.update({"TESTING": True})
    assert hasattr(app, "test_client")  # please mypy
    return app.test_client()


def test_index(app: App, client: FlaskClient, test_sample_folder: Path):
    """Test Dashboard index route"""
    res = client.get("/")
    assert res.status_code == 200

    soup = BeautifulSoup(res.text, "html.parser")

    scan_path = soup.find(id="path")
    assert isinstance(scan_path, Tag)
    assert isinstance(scan_path.strong, Tag)
    assert scan_path.strong.text == str(test_sample_folder)

    assert isinstance(soup.article, Tag)
    sections = soup.article.find_all("section")
    expected = ["50%", "0%", "50%"]
    assert len(sections) == 3
    for i, section in enumerate(sections):
        assert expected[i] in section.text


def test_results(app: App, client: FlaskClient, test_sample_folder: Path):
    """Test /results route"""
    res = client.get("/results")
    assert res.status_code == 200

    soup = BeautifulSoup(res.text, "html.parser")

    scan_path = soup.find(id="path")
    assert isinstance(scan_path, Tag)
    assert isinstance(scan_path.strong, Tag)
    assert scan_path.strong.text == str(test_sample_folder)

    tree = soup.find(id="tree")
    assert isinstance(tree, Tag)
    details = tree.find_all("details")
    for detail in details:
        for attr in EXPECTED_DATA_ATTRIBUTES:
            assert attr in detail.attrs.keys()


def test_api_html_tree(app: App, client: FlaskClient, test_sample_folder: Path):
    """Test /api/v1/html-tree/<path:directory_path> route"""
    res = client.get("/api/v1/html-tree/foo")
    assert res.status_code == 200

    expected_json_keys = ["path", "html"]
    assert res.json
    for key in res.json.keys():
        assert key in expected_json_keys

    soup = BeautifulSoup(res.json["html"], "html.parser")
    # parent tag is an unordered list
    assert soup.ul
    assert isinstance(soup.ul, Tag)
    # with details elements
    details = soup.ul.find_all("details")
    for detail in details:
        for attr in EXPECTED_DATA_ATTRIBUTES:
            assert attr in detail.attrs.keys()
