Software Heritage - Code Scanner
================================

Source code scanner using the
`Software Heritage <https://www.softwareheritage.org/>`_
`archive <https://archive.softwareheritage.org/>`_
as knowledge base.


Sample usage
------------

.. code-block:: shell

   $ swh scanner scan --help

   Usage: swh scanner scan [OPTIONS] PATH

   Scan a source code project to discover files and directories already
   present in the archive

   Options:
     -u, --api-url API_URL     url for the api request  [default:
			       https://archive.softwareheritage.org/api/1]
     -f, --format [text|json]  select the output format
     -h, --help                Show this message and exit.
