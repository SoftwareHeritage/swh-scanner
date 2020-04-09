import pytest

from swh.scanner.cli import extract_regex_objs
from swh.scanner.exceptions import InvalidDirectoryPath


def test_extract_regex_objs(temp_folder):
    root_path = temp_folder["root"]

    patterns = (str(temp_folder["subdir"]), "/none")
    sre_patterns = [reg_obj for reg_obj in extract_regex_objs(root_path, patterns)]
    assert len(sre_patterns) == 1

    patterns = (*patterns, "/tmp")
    with pytest.raises(InvalidDirectoryPath):
        sre_patterns = [reg_obj for reg_obj in extract_regex_objs(root_path, patterns)]
