# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

"""
The purpose of this module is to display and to interact with the result of the
scanner contained in the model.

The `sunburst` function generates a navigable sunburst chart from the
directories information retrieved from the model. The chart displays for
each directory the total number of files and the percentage of file known.

The size of the directory is defined by the total number of contents whereas
the color gradient is generated relying on the percentage of contents known.
"""

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np  # type: ignore
import pandas as pd  # type: ignore
import plotly.graph_objects as go
from plotly.offline import offline


def build_hierarchical_df(
    dirs_dataframe: pd.DataFrame,
    levels: List[str],
    metrics_columns: List[str],
    root_name: str,
) -> pd.DataFrame:
    """
        Build a hierarchy of levels for Sunburst or Treemap charts.

        For each directory the new dataframe will have the following
        information:

        id: the directory name
        parent: the parent directory of id
        contents: the total number of contents of the directory id and
        the relative subdirectories
        known: the percentage of contents known relative to computed
        'contents'

        Example:
        Given the following dataframe:

        .. code-block:: none

            lev0     lev1                contents  known
             ''       ''                 20        2     //root
            kernel   kernel/subdirker    5         0
            telnet   telnet/subdirtel    10        4

        The output hierarchical dataframe will be like the following:

        .. code-block:: none

              id                parent    contents  known
                                          20        10.00
           kernel/subdirker     kernel    5         0.00
           telnet/subdirtel     telnet    10        40.00
                                total     20        10.00
           kernel               total     5         0.00
           telnet               total     10        40.00
           total                          35        17.14

        To create the hierarchical dataframe we need to iterate through
        the dataframe given in input relying on the number of levels.

        Based on the previous example we have to do two iterations:

        iteration 1
        The generated dataframe 'df_tree' will be:

        .. code-block:: none

            id                parent   contents  known
                                       20        10.0
            kernel/subdirker  kernel   5         0.0
            telnet/subdirtel  telnet   10        40.0

        iteration 2
        The generated dataframe 'df_tree' will be:

        .. code-block:: none

            id       parent   contents  known
                     total    20        10.0
            kernel   total    5         0.0
            telnet   total    10        40.0

        Note that since we have reached the last level, the parent given
        to the directory id is the directory root.

        The 'total' row il computed by adding the number of contents of the
        dataframe given in input and the average of the contents known on
        the total number of contents.

    """

    def compute_known_percentage(contents: pd.Series, known: pd.Series) -> pd.Series:
        """This function compute the percentage of known contents and generate
           the new known column with the percentage values.

           It also assures that if there is no contents inside a directory
           the percentage is zero

        """
        known_values = []
        for idx, content_val in enumerate(contents):
            if content_val == 0:
                known_values.append(0)
            else:
                percentage = known[idx] / contents[idx] * 100
                known_values.append(percentage)

        return pd.Series(np.array(known_values))

    complete_df = pd.DataFrame(columns=["id", "parent", "contents", "known"])
    # revert the level order to start from the deepest
    levels = [level for level in reversed(levels)]
    contents_col = metrics_columns[0]
    known_col = metrics_columns[1]

    df_tree_list = []
    for i, level in enumerate(levels):
        df_tree = pd.DataFrame(columns=["id", "parent", "contents", "known"])
        dfg = dirs_dataframe.groupby(levels[i:]).sum()
        dfg = dfg.reset_index()
        df_tree["id"] = dfg[level].copy()
        if i < len(levels) - 1:
            # copy the parent directories (one level above)
            df_tree["parent"] = dfg[levels[i + 1]].copy()
        else:
            # last level reached
            df_tree["parent"] = root_name

        # copy the contents column
        df_tree["contents"] = dfg[contents_col]
        # compute the percentage relative to the contents
        df_tree["known"] = compute_known_percentage(dfg[contents_col], dfg[known_col])

        df_tree_list.append(df_tree)

    complete_df = complete_df.append(df_tree_list, ignore_index=True)

    # create the main parent
    total_contents = dirs_dataframe[contents_col].sum()
    total_known = dirs_dataframe[known_col].sum()
    total_avg = total_known / total_contents * 100

    total = pd.Series(
        dict(id=root_name, parent="", contents=total_contents, known=total_avg)
    )

    complete_df = complete_df.append(total, ignore_index=True)

    return complete_df


def compute_max_depth(dirs_path: List[Path], root: Path) -> int:
    """Compute the maximum depth level of the given directory paths.

       Example: for `var/log/kernel/` the depth level is 3

    """
    max_depth = 0
    for dir_path in dirs_path:
        if dir_path == root:
            continue

        dir_depth = len(dir_path.parts)
        if dir_depth > max_depth:
            max_depth = dir_depth

    return max_depth


def generate_df_from_dirs(
    dirs: Dict[Path, Tuple[int, int]], columns: List[str], root: Path, max_depth: int,
) -> pd.DataFrame:
    """Generate a dataframe from the directories given in input.

    Example:
    given the following directories as input

    .. code-block:: python

        dirs = {
            '/var/log/': (23, 2),
            '/var/log/kernel': (5, 0),
            '/var/log/telnet': (10, 3)
        }

    The generated dataframe will be:

    .. code-block:: none

        lev0   lev1       lev2             contents  known
        'var'  'var/log'   ''              23        2
        'var'  'var/log' 'var/log/kernel'  5         0
        'var'  'var/log' 'var/log/telnet'  10        3

    """

    def get_parents(path: Path):
        parts = path.parts[1:] if path.parts[0] == "/" else path.parts

        for i in range(1, len(parts) + 1):
            yield "/".join(parts[0:i])

    def get_dirs_array():
        for dir_path, contents_info in dirs.items():
            empty_lvl = max_depth - len(dir_path.parts)

            if dir_path == root:
                # ignore the root but store contents information
                yield [""] * (max_depth) + list(contents_info)
            else:
                yield list(get_parents(dir_path)) + [""] * empty_lvl + list(
                    contents_info
                )

    df = pd.DataFrame(
        np.array([dir_array for dir_array in get_dirs_array()]), columns=columns
    )

    df["contents"] = pd.to_numeric(df["contents"])
    df["known"] = pd.to_numeric(df["known"])

    return df


def generate_sunburst(
    directories: Dict[Path, Tuple[int, int]], root: Path
) -> go.Sunburst:
    """Generate a sunburst chart from the directories given in input.

    """
    max_depth = compute_max_depth(list(directories.keys()), root)
    metrics_columns = ["contents", "known"]
    levels_columns = ["lev" + str(i) for i in range(max_depth)]

    df_columns = levels_columns + metrics_columns
    dirs_df = generate_df_from_dirs(directories, df_columns, root, max_depth)

    hierarchical_df = build_hierarchical_df(
        dirs_df, levels_columns, metrics_columns, str(root)
    )

    sunburst = go.Sunburst(
        labels=hierarchical_df["id"],
        parents=hierarchical_df["parent"],
        values=hierarchical_df["contents"],
        branchvalues="total",
        marker=dict(
            colors=hierarchical_df["known"],
            colorscale="matter",
            cmid=50,
            showscale=True,
        ),
        hovertemplate="""<b>%{label}</b>
            <br>Files: %{value}
            <br>Known: <b>%{color:.2f}%</b>""",
        name="",
    )

    return sunburst


def offline_plot(graph_object: go):
    """Plot a graph object to an html file
    """
    fig = go.Figure()
    fig.add_trace(graph_object)
    offline.plot(fig, filename="chart.html")
