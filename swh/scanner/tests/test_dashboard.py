# Copyright (C) 2020-2024 The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from bs4 import BeautifulSoup
import pytest

from swh.scanner.dashboard.dashboard import create_app

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
def summary():
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
def app(test_sample_folder, source_tree, nodes_data, summary):
    yield create_app(
        config={"debug_http": False, "no_web_browse": True},
        root_path=str(test_sample_folder),
        source_tree=source_tree,
        nodes_data=nodes_data,
        summary=summary,
    )


@pytest.fixture
def client(app):
    app.config.update({"TESTING": True})
    return app.test_client()


def test_index(app, client, test_sample_folder):
    """Test Dashboard index route"""
    res = client.get("/")
    assert res.status_code == 200

    soup = BeautifulSoup(res.text, "html.parser")

    scan_path = soup.find(id="path")
    assert scan_path.strong.text == str(test_sample_folder)

    sections = soup.article.find_all("section")
    expected = ["50%", "0%", "50%"]
    assert len(sections) == 3
    for i, section in enumerate(sections):
        assert expected[i] in section.text


def test_results(app, client, test_sample_folder):
    """Test /results route"""
    res = client.get("/results")
    assert res.status_code == 200

    soup = BeautifulSoup(res.text, "html.parser")

    scan_path = soup.find(id="path")
    assert scan_path.strong.text == str(test_sample_folder)

    details = soup.find(id="tree").find_all("details")
    for detail in details:
        for attr in EXPECTED_DATA_ATTRIBUTES:
            assert attr in detail.attrs.keys()


def test_api_html_tree(app, client, test_sample_folder):
    """Test /api/v1/html-tree/<path:directory_path> route"""
    res = client.get("/api/v1/html-tree/foo")
    assert res.status_code == 200

    expected_json_keys = ["path", "html"]
    for key in res.json.keys():
        assert key in expected_json_keys

    soup = BeautifulSoup(res.json["html"], "html.parser")
    # parent tag is an unordered list
    assert soup.ul
    # with details elements
    details = soup.ul.find_all("details")
    for detail in details:
        for attr in EXPECTED_DATA_ATTRIBUTES:
            assert attr in detail.attrs.keys()
