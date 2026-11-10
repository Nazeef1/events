"""
Thin RabbitMQ wrapper built on `pika`.

Topology:
  exchange:  "eventsphere.events"  (topic, durable)
  queues:    one durable queue per consuming service, bound with a
             routing pattern e.g. "eventsphere.#" (all events) or
             "eventsphere.paymentsucceeded" (one event type).

Reliability:
  - publisher confirms are enabled
  - messages are published as persistent (delivery_mode=2)
  - consumers manually ack only after successful processing; on
    exception the message is nacked and requeued once, then dead-lettered
    to `<queue>.dlq` to avoid poison-message loops.
  - consumers should perform their own idempotency check (e.g. an
    `event_id` uniqueness table) since RabbitMQ only guarantees
    at-least-once delivery.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Callable

import pika
from pika.exceptions import AMQPConnectionError

from .events import EventEnvelope

logger = logging.getLogger("eventsphere.bus")

EXCHANGE_NAME = "eventsphere.events"
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/%2F")


def _connect(retries: int = 10, delay: float = 3.0) -> pika.BlockingConnection:
    last_err = None
    for attempt in range(retries):
        try:
            params = pika.URLParameters(RABBITMQ_URL)
            return pika.BlockingConnection(params)
        except AMQPConnectionError as e:  # pragma: no cover - infra timing
            last_err = e
            logger.warning("RabbitMQ connect attempt %s/%s failed: %s", attempt + 1, retries, e)
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to RabbitMQ after {retries} attempts") from last_err


def _declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="topic", durable=True)


class EventPublisher:
    """Short-lived connection publisher. Safe to instantiate per-request."""

    def publish(self, envelope: EventEnvelope) -> None:
        connection = _connect(retries=5, delay=1.0)
        try:
            channel = connection.channel()
            _declare_topology(channel)
            channel.confirm_delivery()
            body = envelope.model_dump_json().encode("utf-8")
            channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=envelope.routing_key(),
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=envelope.event_id,
                ),
                # Not `mandatory=True`: consumer queues are declared/bound at
                # their own startup, which may race with the very first
                # publish. Losing an unroutable message pre-consumer-startup
                # is acceptable for this system's notification/analytics
                # use cases; booking/payment state itself always lives in
                # Postgres, never only in a message.
            )
            logger.info("Published %s [%s]", envelope.event_type, envelope.event_id)
        finally:
            connection.close()


def publish_event(event_type: str, source_service: str, data: dict) -> EventEnvelope:
    envelope = EventEnvelope(event_type=event_type, source_service=source_service, data=data)
    EventPublisher().publish(envelope)
    return envelope


def consume_forever(
    queue_name: str,
    routing_keys: list[str],
    handler: Callable[[EventEnvelope], None],
    prefetch: int = 10,
) -> None:
    """
    Blocking consumer loop. Intended to be run in its own thread/process
    (see each service's `worker.py`). Declares a durable queue bound to
    the shared topic exchange, plus a dead-letter queue for messages
    that repeatedly fail processing.
    """
    dlq_name = f"{queue_name}.dlq"
    connection = _connect()
    channel = connection.channel()
    _declare_topology(channel)

    channel.queue_declare(queue=dlq_name, durable=True)

    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": dlq_name},
    )
    for key in routing_keys:
        channel.queue_bind(queue=queue_name, exchange=EXCHANGE_NAME, routing_key=key)

    channel.basic_qos(prefetch_count=prefetch)

    def _on_message(ch, method, properties, body):
        try:
            payload = json.loads(body)
            envelope = EventEnvelope.model_validate(payload)
            handler(envelope)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:  # noqa: BLE001
            retry = not method.redelivered
            logger.exception("Failed to process message, %s", "retrying once" if retry else "sending to DLQ")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=retry)

    channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
    logger.info("Consumer listening on queue=%s keys=%s", queue_name, routing_keys)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:  # pragma: no cover
        channel.stop_consuming()
    finally:
        connection.close()
