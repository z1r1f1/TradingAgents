import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class UiRefreshConfigTests(unittest.TestCase):
    def test_ui_refresh_defaults_are_low_to_avoid_flicker(self):
        import cli.main as main

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRADINGAGENTS_UI_REFRESH_PER_SECOND", None)
            os.environ.pop("TRADINGAGENTS_UI_UPDATE_INTERVAL_SECONDS", None)
            self.assertEqual(main.get_ui_live_refresh_per_second(), 0.5)
            self.assertEqual(main.get_ui_update_interval_seconds(), 2.0)

    def test_ui_refresh_env_overrides_are_supported(self):
        import cli.main as main

        with patch.dict(
            os.environ,
            {
                "TRADINGAGENTS_UI_REFRESH_PER_SECOND": "1.5",
                "TRADINGAGENTS_UI_UPDATE_INTERVAL_SECONDS": "3.25",
            },
            clear=False,
        ):
            self.assertEqual(main.get_ui_live_refresh_per_second(), 1.5)
            self.assertEqual(main.get_ui_update_interval_seconds(), 3.25)

    def test_should_refresh_live_display_is_throttled_unless_forced(self):
        import cli.main as main

        self.assertFalse(main.should_refresh_live_display(10.0, 9.0, 2.0))
        self.assertTrue(main.should_refresh_live_display(11.0, 9.0, 2.0))
        self.assertTrue(main.should_refresh_live_display(10.0, 9.9, 2.0, force=True))


if __name__ == "__main__":
    unittest.main()
