import logging

from app.core.logging_config import RedactCheckInTokens


def _access_line(path):
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", path, "1.1", 200), None,
    )
    RedactCheckInTokens().filter(record)
    return record.getMessage()


def test_access_log_lines_never_carry_a_check_in_token():
    line = _access_line("/api/v1/checkin/form?token=eyJhbGciOi.eyJzdWIi.sig-123&day=3")
    assert "eyJ" not in line
    assert "/api/v1/checkin/form?token=[redacted]&day=3" in line
    assert _access_line("/api/v1/alerts?status=open").endswith('"GET /api/v1/alerts?status=open HTTP/1.1" 200')


def test_the_filter_is_on_uvicorns_access_logger():
    # configure_logging runs when app.main is imported, which conftest does.
    assert any(isinstance(f, RedactCheckInTokens) for f in logging.getLogger("uvicorn.access").filters)
