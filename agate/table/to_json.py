import json
from collections import OrderedDict
from decimal import Decimal


def to_json(self, path, key=None, newline=False, indent=None, encoding='utf-8', **kwargs):
    """
    Write this table to a JSON file or file-like object.

    :code:`kwargs` will be passed through to the JSON encoder.

    :param path:
        File path or file-like object to write to.
    :param key:
        If specified, JSON will be output as an hash instead of a list. May
        be either the name of a column from the this table containing
        unique values or a :class:`function` that takes a row and returns
        a unique value.
    :param newline:
        If `True`, output will be in the form of "newline-delimited JSON".
    :param indent:
        If specified, the number of spaces to indent the JSON for
        formatting.
    :param encoding:
        Character encoding used when ``path`` is a filepath. Defaults to
        ``'utf-8'``, matching :meth:`.Table.from_json` and the JSON
        specification's default encoding, so non-ASCII content writes
        correctly and round trips on every platform, including Windows where
        the platform default encoding cannot represent characters such as
        emoji. Pass :code:`None` to restore the historical behavior of using
        the platform's preferred encoding. This argument is ignored when
        ``path`` is a file-like object, which is assumed to already be opened
        with the desired encoding.
    """
    if key is not None and newline:
        raise ValueError('key and newline may not be specified together.')

    if newline and indent is not None:
        raise ValueError('newline and indent may not be specified together.')

    from agate.fileio import atomic_open

    key_is_row_function = hasattr(key, '__call__')

    json_kwargs = {
        'ensure_ascii': False,
        'indent': indent
    }

    # Pass remaining kwargs through to JSON encoder
    json_kwargs.update(kwargs)

    json_funcs = [c.jsonify for c in self._column_types]

    if hasattr(path, 'write'):
        _write_json(self, path, key, newline, key_is_row_function, json_kwargs, json_funcs)
    else:
        # atomic_open replaces the destination only after the full content has
        # been written and flushed, so a failed write never leaves a partial
        # file; any encoding error is re-raised as FileWriteError with the
        # target path and encoding named.
        with atomic_open(path, encoding=encoding) as f:
            _write_json(self, f, key, newline, key_is_row_function, json_kwargs, json_funcs)


def _write_json(self, f, key, newline, key_is_row_function, json_kwargs, json_funcs):
    def dump_json(data):
        json.dump(data, f, **json_kwargs)

        if newline:
            f.write('\n')

    # Keyed
    if key is not None:
        output = OrderedDict()

        for row in self._rows:
            if key_is_row_function:
                k = key(row)
            elif isinstance(row[key], Decimal):
                k = str(row[key].normalize())
            else:
                k = str(row[key])

            if k in output:
                raise ValueError('Value %s is not unique in the key column.' % str(k))

            values = tuple(json_funcs[i](d) for i, d in enumerate(row))
            output[k] = OrderedDict(zip(row.keys(), values))
        dump_json(output)
    # Newline-delimited
    elif newline:
        for row in self._rows:
            values = tuple(json_funcs[i](d) for i, d in enumerate(row))
            dump_json(OrderedDict(zip(row.keys(), values)))
    # Normal
    else:
        output = []

        for row in self._rows:
            values = tuple(json_funcs[i](d) for i, d in enumerate(row))
            output.append(OrderedDict(zip(row.keys(), values)))

        dump_json(output)
