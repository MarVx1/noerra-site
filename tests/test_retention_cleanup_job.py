import unittest
from unittest.mock import patch

from scheduler.scheduler import run_retention_cleanup, RETENTION_DAYS


class TestRunRetentionCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_calls_cleanup_with_configured_retention_days(self):
        with patch("database.db.cleanup_unpublished_older_than", return_value={"articles": 3}) as cleanup:
            await run_retention_cleanup()
        cleanup.assert_called_once_with(RETENTION_DAYS)

    async def test_does_not_raise_when_cleanup_fails(self):
        with patch("database.db.cleanup_unpublished_older_than", side_effect=RuntimeError("db locked")):
            await run_retention_cleanup()  # не должно бросить исключение


if __name__ == "__main__":
    unittest.main()
