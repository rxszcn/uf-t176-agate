============
Save a table
============

To a CSV
========

.. code-block:: python

    table.to_csv('filename.csv')

By default the CSV is written as UTF-8, so non-ASCII text is preserved and
round trips with :meth:`.Table.from_csv` on every platform. Pass an explicit
``encoding`` to use another codec, or ``encoding=None`` to fall back to the
platform's preferred encoding:

.. code-block:: python

    table.to_csv('filename.csv', encoding='gbk')

To JSON
=======

.. code-block:: python

    table.to_json('filename.json')

As with CSV, JSON files are written as UTF-8 by default and accept an
``encoding`` argument for another codec.

To newline-delimited JSON
=========================

.. code-block:: python

    table.to_json('filename.json', newline=True)

To a SQL database
=================

Use the `agate-sql <https://agate-sql.readthedocs.org/>`_ extension.

.. code-block:: python

    import agatesql

    table.to_sql('postgresql:///database', 'output_table')
