import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TelegramIncrementalDeliveryTests(unittest.TestCase):
    def test_sends_each_report_as_preview_message_and_md_file(self):
        from tradingagents.utils.telegram import maybe_send_report_to_telegram

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "market_report.md"
            report_path.write_text("# Market Report\n\n" + "市场内容" * 1000, encoding="utf-8")

            env = {
                "TRADINGAGENTS_TELEGRAM_ENABLED": "1",
                "TRADINGAGENTS_TELEGRAM_BOT_TOKEN": "token",
                "TRADINGAGENTS_TELEGRAM_CHAT_ID": "chat",
                "TRADINGAGENTS_TELEGRAM_REPORT_PREVIEW_CHARS": "120",
            }
            with patch.dict(os.environ, env, clear=False), \
                 patch("tradingagents.utils.telegram._send_markdown_message") as send_markdown_message, \
                 patch("tradingagents.utils.telegram._send_document") as send_document:
                status = maybe_send_report_to_telegram(
                    ticker="600330.SS",
                    analysis_date="2000-01-01",
                    report_path=report_path,
                    section_name="market_report",
                )

            self.assertEqual(status, "Telegram sent report preview and md file: market_report.md")
            send_markdown_message.assert_called_once()
            send_document.assert_called_once()
            args = send_markdown_message.call_args.args
            self.assertEqual(args[0], "token")
            self.assertEqual(args[1], "chat")
            self.assertIn("600330.SS", args[2])
            self.assertIn("# Market Report", args[2])
            self.assertIn("内容预览", args[2])
            self.assertNotIn("已截断", args[2])
            self.assertLessEqual(len(args[2]), 300)
            document_args = send_document.call_args.args
            self.assertEqual(document_args[0], "token")
            self.assertEqual(document_args[1], "chat")
            self.assertEqual(document_args[2], report_path)

    def test_non_important_report_is_sent_by_default(self):
        from tradingagents.utils.telegram import maybe_send_report_to_telegram

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "news_report.md"
            report_path.write_text("# News Report\n\n**结论**: 关注公告", encoding="utf-8")

            env = {
                "TRADINGAGENTS_TELEGRAM_ENABLED": "1",
                "TRADINGAGENTS_TELEGRAM_BOT_TOKEN": "token",
                "TRADINGAGENTS_TELEGRAM_CHAT_ID": "chat",
            }
            with patch.dict(os.environ, env, clear=False), \
                 patch("tradingagents.utils.telegram._send_markdown_message") as send_markdown_message, \
                 patch("tradingagents.utils.telegram._send_document") as send_document:
                status = maybe_send_report_to_telegram(
                    ticker="600330.SS",
                    analysis_date="2000-01-01",
                    report_path=report_path,
                    section_name="news_report",
                )

            self.assertEqual(status, "Telegram sent report preview and md file: news_report.md")
            send_markdown_message.assert_called_once()
            send_document.assert_called_once()

    def test_small_markdown_table_is_rendered_as_preformatted_table(self):
        from tradingagents.utils.telegram import _markdown_to_telegram_html

        html = _markdown_to_telegram_html(
            "| 指标 | 数值 | 评价 |\n"
            "|---|---:|---|\n"
            "| PE | 15.2 | 偏低 |\n"
            "| PB | 1.8 | 合理 |"
        )

        self.assertIn("<pre>", html)
        self.assertIn("</pre>", html)
        self.assertIn("指标", html)
        self.assertIn("PE", html)
        self.assertNotIn("|---", html)

    def test_wide_markdown_table_is_rendered_as_mobile_cards(self):
        from tradingagents.utils.telegram import _markdown_to_telegram_html

        html = _markdown_to_telegram_html(
            "| 指标 | 数值 | 同比 | 环比 | 分位 | 评价 | 建议 |\n"
            "|---|---:|---:|---:|---:|---|---|\n"
            "| PE | 15.2 | -3% | +1% | 32% | 偏低 | 关注 |\n"
            "| ROE | 12.4% | +2% | +0.5% | 70% | 较好 | 持有 |"
        )

        self.assertNotIn("<pre>", html)
        self.assertIn("<b>PE</b>", html)
        self.assertIn("• 数值：15.2", html)
        self.assertIn("• 建议：关注", html)
        self.assertIn("<b>ROE</b>", html)

    def test_single_report_delivery_is_disabled_without_chat_config(self):
        from tradingagents.utils.telegram import maybe_send_report_to_telegram

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "news_report.md"
            report_path.write_text("news report content", encoding="utf-8")
            with patch.dict(os.environ, {
                "TRADINGAGENTS_TELEGRAM_ENABLED": "1",
                "TRADINGAGENTS_TELEGRAM_BOT_TOKEN": "",
                "TRADINGAGENTS_TELEGRAM_CHAT_ID": "",
            }, clear=False), \
                 patch("tradingagents.utils.telegram._send_message") as send_message, \
                 patch("tradingagents.utils.telegram._send_document") as send_document:
                status = maybe_send_report_to_telegram(
                    ticker="600330.SS",
                    analysis_date="2000-01-01",
                    report_path=report_path,
                    section_name="news_report",
                )

            self.assertIsNone(status)
            send_message.assert_not_called()
            send_document.assert_not_called()
    def test_final_delivery_sends_summary_and_bundle_without_duplicate_final_markdown(self):
        from tradingagents.utils.telegram import maybe_send_analysis_to_telegram

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_dir = root / "reports"
            report_dir.mkdir()
            final_report = report_dir / "final_trade_decision.md"
            final_report.write_text("# Final Decision\n\n**操作**: 观望", encoding="utf-8")
            log_file = root / "message_tool.log"
            log_file.write_text("tool log", encoding="utf-8")

            env = {
                "TRADINGAGENTS_TELEGRAM_ENABLED": "1",
                "TRADINGAGENTS_TELEGRAM_BOT_TOKEN": "token",
                "TRADINGAGENTS_TELEGRAM_CHAT_ID": "chat",
            }
            with patch.dict(os.environ, env, clear=False), \
                 patch("tradingagents.utils.telegram._send_message") as send_message, \
                 patch("tradingagents.utils.telegram._send_markdown_message") as send_markdown_message, \
                 patch("tradingagents.utils.telegram._send_document") as send_document:
                status = maybe_send_analysis_to_telegram(
                    ticker="600330.SS",
                    analysis_date="2000-01-01",
                    results_dir=root,
                    report_dir=report_dir,
                    log_file=log_file,
                )

            self.assertIn("bundle", status)
            send_message.assert_called_once()
            send_markdown_message.assert_not_called()
            send_document.assert_called_once()
            self.assertTrue(str(send_document.call_args.args[2]).endswith(".zip"))
    def test_telegram_http_error_is_sanitized_and_preserves_retry_after(self):
        from tradingagents.utils.telegram import _post_telegram

        response = Mock()
        response.status_code = 429
        response.json.return_value = {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 32}}
        response.raise_for_status.side_effect = requests.HTTPError(
            "429 Client Error: Too Many Requests for url: https://api.telegram.org/botSECRET/sendMessage",
            response=response,
        )

        with patch("tradingagents.utils.telegram.requests.post", return_value=response):
            with self.assertRaises(RuntimeError) as ctx:
                _post_telegram("sendMessage", "SECRET", data={"chat_id": "chat", "text": "x"})

        message = str(ctx.exception)
        self.assertIn("HTTP 429", message)
        self.assertIn("retry_after=32s", message)
        self.assertNotIn("SECRET", message)
        self.assertNotIn("api.telegram.org/bot", message)


if __name__ == "__main__":
    unittest.main()
