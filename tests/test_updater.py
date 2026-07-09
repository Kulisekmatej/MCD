"""Tests for the GitHub release update check (no network access needed)."""

import unittest
from unittest import mock

from hours_tracker import updater


class ParseVersionTest(unittest.TestCase):
    def test_plain_and_prefixed_tags(self):
        self.assertEqual(updater.parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("v1.2.0"), (1, 2, 0))
        self.assertEqual(updater.parse_version("Beta_v1.1.1"), (1, 1, 1))
        self.assertEqual(updater.parse_version("release-2"), (2,))

    def test_no_number_returns_none(self):
        self.assertIsNone(updater.parse_version("beta"))
        self.assertIsNone(updater.parse_version(""))


class IsNewerTest(unittest.TestCase):
    def test_newer_versions(self):
        self.assertTrue(updater.is_newer("1.2.0", "1.1.1"))
        self.assertTrue(updater.is_newer("Beta_v1.2", "1.1.1"))
        self.assertTrue(updater.is_newer("v2", "1.9.9"))

    def test_equal_and_older_versions(self):
        self.assertFalse(updater.is_newer("1.1.1", "1.1.1"))
        self.assertFalse(updater.is_newer("1.2", "1.2.0"))  # padded equal
        self.assertFalse(updater.is_newer("1.1.1", "1.2.0"))

    def test_unparsable_is_never_newer(self):
        self.assertFalse(updater.is_newer("beta", "1.1.1"))
        self.assertFalse(updater.is_newer("1.2.0", "unknown"))


class CheckForUpdateTest(unittest.TestCase):
    def test_reports_newer_release(self):
        payload = {"tag_name": "Beta_v9.9.9", "html_url": "https://example.test/rel"}
        with mock.patch.object(updater, "fetch_latest_release", return_value=payload):
            info = updater.check_for_update("1.1.1")
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "9.9.9")
        self.assertEqual(info.tag, "Beta_v9.9.9")
        self.assertEqual(info.url, "https://example.test/rel")

    def test_missing_html_url_falls_back_to_releases_page(self):
        payload = {"tag_name": "v9.9.9"}
        with mock.patch.object(updater, "fetch_latest_release", return_value=payload):
            info = updater.check_for_update("1.1.1")
        self.assertEqual(info.url, updater.RELEASES_PAGE_URL)

    def test_up_to_date_returns_none(self):
        payload = {"tag_name": "Beta_v1.1.1", "html_url": "https://example.test/rel"}
        with mock.patch.object(updater, "fetch_latest_release", return_value=payload):
            self.assertIsNone(updater.check_for_update("1.1.1"))

    def test_network_error_is_silent(self):
        with mock.patch.object(
            updater, "fetch_latest_release", side_effect=OSError("offline")
        ):
            self.assertIsNone(updater.check_for_update("1.1.1"))


class StartUpdateCheckTest(unittest.TestCase):
    def test_callback_runs_via_after_when_update_found(self):
        """The callback must be delivered through root.after (GUI thread)."""

        class FakeRoot:
            def __init__(self):
                self.scheduled = []

            def after(self, _ms, callback):
                self.scheduled.append(callback)

            def run_scheduled(self):
                while self.scheduled:
                    self.scheduled.pop(0)()

        root = FakeRoot()
        found = updater.UpdateInfo(version="9.9.9", tag="v9.9.9", url="u")
        received = []
        with mock.patch.object(updater, "check_for_update", return_value=found):
            updater.start_update_check(root, received.append)
            # The worker thread is near-instant with the mock; wait for the
            # queue to fill, then drain the polling callbacks.
            for _ in range(100):
                root.run_scheduled()
                if received:
                    break
        self.assertEqual(received, [found])


if __name__ == "__main__":
    unittest.main()
