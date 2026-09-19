from models.webhook import WebhookPayload
from models.common import OrderResult
from helpers.error_handler import AppError
from constants.http import HTTP
from helpers.hyperliquid_helpers import get_env_config, create_clients, extract_order_id, get_asset_info
from repositories.dynamo_repository import insert_order
from helpers.telegram import send_notification
from models.order import NewOrder


def get_order_statuses(order_response):
    """Extract Hyperliquid order statuses without hiding an API error response."""
    if not isinstance(order_response, dict):
        raise AppError(f"Unexpected Hyperliquid order response: {order_response!r}", HTTP.BAD_REQUEST)

    response = order_response.get("response")
    if not isinstance(response, dict):
        detail = response if response is not None else order_response
        raise AppError(f"Hyperliquid rejected the order: {detail}", HTTP.BAD_REQUEST)

    data = response.get("data")
    if not isinstance(data, dict):
        raise AppError(f"Unexpected Hyperliquid order response data: {response!r}", HTTP.BAD_REQUEST)

    statuses = data.get("statuses")
    if not isinstance(statuses, list) or not statuses:
        raise AppError(f"Hyperliquid order response has no statuses: {data!r}", HTTP.BAD_REQUEST)

    return statuses


def execute_order(signal: WebhookPayload) -> OrderResult:
    try:
        if not signal.quantity:
            raise AppError("Quantity is required. Did you call build_order first?", HTTP.BAD_REQUEST)
        
        private_key, user_address, is_testnet = get_env_config()
        exchange_client, info_client = create_clients(private_key, is_testnet)
        asset_info, asset_id = get_asset_info(info_client, signal.symbol)

        is_buy = signal.type.upper() == "BUY"
        size = float(signal.quantity)

        # 1. Prepare Batched Orders (Main Entry + Stop Loss)
        # bulk_orders expects OrderRequest objects (not raw wires)
        orders = [{
            "coin": signal.symbol,
            "is_buy": is_buy,
            "sz": size,
            "limit_px": float(signal.price),
            "order_type": {"limit": {"tif": "Gtc"}},
            "reduce_only": False
        }]

        if signal.stopLoss:
            orders.append({
                "coin": signal.symbol,
                "is_buy": not is_buy,
                "sz": size,
                "limit_px": float(signal.stopLoss),
                "order_type": {
                    "trigger": {
                        "isMarket": True,
                        "triggerPx": float(signal.stopLoss),
                        "tpsl": "sl"
                    }
                },
                "reduce_only": True
            })

        # 2. Execute Batch Order (Single Network Call)
        # In python sdk, exchange_client.bulk_orders expects a list of order dicts
        # BUT exchange.bulk_orders signature: bulk_orders(self, orders: list[dict])
        grouping = "normalTpsl" if signal.stopLoss else "na"
        order_response = exchange_client.bulk_orders(orders, grouping=grouping)
        statuses = get_order_statuses(order_response)

        main_order_status = statuses[0]
        order_id = extract_order_id(main_order_status)

        stop_loss_oid = None
        if signal.stopLoss and len(statuses) > 1:
            try:
                stop_loss_oid = str(extract_order_id(statuses[1]))
            except AppError:
                pass

        # 3. Database & Notifications
        new_order = NewOrder(
            user_address=user_address,
            symbol=signal.symbol,
            strategy=signal.strategy,
            quantity=signal.quantity,
            order_type=signal.type,
            price=signal.price,
            oid=str(order_id),
            stopLossOid=stop_loss_oid,
            stopLossPrice=signal.stopLoss,
            status="open"
        )
        
        db_order = insert_order(new_order)
        
        try:
            send_notification(
                title="Order Executed",
                symbol=signal.symbol,
                is_buy=is_buy,
                price=signal.price,
                stop_loss=signal.stopLoss,
                position_value=signal.positionValue
            )
        except Exception as e:
            print("Notification failed:", e)

        return OrderResult(
            success=True,
            message=f"Order placed successfully for {signal.symbol}",
            orderId=str(order_id),
            stopLossOrderId=stop_loss_oid,
            dbOrderId=db_order.id
        )

    except Exception as error:
        return OrderResult(
            success=False,
            error=str(error)
        )
