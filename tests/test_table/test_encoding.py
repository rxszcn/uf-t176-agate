"""
Round-trip and explicit-encoding tests for the CSV and JSON writers/readers.

These tests pin down the contract that non-ASCII content survives a
write/read round trip on every platform (including Windows, whose preferred
encoding may be cp936 or another locale-specific codec), that the encoding
parameter is honored at both the CSV and JSON entry points, that special
values keep their exact serialized form, and that a failed write surfaces a
locatable error without leaving a truncated file behind.
"""

import json
import locale
import os
import shutil
import unittest
from collections import OrderedDict
from decimal import Decimal

from agate import Table, TableSet
from agate.data_types import Boolean, Number, Text
from agate.fileio import FileWriteError
from agate.testcase import AgateTestCase

# Codecs that every CPython build ships. The non-ASCII sample text for each
# codec only contains characters that codec can encode, so a failure can be
# attributed to the write/read path rather than to unsupported test data.
ENCODINGS = (
    ('utf-8', '中文数据 👍'),
    ('utf-8-sig', '中文数据'),
    ('gbk', '中文数据'),
    ('utf-16', '中文数据 👍'),
)


def make_table(text_value):
    # Nulls, a quoted embedded newline, embedded quotes and commas, plus
    # non-ASCII text and full-precision decimals exercise every special
    # serialized value form at once.
    rows = (
        (Decimal('1.50'), 'a,b', True, None),
        (Decimal('2'), 'line1\nline2', False, '引号"quote"'),
        (None, text_value, None, None),
    )
    column_names = ['number', 'text', 'boolean', 'note']
    column_types = [Number(), Text(), Boolean(), Text()]

    return Table(rows, column_names, column_types)


class EncodingAssertionsMixin:
    def assertRoundTrips(self, table, reloaded):
        self.assertColumnNames(reloaded, table.column_names)
        self.assertColumnTypes(reloaded, [Number, Text, Boolean, Text])
        self.assertEqual(len(reloaded.rows), len(table.rows))

        for original, reloaded_row in zip(table.rows, reloaded.rows):
            # Compare value by value so a single mismatched cell is reported
            # precisely instead of as an opaque row diff.
            self.assertEqual(len(reloaded_row), len(original))

            for i, (a, b) in enumerate(zip(original, reloaded_row)):
                if isinstance(a, Decimal):
                    # Decimal must survive the full round trip digit-for-digit.
                    self.assertIsInstance(b, Decimal)
                self.assertEqual(a, b, 'value mismatch at column %s: %r != %r' % (
                    table.column_names[i], a, b))


class TestCSVEncoding(EncodingAssertionsMixin, AgateTestCase):
    def _path(self, tmpdir, encoding):
        return os.path.join(tmpdir, 'table-%s.csv' % encoding.replace('-', '_'))

    def test_default_writes_utf8_bytes(self):
        table = make_table('中文数据 👍 café')

        table.to_csv('.test-default-encoding.csv')

        # Read the raw bytes: the default must be UTF-8 regardless of the
        # platform's preferred encoding (cp936 on this Windows machine).
        with open('.test-default-encoding.csv', 'rb') as f:
            raw = f.read()

        self.assertIn('中文数据'.encode('utf-8'), raw)
        self.assertIn('👍'.encode('utf-8'), raw)

        reloaded = Table.from_csv('.test-default-encoding.csv')
        self.assertRoundTrips(table, reloaded)

        os.remove('.test-default-encoding.csv')

    def test_round_trip_for_every_encoding(self):
        tmpdir = '.test-encoding-csv'
        os.makedirs(tmpdir, exist_ok=True)

        try:
            for encoding, sample in ENCODINGS:
                with self.subTest(encoding=encoding):
                    table = make_table(sample)
                    path = self._path(tmpdir, encoding)

                    table.to_csv(path, encoding=encoding)

                    # The same explicit codec must be used on the way back in.
                    reloaded = Table.from_csv(path, encoding=encoding)
                    self.assertRoundTrips(table, reloaded)

                    # The on-disk bytes must really be the chosen encoding,
                    # not a UTF-8 file in disguise: decoding them as UTF-8
                    # must fail for the non-UTF-8 codecs, while decoding them
                    # with the declared codec must reproduce the content.
                    with open(path, 'rb') as f:
                        raw = f.read()

                    with open(path, encoding=encoding, newline='') as f:
                        decoded = f.read()

                    self.assertEqual(decoded.encode(encoding).replace(b'\r\n', b'\n'),
                                     raw.replace(b'\r\n', b'\n'))

                    # utf-8-sig is still UTF-8 (it only adds a BOM), so only
                    # the genuinely different codecs must fail UTF-8 decoding.
                    if encoding not in ('utf-8', 'utf-8-sig'):
                        with self.assertRaises(UnicodeDecodeError):
                            raw.decode('utf-8')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_special_values_are_verbatim_under_explicit_encoding(self):
        table = make_table('中文数据 👍')

        table.to_csv('.test-special.csv', encoding='utf-8')

        # newline='' disables platform newline translation so the assertion is
        # about agate's own serialization, not the OS text-mode layer.
        with open('.test-special.csv', encoding='utf-8', newline='') as f:
            text = f.read()

        # Parse it back through agate's own reader: every special value form
        # must survive the explicit-encoding write byte-for-byte at the value
        # level, independent of the platform's newline translation.
        reloaded = Table.from_csv('.test-special.csv', encoding='utf-8')
        self.assertRoundTrips(table, reloaded)

        # Structural checks on the raw text: header first, embedded newline
        # stays inside quotes, embedded quotes are doubled, nulls stay empty.
        self.assertTrue(text.startswith('number,text,boolean,note'))
        self.assertIn('"line1', text)
        self.assertIn('line2"', text)
        self.assertIn('"引号""quote"""', text)
        # The null-number row begins with an empty field.
        self.assertIn((os.linesep if '\r\n' in text else '\n') + ',中文数据 👍,,', text)

        os.remove('.test-special.csv')

    def test_legacy_none_uses_platform_preferred_encoding(self):
        preferred = locale.getpreferredencoding(False)

        # ASCII-only content so the platform codec can always encode it.
        ascii_table = Table(
            ((Decimal('1'), 'plain text', True, None),),
            ['number', 'text', 'boolean', 'note'],
            [Number(), Text(), Boolean(), Text()],
        )

        path = '.test-legacy.csv'
        ascii_table.to_csv(path, encoding=None)

        with open(path, 'rb') as f:
            raw = f.read()

        with open(path, encoding=preferred, newline='') as f:
            self.assertEqual(f.read().encode(preferred), raw)

        reloaded = Table.from_csv(path, encoding=preferred)
        self.assertRows(reloaded, ascii_table.rows)

        os.remove(path)


class TestJSONEncoding(EncodingAssertionsMixin, AgateTestCase):
    def _path(self, tmpdir, encoding):
        return os.path.join(tmpdir, 'table-%s.json' % encoding.replace('-', '_'))

    def test_default_writes_utf8_bytes(self):
        table = make_table('中文数据 👍 café')

        table.to_json('.test-default-encoding.json')

        with open('.test-default-encoding.json', 'rb') as f:
            raw = f.read()

        self.assertIn('中文数据'.encode('utf-8'), raw)
        self.assertIn('👍'.encode('utf-8'), raw)

        reloaded = Table.from_json('.test-default-encoding.json')
        self.assertRoundTrips(table, reloaded)

        os.remove('.test-default-encoding.json')

    def test_round_trip_for_every_encoding(self):
        tmpdir = '.test-encoding-json'
        os.makedirs(tmpdir, exist_ok=True)

        try:
            for encoding, sample in ENCODINGS:
                with self.subTest(encoding=encoding):
                    table = make_table(sample)
                    path = self._path(tmpdir, encoding)

                    table.to_json(path, encoding=encoding, newline=True)

                    reloaded = Table.from_json(path, encoding=encoding, newline=True)
                    self.assertRoundTrips(table, reloaded)

                    with open(path, 'rb') as f:
                        raw = f.read()

                    with open(path, encoding=encoding, newline='') as f:
                        decoded = f.read()

                    self.assertEqual(decoded.encode(encoding).replace(b'\r\n', b'\n'),
                                     raw.replace(b'\r\n', b'\n'))

                    # utf-8-sig is still UTF-8 (it only adds a BOM), so only
                    # the genuinely different codecs must fail UTF-8 decoding.
                    if encoding not in ('utf-8', 'utf-8-sig'):
                        with self.assertRaises(UnicodeDecodeError):
                            raw.decode('utf-8')
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_keyed_and_indented_round_trip(self):
        table = Table(
            (('键一', Decimal('3.14')), ('键二', Decimal('-0.001'))),
            ['name', 'value'],
            [Text(), Number()],
        )
        tmpdir = '.test-json-keyed'
        os.makedirs(tmpdir, exist_ok=True)

        try:
            for encoding in ('utf-8', 'gbk'):
                with self.subTest(encoding=encoding):
                    path = os.path.join(tmpdir, 'keyed-%s.json' % encoding)

                    table.to_json(path, key='name', indent=2, encoding=encoding)

                    # Keyed output is a top-level dictionary; decode it with
                    # the matching codec and verify its content and precision.
                    with open(path, encoding=encoding) as f:
                        parsed = json.load(f, parse_float=Decimal)

                    self.assertEqual(set(parsed.keys()), {'键一', '键二'})
                    self.assertEqual(parsed['键一']['value'], Decimal('3.14'))
                    self.assertEqual(parsed['键二']['value'], Decimal('-0.001'))

                    # The non-ASCII keys must be present as raw encoded bytes,
                    # not ASCII \\u escapes (ensure_ascii=False).
                    with open(path, 'rb') as f:
                        raw = f.read()

                    self.assertIn('键一'.encode(encoding), raw)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_nulls_and_unicode_are_verbatim_under_explicit_encoding(self):
        table = make_table('中文数据 👍 café')

        table.to_json('.test-special.json', encoding='utf-8')

        with open('.test-special.json', encoding='utf-8') as f:
            parsed = json.load(f)

        # Nulls stay JSON null; non-ASCII is emitted unescaped (ensure_ascii=False).
        self.assertIsNone(parsed[2]['number'])
        self.assertIsNone(parsed[2]['boolean'])
        self.assertEqual(parsed[2]['text'], '中文数据 👍 café')
        self.assertEqual(parsed[1]['note'], '引号"quote"')
        # Numbers keep their precision through Decimal on reload.
        self.assertEqual(parsed[0]['number'], 1.5)

        with open('.test-special.json', 'rb') as f:
            raw = f.read()

        self.assertIn('中文数据'.encode('utf-8'), raw)
        self.assertNotIn(b'\\u', raw)

        os.remove('.test-special.json')

    def test_legacy_none_uses_platform_preferred_encoding(self):
        preferred = locale.getpreferredencoding(False)
        ascii_table = Table(
            ((Decimal('1'), 'plain text', True, None),),
            ['number', 'text', 'boolean', 'note'],
            [Number(), Text(), Boolean(), Text()],
        )

        path = '.test-legacy.json'
        ascii_table.to_json(path, encoding=None)

        with open(path, 'rb') as f:
            raw = f.read()

        with open(path, encoding=preferred) as f:
            self.assertEqual(f.read().encode(preferred), raw)

        reloaded = Table.from_json(path, encoding=preferred)
        self.assertRows(reloaded, ascii_table.rows)

        os.remove(path)


class TestWriteFailureHandling(AgateTestCase):
    def setUp(self):
        self.table = Table(
            ((Decimal('1'), '中文数据 👍'),),
            ['number', 'text'],
            [Number(), Text()],
        )

    def test_csv_unencodable_content_raises_located_error(self):
        path = '.test-failure.csv'

        with self.assertRaises(FileWriteError) as exc:
            self.table.to_csv(path, encoding='ascii')

        message = str(exc.exception)
        self.assertIn(path, message)
        self.assertIn('ascii', message)
        self.assertIsInstance(exc.exception.__cause__, UnicodeEncodeError)

        # No half-written target file and no stray temporary files remain.
        self.assertFalse(os.path.exists(path))
        self.assertEqual([name for name in os.listdir('.') if name.startswith('.agate-')], [])

    def test_json_unencodable_content_raises_located_error(self):
        path = '.test-failure.json'

        with self.assertRaises(FileWriteError) as exc:
            self.table.to_json(path, encoding='ascii')

        message = str(exc.exception)
        self.assertIn(path, message)
        self.assertIn('ascii', message)
        self.assertIsInstance(exc.exception.__cause__, UnicodeEncodeError)
        self.assertFalse(os.path.exists(path))

    def test_existing_file_is_untouched_after_failure(self):
        path = '.test-preserve.csv'

        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write('original,content\n')

        original_bytes = open(path, 'rb').read()

        with self.assertRaises(FileWriteError):
            self.table.to_csv(path, encoding='ascii')

        # The pre-existing file keeps its exact prior content.
        self.assertEqual(open(path, 'rb').read(), original_bytes)

        os.remove(path)

    def test_missing_directory_is_in_error_message(self):
        # A file occupies the intermediate component, so makedirs fails.
        blocker = 'blocker-file'
        with open(blocker, 'w', encoding='utf-8') as f:
            f.write('x')

        try:
            with self.assertRaises(FileWriteError) as exc:
                self.table.to_csv(os.path.join(blocker, 'nested', 'table.csv'), encoding='utf-8')
        finally:
            os.remove(blocker)

        self.assertIn('table.csv', str(exc.exception))
        self.assertIsNotNone(exc.exception.__cause__)

    def test_file_like_object_errors_are_not_wrapped(self):
        # Only filepath writes go through atomic_open; streams keep their
        # original exception semantics and are left open for the caller.
        from io import StringIO

        class BrokenStream(StringIO):
            def write(self, _text):
                raise RuntimeError('stream exploded')

        stream = BrokenStream()

        with self.assertRaises(RuntimeError):
            self.table.to_csv(stream)

        self.assertFalse(stream.closed)

    def test_domain_error_keeps_original_type_and_leaves_no_debris(self):
        # A non-unique JSON key is a ValueError in the serialization layer,
        # not a filesystem/codec failure: it must keep its historical type
        # even on the filepath branch, and the temp file must still be removed.
        duplicate_key_table = Table(
            ((Decimal('3'),), (Decimal('3.0'),)),
            ['a'],
            [Number()],
        )
        path = '.test-dup-key.json'

        with self.assertRaises(ValueError):
            duplicate_key_table.to_json(path, key='a')

        self.assertFalse(os.path.exists(path))
        self.assertEqual([name for name in os.listdir('.') if name.startswith('.agate-')], [])


class TestTableSetEncoding(AgateTestCase):
    def setUp(self):
        # Chinese-only text so both utf-8 and gbk can encode every fixture.
        self.tables = OrderedDict([
            ('表一', Table((('中文', Decimal('1.5')), ('数据', None)), ['text', 'number'], [Text(), Number()])),
            ('表二', Table((('咖啡馆', Decimal('2')),), ['text', 'number'], [Text(), Number()])),
        ])
        self.tableset = TableSet(self.tables.values(), self.tables.keys())

    def test_csv_directory_round_trip_with_encoding(self):
        tmpdir = '.test-tableset-encoding-csv'

        for encoding in ('utf-8', 'gbk'):
            with self.subTest(encoding=encoding):
                self.tableset.to_csv(tmpdir, encoding=encoding)

                reloaded = TableSet.from_csv(tmpdir, ['text', 'number'], [Text(), Number()],
                                             encoding=encoding)

                for name in self.tables:
                    original = self.tables[name]
                    got = reloaded[name]
                    self.assertEqual(len(got.rows), len(original.rows))

                    for row_a, row_b in zip(original.rows, got.rows):
                        for a, b in zip(row_a, row_b):
                            self.assertEqual(a, b)

                shutil.rmtree(tmpdir, ignore_errors=True)

    def test_json_directory_round_trip_with_encoding(self):
        tmpdir = '.test-tableset-encoding-json'

        for encoding in ('utf-8', 'gbk'):
            with self.subTest(encoding=encoding):
                self.tableset.to_json(tmpdir, encoding=encoding)

                reloaded = TableSet.from_json(tmpdir, encoding=encoding)

                for name in self.tables:
                    original = self.tables[name]
                    got = reloaded[name]

                    for row_a, row_b in zip(original.rows, got.rows):
                        for a, b in zip(row_a, row_b):
                            self.assertEqual(a, b)

                shutil.rmtree(tmpdir, ignore_errors=True)

    def test_nested_json_round_trip_with_encoding(self):
        path = '.test-nested-tableset.json'

        for encoding in ('utf-8', 'gbk'):
            with self.subTest(encoding=encoding):
                self.tableset.to_json(path, nested=True, encoding=encoding)

                reloaded = TableSet.from_json(path, encoding=encoding)

                self.assertEqual(list(reloaded.keys()), list(self.tables.keys()))

                for name in self.tables:
                    for row_a, row_b in zip(self.tables[name].rows, reloaded[name].rows):
                        for a, b in zip(row_a, row_b):
                            self.assertEqual(a, b)

        os.remove(path)

    def test_nested_json_failure_leaves_no_partial_file(self):
        path = '.test-nested-failure.json'

        with self.assertRaises(FileWriteError):
            self.tableset.to_json(path, nested=True, encoding='ascii')

        self.assertFalse(os.path.exists(path))


if __name__ == '__main__':
    unittest.main()
