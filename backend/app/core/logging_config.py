import logging
import re

# A check-in link's token is a credential for a patient's day. Links put it after
# '#', which browsers never send, but links sent before that carry ?token=, and
# uvicorn's access log records every request URL.
TOKEN_IN_URL = re.compile(r"([?&#]token=)[^&#\s\"]+")


class RedactCheckInTokens(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                TOKEN_IN_URL.sub(r"\1[redacted]", arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("uvicorn.access").addFilter(RedactCheckInTokens())
