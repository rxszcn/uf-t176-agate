import os


def to_csv(self, dir_path, encoding='utf-8', **kwargs):
    """
    Write each table in this set to a separate CSV in a given
    directory.

    See :meth:`.Table.to_csv` for additional details.

    :param dir_path:
        Path to the directory to write the CSV files to.
    :param encoding:
        Character encoding of the written files. See
        :meth:`.Table.to_csv`. Defaults to ``'utf-8'``; pass :code:`None` to
        use the platform's preferred encoding.
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    for name, table in self.items():
        path = os.path.join(dir_path, '%s.csv' % name)

        table.to_csv(path, encoding=encoding, **kwargs)
