from paper_radar.core.exceptions import RadarError
from paper_radar.infrastructure.http_client import HttpClient
from paper_radar.notifications.base import Notifier, webhook_url


class WeChatNotifier(Notifier):
    """Enterprise WeChat group robot; personal WeChat has no equivalent webhook."""

    name = "wechat"

    def __init__(self, http: HttpClient):
        super().__init__(http)
        self.url = webhook_url("WECHAT_WEBHOOK_URL")

    def send(self, message: str) -> None:
        response = self.http.post_json(self.url, {"msgtype": "text", "text": {"content": message}})
        if type(response.get("errcode")) is not int or response["errcode"] != 0:
            raise RadarError("WeCom rejected notification")
