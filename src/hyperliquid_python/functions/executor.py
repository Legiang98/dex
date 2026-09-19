import json
from services.parse_webhook import parse_webhook
from services.validate_signal import validate_signal
from services.build_order import build_order
from services.execute_order import execute_order
from services.close_order import close_order
from services.log_trade import log_trade
from helpers.telegram import send_execution_failure_notification


def notify_execution_failure(payload, error) -> None:
    """Failure notifications must not prevent SQS retry/error handling."""
    try:
        send_execution_failure_notification(
            symbol=payload.symbol,
            action=payload.action,
            order_type=payload.type,
            price=payload.price,
            error=str(error),
        )
    except Exception as notification_error:
        print(f"Failed to send execution-failure notification: {notification_error}")

def handler(event, context):
    try:
        records = event.get('Records', [])
        print(f"Processing {len(records)} trade signals from SQS")
        
        for record in records:
            message = record.get('body')
            print("Raw SQS message:", message)
            
            raw_payload = json.loads(message)
            payload = parse_webhook(raw_payload)
            
            validation = validate_signal(payload)
            print(f"Validation Result: is_valid={validation.is_valid}, reason={validation.reason}, skipped={validation.skipped}")
            
            if not validation.is_valid:
                print(f"Validation skipped: {validation.reason}")
                continue
                
            action = payload.action.upper()
            order_result = None
            
            if action == "ENTRY":
                trade_order = build_order(payload)
                print(f"Build Order: {trade_order.symbol} {trade_order.type} {trade_order.quantity} @ {trade_order.price}")
                
                order_result = execute_order(trade_order)
                if order_result.success:
                    print(f"✅ Order Executed: {order_result.orderId}")
                else:
                    print(f"❌ Execution Failed: {order_result.error}")
                    notify_execution_failure(trade_order, order_result.error or "Unknown execution error")
                
            elif action == "EXIT":
                order_result = close_order(payload)
                if order_result.success:
                    print(f"✅ Exit Order Executed: {order_result.orderId}")
                else:
                    print(f"❌ Exit Failed: {order_result.error}")
                    notify_execution_failure(payload, order_result.error or "Unknown execution error")
                
            else:
                print(f"Unknown action in queue: {action}")
                continue
                
            if order_result:
                log_trade(payload, order_result)
                
    except Exception as error:
        print(f"Fatal error in background trade processing: {error}")
        raise error
