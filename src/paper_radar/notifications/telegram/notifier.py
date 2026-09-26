import re
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from paper_radar.core.exceptions import RadarError
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.notifications.base import Notifier, required_env


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, http: HttpClient):
        super().__init__(http)
        token = required_env("TELEGRAM_BOT_TOKEN")
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
            raise RadarError("Invalid TELEGRAM_BOT_TOKEN format")
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = required_env("TELEGRAM_CHAT_ID")

    def send(self, message: str) -> None:
        sent_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
        timestamp = f"发送时间：{sent_at}（北京时间 UTC+08:00）"
        message = f"{timestamp}\n\n{message}"
        formatted = re.sub(
            r"^(中文标题|总结|中文总结)：",
            r"<b>\1：</b>",
            escape(message),
            flags=re.MULTILINE,
        )
        # Count UTF-16 units conservatively, including emoji, before choosing text delivery.
        if len(message.encode("utf-16-le")) // 2 <= 4096:
            response = self.http.post_json(
                self.url,
                {
                    "chat_id": self.chat_id,
                    "text": formatted,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
        else:
            # Paper URLs occupy their own line; keep the already-escaped text safe in HTML.
            formatted = re.sub(
                r"^https?://[^\s<>]+$",
                lambda match: (
                    f'<a href="{match.group(0)}" target="_blank" rel="noopener noreferrer">'
                    f"{match.group(0)}</a>"
                ),
                formatted,
                flags=re.MULTILINE,
            )
            report = (
                '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                "<title>Paper Radar 论文汇总</title><style>"
                "body{max-width:900px;margin:40px auto;padding:0 20px;"
                "font-family:system-ui,sans-serif;line-height:1.9;color:#222}"
                "main{white-space:pre-wrap;overflow-wrap:anywhere}b{font-weight:700}"
                "</style><body><main>" + formatted + "</main></body></html>"
            )
            response = self.http.post_json(
                self.url.removesuffix("sendMessage") + "sendDocument",
                {
                    "chat_id": self.chat_id,
                    "caption": (
                        f"{timestamp}\nPaper Radar 论文汇总：完整标题、链接和总结请查看附件。"
                    ),
                },
                files={"document": ("paper-radar.html", report.encode("utf-8"), "text/html")},
            )
        if response.get("ok") is not True:
            raise RadarError("Telegram rejected notification")

    def send_batch(self, messages: list[str]) -> None:
        self.send("".join(messages))
