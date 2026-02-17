"""
PURPOSE: WebSocket endpoint for real-time live updates in JSR Hydra trading system.

Provides a persistent connection for clients to receive real-time events including:
- Trade opened/closed events
- Market regime changes
- Allocation updates
- Risk alerts and kill switch events
"""

import json
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.events.bus import get_event_bus
from app.events.types import EventPayload
from app.utils.logger import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# Track connected clients
_connected_clients: Set[WebSocket] = set()


# ════════════════════════════════════════════════════════════════
# WebSocket Event Handler
# ════════════════════════════════════════════════════════════════


async def broadcast_event(event: EventPayload) -> None:
    """
    PURPOSE: Broadcast an event from EventBus to all connected WebSocket clients.

    CALLED BY: EventBus subscribers, background tasks

    Args:
        event: EventPayload to broadcast to clients

    Returns:
        None
    """
    disconnected = []

    for client in _connected_clients:
        try:
            # Convert event to JSON and send to client
            message = {
                "type": "event",
                "event_type": event.event_type,
                "data": event.data,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
                "severity": event.severity,
            }
            await client.send_json(message)

        except Exception as e:
            logger.warning(
                "websocket_send_failed",
                error=str(e),
                client_count=len(_connected_clients)
            )
            disconnected.append(client)

    # Clean up disconnected clients
    for client in disconnected:
        _connected_clients.discard(client)


# ════════════════════════════════════════════════════════════════
# WebSocket Endpoint
# ════════════════════════════════════════════════════════════════


@router.websocket("/live")
async def websocket_live_updates(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    PURPOSE: WebSocket endpoint for live streaming of trading events and system updates.

    CALLED BY: Frontend dashboard component for real-time updates

    Behavior:
        1. Accept WebSocket connection
        2. Register client in connected set
        3. Subscribe to event bus for all events
        4. Listen for heartbeat/ping messages from client
        5. Broadcast all events to this client
        6. Handle disconnection gracefully

    Args:
        websocket: WebSocket connection from client
        db: Database session (available if needed for context)

    Returns:
        None (runs indefinitely until disconnect)

    Raises:
        WebSocketDisconnect: Client initiated disconnect
    """
    await websocket.accept()

    # Add client to connected set
    _connected_clients.add(websocket)
    client_id = id(websocket)

    logger.info(
        "websocket_client_connected",
        client_id=client_id,
        total_clients=len(_connected_clients)
    )

    try:
        # Get event bus and register handler
        event_bus = get_event_bus()

        # Create a handler that broadcasts to this specific client
        async def event_handler(event: EventPayload) -> None:
            """Forward events to this WebSocket client."""
            try:
                message = {
                    "type": "event",
                    "event_type": event.event_type,
                    "data": event.data,
                    "timestamp": event.timestamp.isoformat(),
                    "source": event.source,
                    "severity": event.severity,
                }
                await websocket.send_json(message)
            except Exception as e:
                logger.debug(
                    "websocket_event_send_failed",
                    client_id=client_id,
                    error=str(e)
                )

        # Subscribe to all events
        # NOTE: In production, could filter by event type based on client request
        event_bus.on("trade_opened", event_handler)
        event_bus.on("trade_closed", event_handler)
        event_bus.on("regime_changed", event_handler)
        event_bus.on("allocation_updated", event_handler)
        event_bus.on("kill_switch_triggered", event_handler)
        event_bus.on("daily_loss_limit_reached", event_handler)

        # Listen for client messages (heartbeat, subscriptions, etc)
        while True:
            try:
                data = await websocket.receive_text()

                if not data:
                    continue

                try:
                    message = json.loads(data)
                    message_type = message.get("type", "unknown")

                    if message_type == "ping":
                        # Respond to ping with pong
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": json.dumps(
                                {"time": __import__('datetime').datetime.utcnow().isoformat()}
                            )
                        })

                    elif message_type == "subscribe":
                        # Client can subscribe to specific event types
                        event_types = message.get("events", [])
                        logger.info(
                            "websocket_subscription_changed",
                            client_id=client_id,
                            events=event_types
                        )
                        await websocket.send_json({
                            "type": "subscription_confirmed",
                            "events": event_types
                        })

                    else:
                        logger.debug(
                            "websocket_unknown_message_type",
                            client_id=client_id,
                            message_type=message_type
                        )

                except json.JSONDecodeError as e:
                    logger.warning(
                        "websocket_json_decode_failed",
                        client_id=client_id,
                        error=str(e)
                    )
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid JSON format"
                    })

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        logger.info(
            "websocket_client_disconnected",
            client_id=client_id,
            total_clients=len(_connected_clients) - 1
        )

    except Exception as e:
        logger.error(
            "websocket_error",
            client_id=client_id,
            error=str(e)
        )

    finally:
        # Always remove client from connected set
        _connected_clients.discard(websocket)
        logger.info(
            "websocket_client_cleanup",
            client_id=client_id,
            remaining_clients=len(_connected_clients)
        )


# ════════════════════════════════════════════════════════════════
# Utility Functions
# ════════════════════════════════════════════════════════════════


def get_connected_client_count() -> int:
    """
    PURPOSE: Get current count of connected WebSocket clients.

    CALLED BY: Monitoring, diagnostics

    Returns:
        int: Number of connected clients
    """
    return len(_connected_clients)
