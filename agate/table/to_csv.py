def to_csv(self, path, encoding='utf-8', **kwargs):
    """
    Write this table to a CSV. This method uses agate's builtin CSV writer,
    which supports unicode on both Python 2 and Python 3.

    ``kwargs`` will be passed through to the CSV writer.

    The ``lineterminator`` defaults to the newline character (LF, ``\\n``).

    :param path:
        Filepath or file-like object to write to.
    :param encoding:
        Character encoding used when ``path`` is a filepath. Defaults to
        ``'utf-8'`` so non-ASCII content writes correctly and round trips
        with :meth:`.Table.from_csv` (which also defaults to ``'utf-8'``) on
        every platform, including Windows where the platform default encoding
        cannot represent characters such as emoji. Pass :code:`None` to
        restore the historical behavior of using the platform's preferred
        encoding. This argument is ignored when ``path`` is a file-like
        object, which is assumed to already be opened with the desired
        encoding.
    """
    from agate.fileio import atomic_open

    if 'lineterminator' not in kwargs:
        kwargs['lineterminator'] = '\n'

    if hasattr(path, 'write'):
        _write_csv(self, path, **kwargs)
    else:
        # atomic_open replaces the destination only after the full content has
        # been written and flushed, so a failed write never leaves a partial
        # file; any encoding error is re-raised as FileWriteError with the
        # target path and encoding named.
        with atomic_open(path, encoding=encoding) as f:
            _write_csv(self, f, **kwargs)


def _write_csv(self, f, **kwargs):
    from agate import csv

    writer = csv.writer(f, **kwargs)
    writer.writerow(self._column_names)

    csv_funcs = [c.csvify for c in self._column_types]

    for row in self._rows:
        writer.writerow(tuple(csv_funcs[i](d) for i, d in enumerate(row)))
