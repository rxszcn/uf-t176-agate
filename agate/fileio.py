"""
Helpers for writing files to disk with an explicit character encoding and
atomic replacement semantics.

The writers in :mod:`agate.table` and :mod:`agate.tableset` funnel every
filepath-based write through :func:`atomic_open` so that:

* the character encoding is always explicit (it never silently depends on the
  platform's preferred encoding, which makes non-ASCII content fail or round
  trip incorrectly on Windows);
* a file is only replaced after the full content has been written and flushed,
  so a failed write never leaves a truncated, half-written file behind;
* filesystem and codec errors carry the target path and encoding, making the
  failure locatable instead of surfacing as a bare :class:`UnicodeEncodeError`.
  Domain errors raised while serializing keep their original exception type.
"""

import os
import tempfile
from contextlib import contextmanager


class FileWriteError(OSError):
    """
    Raised when a table cannot be written to a file.

    The original exception is preserved as the :attr:`__cause__` of this
    error (visible via a ``raise ... from`` chain), while the message names
    the target path and encoding so the failure can be located directly.
    """
    pass


@contextmanager
def atomic_open(path, encoding='utf-8'):
    """
    Open ``path`` for writing through a temporary file in the same directory.

    The yielded text stream is opened with the explicit ``encoding``. On
    clean completion the temporary file is flushed and atomically moved onto
    ``path`` via :func:`os.replace`. If an :class:`OSError` or
    :class:`UnicodeError` is raised (for example a
    :class:`UnicodeEncodeError` or a filesystem error), the temporary file is
    removed, any pre-existing file at ``path`` is left untouched and the error
    is re-raised as a :class:`FileWriteError` referencing ``path`` and
    ``encoding``. Any other exception (for example a domain-level
    :class:`ValueError`) is not wrapped: it propagates unchanged after the
    temporary file has been cleaned up.

    :param path:
        Destination filepath. Parent directories are created as needed.
    :param encoding:
        Character encoding passed to :func:`open`. Defaults to ``'utf-8'``.
        Pass :code:`None` to use the platform's preferred encoding (the
        historical implicit behavior).
    """
    directory = os.path.dirname(path) or os.curdir

    try:
        if not os.path.exists(directory):
            os.makedirs(directory)

        # The temporary file must live in the same directory so that
        # os.replace is an atomic rename on the same filesystem (including
        # Windows). delete=False lets us control the rename/cleanup ourselves.
        fd, tmp_path = tempfile.mkstemp(suffix='.tmp', prefix='.agate-', dir=directory)
        os.close(fd)

        try:
            f = open(tmp_path, 'w', encoding=encoding)

            try:
                yield f
                f.flush()
                os.fsync(f.fileno())
            finally:
                f.close()

            os.replace(tmp_path, path)
            tmp_path = None
        finally:
            # Always clean up the temporary file, whatever went wrong, so a
            # failed write leaves neither a truncated destination nor debris.
            if tmp_path is not None and os.path.exists(tmp_path):
                os.remove(tmp_path)
    except (OSError, UnicodeError) as e:
        # Only wrap errors that originate from the filesystem or the codec
        # layer. Domain errors raised while serializing (e.g. a non-unique
        # JSON key) propagate with their original type, as they did before.
        raise FileWriteError(
            'Failed to write file "%s" with encoding %s: %s: %s'
            % (path, repr(encoding), type(e).__name__, e)
        ) from e
