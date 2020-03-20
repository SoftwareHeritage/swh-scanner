# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

correct_api_response = {
        "swh:1:dir:17d207da3804cc60a77cba58e76c3b2f767cb112":
        {"known": False},
        "swh:1:dir:01fa282bb80be5907505d44b4692d3fa40fad140":
        {"known": True},
        "swh:1:dir:4b825dc642cb6eb9a060e54bf8d69288fbee4904":
        {"known": True}}

# present pids inside /data/sample-folder
present_pids = [
        "swh:1:cnt:7c4c57ba9ff496ad179b8f65b1d286edbda34c9a",  # quotes.md
        "swh:1:cnt:68769579c3eaadbe555379b9c3538e6628bae1eb",  # some-binary
        "swh:1:dir:9619a28687b2462efbb5be816bc1185b95753d93"  # barfoo2/
        ]