# Line 1:  Import dataclass decorator to build the message structure with type hints.
from dataclasses import (
    dataclass,
    field,
)  # Line 2:  Also import field() for mutable defaults (lists/dicts).

# Line 3:  Import uuid to generate unique message IDs for tracing and deduplication.
import uuid  # Line 4:  Import time to timestamp each message for ordering and timeout logic.
import time  # Line 5:  (blank line for readability)


@dataclass  # Line 7:  Decorator that auto-generates __init__, __repr__, and __eq__ from field annotations.
class MessageEnvelope:  # Line 8:  The universal message format — every communication between agents uses this.
    """A single unit of inter-agent communication.

    Analogy: Think of this as a postal envelope. It has a sender, a recipient,
    and a payload (the letter inside). The bus is the post office that delivers it.
    """

    # Line 14:  Unique identifier for this message — used to match requests with responses.
    message_id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )  # Line 15:  Auto-generate a UUID so no two messages collide even under concurrent load.
    # Line 16:  The ID of the agent that sent this message (e.g. "math_agent").
    sender_id: str = (
        ""  # Line 17:  Empty string default so we can detect unset senders during validation.
    )
    # Line 18:  The ID of the agent that should receive and process this message.
    recipient_id: str = (
        ""  # Line 19:  Must match a registered agent on the bus or it will be dropped.
    )
    # Line 20:  A short human-readable subject line (e.g. "delegation", "response", "task").
    subject: str = (
        ""  # Line 21:  Used by the trace logger to quickly categorize the message type.
    )
    # Line 22:  The actual data being passed — a dict so it can hold arbitrary key-value pairs.
    payload: dict = field(
        default_factory=dict
    )  # Line 23:  Mutable default via factory to avoid the shared-list bug across instances.
    # Line 24:  Unix timestamp of when this envelope was created.
    timestamp: float = field(
        default_factory=time.time
    )  # Line 25:  Used for timeout calculations and ordering in the trace report.
    # Line 26:  Optional reference to a prior message_id (for request→response correlation).
    reply_to: str = (
        ""  # Line 27:  When agent B responds to agent A, it sets reply_to = A's original message_id.
    )

    def __str__(
        self,
    ) -> (
        str
    ):  # Line 29:  Human-readable summary for logging without dumping the full payload.
        # Line 30:  Format as "msg_id[:8] sender→recipient [subject]" to keep trace lines compact.
        return f"[{self.message_id[:8]}] {self.sender_id} → {self.recipient_id} [{self.subject}]"  # Line 31:  Truncate UUID to 8 chars for readability; full ID available in payload if needed.
