import json
import os
from collections import OrderedDict
from io import StringIO


def to_json(self, path, nested=False, indent=None, encoding='utf-8', **kwargs):
    """
    Write :class:`TableSet` to either a set of JSON files for each table or
    a single nested JSON file.

    See :meth:`.Table.to_json` for additional details.

    :param path:
        Path to the directory to write the JSON file(s) to. If nested is
        `True`, this should be a file path or file-like object to write to.
    :param nested:
        If `True`, the output will be a single nested JSON file with each
        Table's key paired with a list of row objects. Otherwise, the output
        will be a set of files for each table. Defaults to `False`.
    :param indent:
        See :meth:`Table.to_json`.
    :param encoding:
        Character encoding used when writing to a filepath. Defaults to
        ``'utf-8'``; pass :code:`None` to use the platform's preferred
        encoding. Ignored when ``path`` is a file-like object.
    """
    from agate.fileio import atomic_open

    if not nested:
        if not os.path.exists(path):
            os.makedirs(path)

        for name, table in self.items():
            filepath = os.path.join(path, '%s.json' % name)

            table.to_json(filepath, indent=indent, encoding=encoding, **kwargs)
    else:
        tableset_dict = OrderedDict()

        for name, table in self.items():
            output = StringIO()
            table.to_json(output, **kwargs)
            tableset_dict[name] = json.loads(output.getvalue(), object_pairs_hook=OrderedDict)

        if hasattr(path, 'write'):
            _dump_nested(tableset_dict, path, indent, **kwargs)
        else:
            # atomic_open replaces the destination only after the full content
            # has been written and flushed, so a failed write never leaves a
            # partial file.
            with atomic_open(path, encoding=encoding) as f:
                _dump_nested(tableset_dict, f, indent, **kwargs)


def _dump_nested(tableset_dict, f, indent, **kwargs):
    json_kwargs = {'ensure_ascii': False, 'indent': indent}

    json_kwargs.update(kwargs)
    json.dump(tableset_dict, f, **json_kwargs)
