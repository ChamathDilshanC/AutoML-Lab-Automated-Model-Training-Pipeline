"""Getting queued experiments to a worker.

`db` mode (default): the experiment row *is* the queue and workers poll the table; nothing is
published. `sqs` mode: the API also sends the experiment ID to an SQS queue and workers long-poll it
(docs/ADR/0005). The message carries only the ID. The configuration always comes from the database,
so a message can never change what runs.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

EXPERIMENT_ID = re.compile(r"^ex_[0-9a-f]{32}$")


class JobPublishError(Exception):
    """The job could not be handed to the queue."""


class JobPublisher(Protocol):
    def publish(self, experiment_id: str) -> None: ...


class NullPublisher:
    def publish(self, experiment_id: str) -> None:
        return None


@dataclass(frozen=True)
class QueueMessage:
    receipt_handle: str
    body: str
    receive_count: int


def parse_experiment_id(body: str) -> str | None:
    """The experiment ID in a message body, or `None` if the message is not one of ours."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    candidate = data.get("experiment_id") if isinstance(data, dict) else None
    if isinstance(candidate, str) and EXPERIMENT_ID.match(candidate):
        return candidate
    return None


class SqsQueue:
    def __init__(self, client: Any, queue_url: str, wait_seconds: int = 20) -> None:
        self._client = client
        self._url = queue_url
        self._wait = wait_seconds

    def publish(self, experiment_id: str) -> None:
        try:
            self._client.send_message(
                QueueUrl=self._url,
                MessageBody=json.dumps({"experiment_id": experiment_id, "version": 1}),
            )
        except Exception as exc:
            logger.exception("Could not send experiment %s to the queue", experiment_id)
            raise JobPublishError("Could not send the job to the queue.") from exc

    def receive(self) -> QueueMessage | None:
        """Wait up to the configured time (long polling) for one message."""
        response = self._client.receive_message(
            QueueUrl=self._url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=self._wait,
            AttributeNames=["ApproximateReceiveCount"],
        )
        messages = response.get("Messages", [])
        if not messages:
            return None
        message = messages[0]
        return QueueMessage(
            receipt_handle=message["ReceiptHandle"],
            body=message["Body"],
            receive_count=int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1)),
        )

    def delete(self, message: QueueMessage) -> None:
        """Remove a message for good. Until this is called SQS will deliver it again."""
        self._client.delete_message(QueueUrl=self._url, ReceiptHandle=message.receipt_handle)
