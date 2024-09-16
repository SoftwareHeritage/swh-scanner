================================
Software Heritage - Code Scanner
================================

Source code scanner to analyze code bases and compare them with source code
artifacts archived by Software Heritage.

Getting Started
===============

Installation
------------

To install the Software Heritage scanner, run::

  pip install swh-scanner

Registering to the Software Heritage Archive
--------------------------------------------

To efficiently query the Software Heritage Archive, you need to create an
account. This is not strictly necessary, but the rate limit imposed on anonymous
users will likely result in very slow operation.

First, visit https://archive.softwareheritage.org/oidc/login/ and create
a new user by clicking on ``Register``.

Then use this newly created account to authenticate within the Scanner.::

  swh scanner login

Configuring your scan
---------------------

The scanner will guide you through your initial configuration through the
``setup`` command::

  swh scanner setup


Running a Scan
--------------

To scan your local file in ``PROJECT_PATH``, use::

  swh scanner scan PROJECT_PATH

This will find your local files, query the archive, and provide you with a
graphical user interface to browse the result.

Note that the ``scan`` command has a ``--provenance`` flag that retrieves
information about where the files known to the archive might come from. This
option is experimental and you need to get in touch with the Software Heritage
team to be granted permission to the necessary APIs. Alternatively, there is a
button in the dashboard that will query the provenance for a given selected
file or directory. This is also experimental and gated to privileged users.

Further Configuration
---------------------

The scanner will add up configuration options from three places, in order of precedence:

- The command line
- The project config file
- The global config file

You can view the command line options by invoking ``swh scanner scan --help``.

The scanner will look for a ``swh.scanner.project.yml`` file inside the directory
being scanned, or at the path given to ``--project-config-file``.

The global configuration resides in the
``swh > scanner`` section of the shared `YAML <https://yaml.org/>`_ configuration
file used by all Software Heritage tools, located by default at
``~/.config/swh/global.yml``.

The configuration file location is subject to the `XDG Base Directory
<https://wiki.archlinux.org/index.php/XDG_Base_Directory>`_ specification as
well as explicitly overridden on the `command line
<https://docs.softwareheritage.org/devel/swh-scanner/cli.html>`_ via the
``-C/--config-file`` flag.

The following sub-sections and fields can be used within the ``swh > scanner``
stanza:

- ``disable_global_patterns`` (default: ``false``): whether to disable the
  global exclusion patterns, which refer to very common patterns of files to
  exclude from the scan. Only use this if you're finding that some files are
  being ignored that you would want to scan, though very unlikely.
- ``disable_vcs_patterns`` (default: ``false``): whether to stop using the
  ignore mechanisms from version control systems (.gitignore, .hgignore,
  .svnignore). Note that this ignore mechanism only works in the first place
  if the VCS is available in your PATH (Git, Mercurial or SVN).
- ``exclude``: (default: ``[]``): a list of glob patterns of paths to exclude
  from the scan, to use on top of all other exclusion patterns.
- ``exclude_templates``: (default: ``[]``): a list of names of exclusion
  templates (as listed in the scanner's help) to use on top of all other
  exclusion patterns. This is useful if you want to exclude all common Python
  cache files for example.

Here is an example:

.. code:: yaml

    scanner:
      disable_global_patterns: false
      disable_vcs_patterns: false
      exclude: ["ignored*", "someotherpattern"]
      exclude_templates: ["Python", "Go", "Rust", "Node"]
