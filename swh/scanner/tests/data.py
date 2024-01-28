# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information
from swh.model.swhids import CoreSWHID

correct_known_web_api_response = {
    "swh:1:dir:17d207da3804cc60a77cba58e76c3b2f767cb112": {"known": False},
    "swh:1:dir:01fa282bb80be5907505d44b4692d3fa40fad140": {"known": True},
    "swh:1:dir:4b825dc642cb6eb9a060e54bf8d69288fbee4904": {"known": True},
}

correct_known_client_api_response = {
    CoreSWHID.from_string(k): v for (k, v) in correct_known_web_api_response.items()
}


sample_A_folder_root_swhid = "swh:1:dir:0a7b61ef5780b03aa274d11069564980246445ce"
sample_A_release_swhid = "swh:1:rel:0b3a2a741d10607ab16ef75809564980246445ce"
sample_A_revision_swhid = "swh:1:rev:10607ab16ef75809560b3a2a741d4980246445ce"
sample_A_origin = "https://bitbucket.org/chubbymaggie/bindead.git"

sample_B_content_swhid = "swh:1:cnt:68769579c3eaadbe555379b9c3538e6628bae1eb"
sample_B_revision_swhid = "swh:1:rev:10607ab1741d46ef75809560b3a2a980246445ce"
sample_B_origin = "https://github.com/babar/celeste.git"

fake_origin = {
    sample_A_folder_root_swhid: sample_A_origin,
    sample_A_release_swhid: sample_A_origin,
    sample_A_revision_swhid: sample_A_origin,
    sample_B_content_swhid: sample_B_origin,
    sample_B_revision_swhid: sample_B_origin,
}

fake_release = {
    sample_A_folder_root_swhid: sample_A_release_swhid,
}

fake_revision = {
    sample_A_folder_root_swhid: sample_A_revision_swhid,
    sample_A_release_swhid: sample_A_revision_swhid,
    sample_B_content_swhid: sample_B_revision_swhid,
}

present_swhids = [
    "swh:1:cnt:7c4c57ba9ff496ad179b8f65b1d286edbda34c9a",  # quotes.md
    "swh:1:cnt:68769579c3eaadbe555379b9c3538e6628bae1eb",  # some-binary
    "swh:1:dir:9619a28687b2462efbb5be816bc1185b95753d93",  # barfoo2/
    "swh:1:dir:07d4d9ec5c406632d203dbd4631e7863612a0326",  # toexclude/
]

# these SWHIDs are considered known by the fake backend (scanner.test.flask_api)
unknown_swhids = [
    "swh:1:dir:fe8cd7076bef324eb8865f818ef08617879022ce",  # root sample-folder-policy
    "swh:1:dir:0a7b61ef5780b03aa274d11069564980246445ce",  # root sample-folder
    "swh:1:cnt:5f1cfce26640056bed3710cfaf3062a6a326a119",  # toexclude/example.txt
    "swh:1:dir:07d4d9ec5c406632d203dbd4631e7863612a0326",  # toexclude/
]

to_exclude_swhid = "swh:1:dir:07d4d9ec5c406632d203dbd4631e7863612a0326"
