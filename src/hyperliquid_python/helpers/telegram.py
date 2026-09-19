import os
import requests
from typing import Optional, Dict

def send_telegram_message(chat_id: str, token: str, message: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        requests.post(url, json=payload, timeout=5.0)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def send_notification(
    title: str,
    symbol: str,
    is_buy: bool,
    price: float,
    stop_loss: Optional[float] = None,
    position_value: Optional[float] = None,
    pnl: Optional[Dict[str, float]] = None
) -> None:
    is_enabled = os.environ.get('TELEGRAM_ENABLED') == 'true'
    
    if not is_enabled:
        print("Telegram notifications disabled")
        return
        
    from helpers.config_helpers import get_secret
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    ssm_path = os.environ.get("SSM_TELEGRAM_TOKEN_PATH", "/hl/telegram_bot_token")
    token = get_secret('TELEGRAM_BOT_TOKEN', ssm_path)
    
    if not chat_id or not token:
        print("Telegram credentials not configured, skipping notification")
        return

    action = "🟢 BUY" if is_buy else "🔴 SELL"
    message = f"{title}\n{action} {symbol} @ {price}"
    
    if position_value:
        message += f"\n💵 Position Value: ${position_value:.2f}"
    
    if stop_loss is not None:
        message += f"\nSL: {stop_loss}"
        
    if pnl:
        # dict should have netPnl and totalFees
        net_pnl = pnl.get("netPnl", 0)
        total_fees = pnl.get("totalFees", 0)
        pnl_emoji = "💰" if net_pnl >= 0 else "📉"
        message += f"\n\n{pnl_emoji} Net PnL: ${net_pnl:.2f}"
        message += f"\n💸 Fees: ${total_fees:.2f}"

    try:
        send_telegram_message(chat_id, token, message)
    except Exception as e:
        print(f"Failed to send notification: {e}")


def send_execution_failure_notification(
    symbol: str,
    action: str,
    order_type: str,
    price: float,
    error: str,
) -> None:
    """Notify the configured Telegram chat when a queued trade cannot be executed."""
    is_enabled = os.environ.get('TELEGRAM_ENABLED') == 'true'
    if not is_enabled:
        print("Telegram notifications disabled")
        return

    from helpers.config_helpers import get_secret
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    ssm_path = os.environ.get("SSM_TELEGRAM_TOKEN_PATH", "/hl/telegram_bot_token")
    token = get_secret('TELEGRAM_BOT_TOKEN', ssm_path)

    if not chat_id or not token:
        print("Telegram credentials not configured, skipping notification")
        return

    message = (
        "❌ Trade Execution Failed"
        f"\n{action.upper()} {order_type.upper()} {symbol} @ {price}"
        f"\nError: {error}"
    )
    send_telegram_message(chat_id, token, message)
