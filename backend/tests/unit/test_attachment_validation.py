"""What may be uploaded, and under what name.

Pure functions over strings and integers, so these run with no database and no
storage — which is why they can afford to be exhaustive about the cases that
matter. The behavioural half (does storage actually enforce the signed length,
does a rejected upload leave anything behind) lives in
``tests/integration/test_attachments.py``, where there is a real S3 endpoint to
answer it.
"""

from __future__ import annotations

import uuid

import pytest

from app.platform.documents.models import MAX_ATTACHMENT_BYTES
from app.platform.documents.validation import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILENAME_LENGTH,
    FileTooLargeError,
    InvalidFilenameError,
    UnsupportedFileTypeError,
    build_storage_key,
    file_extension,
    sanitize_filename,
    validate_content_type,
    validate_size,
)

# --- The whitelist ----------------------------------------------------------


@pytest.mark.parametrize(
    ("content_type", "filename"),
    [
        ("application/pdf", "contract.pdf"),
        ("image/png", "screenshot.png"),
        ("image/jpeg", "photo.jpg"),
        ("image/jpeg", "photo.jpeg"),
        ("text/csv", "export.csv"),
        ("text/plain", "notes.txt"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "proposal.docx",
        ),
        (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "model.xlsx",
        ),
    ],
)
def test_a_business_document_is_accepted(content_type: str, filename: str) -> None:
    assert validate_content_type(content_type, filename) == content_type


@pytest.mark.parametrize(
    ("content_type", "filename"),
    [
        ("application/x-msdownload", "setup.exe"),
        ("application/x-sh", "install.sh"),
        ("application/x-httpd-php", "shell.php"),
        ("application/java-archive", "app.jar"),
        # Both can carry script. Served inline from the storage origin — which
        # a misconfigured bucket would do — either becomes stored XSS.
        ("text/html", "page.html"),
        ("image/svg+xml", "logo.svg"),
    ],
)
def test_an_executable_or_scriptable_type_is_refused(
    content_type: str, filename: str
) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_content_type(content_type, filename)


def test_the_whitelist_contains_nothing_a_browser_will_execute() -> None:
    """Guards the list itself against a careless addition.

    A block-list is a promise to have thought of every dangerous type; this is
    the inverse check on the allow-list, so adding one of these later fails
    here rather than in production.
    """
    dangerous = {"text/html", "image/svg+xml", "application/javascript", "text/xml"}

    assert not dangerous & set(ALLOWED_CONTENT_TYPES)


def test_a_type_parameter_is_stripped_before_matching() -> None:
    """Browsers send ``text/csv; charset=utf-8``; the whitelist holds bare types."""
    assert validate_content_type("text/csv; charset=utf-8", "export.csv") == "text/csv"


def test_matching_is_case_insensitive() -> None:
    assert validate_content_type("Application/PDF", "contract.pdf") == "application/pdf"


def test_an_extension_that_contradicts_the_type_is_refused() -> None:
    """The mismatch a whitelist alone misses.

    Declaring ``application/pdf`` for ``payload.exe`` would otherwise store an
    executable under a trusted content type and hand it back with one.
    """
    with pytest.raises(UnsupportedFileTypeError):
        validate_content_type("application/pdf", "payload.exe")


def test_a_missing_extension_is_refused() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_content_type("application/pdf", "contract")


def test_a_double_extension_is_judged_on_the_last_one() -> None:
    """``invoice.pdf.exe`` is an executable, whatever the middle says."""
    with pytest.raises(UnsupportedFileTypeError):
        validate_content_type("application/pdf", "invoice.pdf.exe")


def test_extension_matching_ignores_case() -> None:
    assert validate_content_type("application/pdf", "CONTRACT.PDF") == "application/pdf"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("a.pdf", ".pdf"), ("a.PDF", ".pdf"), ("a.b.csv", ".csv"), ("noext", ""), ("x.", "")],
)
def test_extension_extraction(filename: str, expected: str) -> None:
    assert file_extension(filename) == expected


# --- Size -------------------------------------------------------------------


def test_a_file_at_the_ceiling_is_accepted() -> None:
    assert validate_size(MAX_ATTACHMENT_BYTES) == MAX_ATTACHMENT_BYTES


def test_one_byte_over_the_ceiling_is_refused() -> None:
    with pytest.raises(FileTooLargeError):
        validate_size(MAX_ATTACHMENT_BYTES + 1)


@pytest.mark.parametrize("size", [0, -1, -5000])
def test_an_empty_or_negative_size_is_refused(size: int) -> None:
    """An empty object is never a file somebody meant to attach, and the
    table's CHECK constraint forbids it — better a 413 than a 500."""
    with pytest.raises(FileTooLargeError):
        validate_size(size)


def test_the_ceiling_matches_the_documented_limit() -> None:
    """Doc 13: 50 MB for the MVP."""
    assert MAX_ATTACHMENT_BYTES == 50 * 1024 * 1024


# --- Filenames --------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("contract.pdf", "contract.pdf"),
        ("  spaced name.pdf  ", "spaced name.pdf"),
        ("Q3 report (final).xlsx", "Q3 report (final).xlsx"),
        ("data[2026].csv", "data[2026].csv"),
    ],
)
def test_an_ordinary_filename_survives_intact(raw: str, expected: str) -> None:
    """Over-sanitising would mangle every legitimate name."""
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "../../../etc/passwd.pdf",
        "..\\..\\windows\\system32\\config.pdf",
        "/absolute/path/file.pdf",
        "C:\\Users\\admin\\secret.pdf",
    ],
)
def test_a_path_is_reduced_to_its_final_component(raw: str) -> None:
    """The storage key never contains user input, so this protects the
    *metadata* — the name is displayed in the CRM and echoed in a
    ``Content-Disposition`` header."""
    cleaned = sanitize_filename(raw)

    assert "/" not in cleaned
    assert "\\" not in cleaned
    assert ".." not in cleaned


@pytest.mark.parametrize(
    "raw",
    ["report\n.pdf", "report\r\n.pdf", "report\t.pdf", "report\x00.pdf"],
)
def test_control_characters_are_stripped(raw: str) -> None:
    """A newline reaching ``Content-Disposition`` would split the header."""
    cleaned = sanitize_filename(raw)

    assert not any(character in cleaned for character in "\n\r\t\x00")


def test_a_quote_cannot_break_out_of_the_disposition_header() -> None:
    cleaned = sanitize_filename('evil";attachment;filename="owned.pdf')

    assert '"' not in cleaned


def test_runs_of_dots_are_collapsed() -> None:
    assert ".." not in sanitize_filename("a....b.pdf")


def test_an_over_long_filename_is_truncated_to_the_column_width() -> None:
    cleaned = sanitize_filename("x" * 900 + ".pdf")

    assert len(cleaned) <= MAX_FILENAME_LENGTH


@pytest.mark.parametrize("raw", ["", "   ", "...", "///", "\x00"])
def test_a_filename_with_nothing_usable_is_refused(raw: str) -> None:
    """Failing closed: an unnamed attachment is not stored under a made-up name."""
    with pytest.raises(InvalidFilenameError):
        sanitize_filename(raw)


def test_non_ascii_names_are_preserved_where_they_can_be() -> None:
    """Accented and non-Latin names are ordinary, not suspicious.

    They are replaced rather than dropped, so the result stays a usable name
    instead of collapsing to nothing.
    """
    cleaned = sanitize_filename("Bericht Übersicht.pdf")

    assert cleaned.endswith(".pdf")
    assert len(cleaned) > 4


# --- Storage keys -----------------------------------------------------------


def test_a_storage_key_is_the_organization_then_the_attachment() -> None:
    """Doc 13: ``{orgId}/{documentId}``. The prefix is a tenant boundary."""
    organization_id = uuid.uuid4()
    attachment_id = uuid.uuid4()

    key = build_storage_key(organization_id, attachment_id)

    assert key == f"{organization_id}/{attachment_id}"


def test_a_storage_key_contains_no_client_supplied_text() -> None:
    """Composed only of two server-generated UUIDs, so a crafted filename
    cannot escape the organization prefix and reach another tenant."""
    key = build_storage_key(uuid.uuid4(), uuid.uuid4())

    assert key.count("/") == 1
    assert ".." not in key
