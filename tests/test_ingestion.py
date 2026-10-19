import pytest

from datasentry import CSVInputError, load_csv, load_csv_path
from datasentry.ingestion import MAX_BYTES


def test_bom_quotes_multiline_and_leading_zeros():
    frame = load_csv(
        b'\xef\xbb\xbfid,description,empty\r\n001,"Hello, ""world""\r\nAgain",\r\n'
    )
    assert frame.to_dict("list") == {
        "id": ["001"],
        "description": ['Hello, "world"\r\nAgain'],
        "empty": [""],
    }
    assert isinstance(frame.iloc[0, 0], str)


@pytest.mark.parametrize("content", [b"", b" \r\n\t", b"\xef\xbb\xbf"])
def test_empty_files_fail(content):
    with pytest.raises(CSVInputError, match="empty"):
        load_csv(content)


@pytest.mark.parametrize("content", [b"a,a\n1,2", b"a, a \n1,2", b",b\n1,2", b"a, \n1,2"])
def test_invalid_headers_fail_before_pandas(content):
    with pytest.raises(CSVInputError, match="[Cc]olumn|Duplicate"):
        load_csv(content)


@pytest.mark.parametrize(
    "content",
    [
        b"a,b\n1",
        b"a,b\n1,2,3",
        b"a,b\n\n",
        b'a\n"unclosed',
        b'a\nbare"quote',
        b'a\n"closed"tail',
        b'a\n "quote"',
    ],
)
def test_malformed_records_never_disappear(content):
    with pytest.raises(CSVInputError):
        load_csv(content)


@pytest.mark.parametrize("content", [b"a\ncaf\xe9", "a\nx".encode("utf-16"), b"a\n\x00"])
def test_unsupported_encodings_and_null_bytes(content):
    with pytest.raises(CSVInputError):
        load_csv(content)


def test_exact_upload_limit_and_large_field():
    frame = load_csv(b"a\n" + b"x" * (MAX_BYTES - 2))
    assert len(frame.iloc[0, 0]) == MAX_BYTES - 2
    with pytest.raises(CSVInputError, match="limit"):
        load_csv(b"a\n" + b"x" * (MAX_BYTES - 1))


def test_path_reader_enforces_limit(tmp_path):
    path = tmp_path / "too-large.csv"
    path.write_bytes(b"a\n" + b"x" * MAX_BYTES)
    with pytest.raises(CSVInputError, match="limit"):
        load_csv_path(path)


def test_header_only_is_valid_empty_dataset():
    frame = load_csv(b"a,b\n")
    assert frame.shape == (0, 2)


def test_missing_fields_are_explicit_cells_and_blank_records_rejected():
    assert load_csv(b"a,b\n,\n1,\n").values.tolist() == [["", ""], ["1", ""]]
    with pytest.raises(CSVInputError, match="Data row 2"):
        load_csv(b"a,b\n1,2\n\n3,4")


def test_multiline_position_error_uses_data_row_not_line_number():
    with pytest.raises(CSVInputError, match="Data row 2"):
        load_csv(b'a,b\n1,"two\nlines"\nmissing')


def test_single_column_csv_and_header_whitespace_preserved():
    frame = load_csv(b" label \nhello\n")
    assert list(frame.columns) == [" label "]
    assert frame.iloc[0, 0] == "hello"
