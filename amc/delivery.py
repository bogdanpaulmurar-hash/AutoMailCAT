"""Sends the daily message to Teams.

  webhook  POST an Adaptive Card to the URL of a Teams Workflow
           ("Send webhook alerts to a channel" / "... to a chat")
  email    send the message from Outlook to the e-mail address of the channel
  copy     nothing is sent; the interface shows a Copy button

The webhook uses the proxy configured in Windows (urllib reads it).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .report import adaptive_card

LOG = logging.getLogger("automailcat.delivery")


class DeliveryError(Exception):
    pass


def post_webhook(url: str, report: dict, timeout: int = 20) -> None:
    if not url.lower().startswith("https://"):
        raise DeliveryError("webhook_not_https")
    data = json.dumps(adaptive_card(report)).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 300:
                raise DeliveryError(f"HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        raise DeliveryError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DeliveryError(str(exc.reason)) from exc


def send(team: dict, report: dict, outlook=None) -> str:
    """Delivers the message; returns the channel used. Raises DeliveryError."""
    cfg = team.get("report", {})
    channel = cfg.get("channel", "copy")
    if channel == "webhook":
        if not cfg.get("webhook_url"):
            raise DeliveryError("webhook_missing")
        post_webhook(cfg["webhook_url"], report)
    elif channel == "email":
        if not cfg.get("email_to"):
            raise DeliveryError("email_missing")
        if outlook is None:
            raise DeliveryError("outlook_unavailable")
        outlook.send_mail(cfg["email_to"], report["title"], report["html"])
    LOG.info("Daily message delivered via %s", channel)
    return channel
