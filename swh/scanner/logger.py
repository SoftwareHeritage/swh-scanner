# Copyright (C) 2020  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import logging


logger = None


def init(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func
    return decorate


def setup_logger(verbose: bool) -> None:
    global logger
    console = logging.FileHandler('scan.log')
    console.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s: %(message)s')
    console.setFormatter(formatter)

    logger = logging.getLogger('debug')
    logger.addHandler(console)
    if not verbose:
        logger.propagate = False


@init(count=0)
def log_queries(n: int) -> None:
    if logger is not None:
        log_queries.count += n


def log_counters() -> None:
    if logger is not None:
        logger.info('number of queries: %s' % log_queries.count)


def error(*args) -> None:
    if logger is not None:
        logger.error(args)


def warning(*args) -> None:
    if logger is not None:
        logger.warning(args)


def info(*args) -> None:
    if logger is not None:
        logger.info(args)


def debug(*args):
    if logger is not None:
        logger.debug(args)
