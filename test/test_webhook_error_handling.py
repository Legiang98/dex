import os
import sys
import importlib
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/hyperliquid_python"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_gatekeeper_returns_400_for_malformed_json(monkeypatch):
    monkeypatch.setattr("functions.gatekeeper.sqs", MagicMock())
    from functions.gatekeeper import handler

    response = handler({"body": "{'symbol': 'SKYUSDT'}"}, None)

    assert response["statusCode"] == 400
    assert response["body"] == '{"error": "Request body must be valid JSON"}'


def test_order_statuses_preserve_hyperliquid_string_error():
    from helpers.error_handler import AppError
    from services.execute_order import get_order_statuses

    with pytest.raises(AppError, match="Hyperliquid rejected the order: Insufficient margin"):
        get_order_statuses({"status": "err", "response": "Insufficient margin"})


def test_order_statuses_accepts_success_response():
    from services.execute_order import get_order_statuses

    statuses = get_order_statuses({
        "status": "ok",
        "response": {"data": {"statuses": [{"resting": {"oid": 123}}]}},
    })

    assert statuses == [{"resting": {"oid": 123}}]


def test_executor_notifies_telegram_for_execution_failure():
    from functions.executor import notify_execution_failure
    from models.webhook import WebhookPayload

    payload = WebhookPayload(
        symbol="SKY",
        action="ENTRY",
        type="BUY",
        price=0.0705,
    )

    with patch("functions.executor.send_execution_failure_notification") as notify:
        notify_execution_failure(payload, "Insufficient margin")

    notify.assert_called_once_with(
        symbol="SKY",
        action="ENTRY",
        order_type="BUY",
        price=0.0705,
        error="Insufficient margin",
    )


def test_failure_notification_sends_to_configured_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    sys.modules.pop("helpers.telegram", None)
    telegram = importlib.import_module("helpers.telegram")

    with patch("helpers.config_helpers.get_secret", return_value="token"), patch.object(
        telegram, "send_telegram_message"
    ) as send_message:
        telegram.send_execution_failure_notification("SKY", "ENTRY", "BUY", 0.0705, "Insufficient margin")

    send_message.assert_called_once_with(
        "12345",
        "token",
        "❌ Trade Execution Failed\nENTRY BUY SKY @ 0.0705\nError: Insufficient margin",
    )
