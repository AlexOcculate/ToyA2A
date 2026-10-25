# Line 1:  Import queue module — provides thread-safe FIFO queues which are the backbone of the bus.
import queue  # Line 2:  Import threading to lock around registry mutations (agents can register at any time).
import threading  # Line 3:  Import time for timeout values in poll calls.
import time  # Line 4:  Import typing for type hints on the registry dict.
from typing import Dict, Optional  # Line 5:  (blank line)

# Line 7:  Import our envelope class — the bus only deals with MessageEnvelope objects.
from Harness.envelope import MessageEnvelope  # Line 8:  (blank line)


class MessageBus:  # Line 10:  The central communication hub — agents publish and poll through this object.
    """An in-memory message bus using one queue per registered agent.

    Analogy: A switchboard operator. Each agent has their own phone line (queue).
    When someone calls (publishes), the message lands on the recipient's line.
    The recipient picks up when ready (polls). No direct connection between agents —
    they only talk to the bus. This is the key decoupling insight.
    """

    def __init__(
        self,
    ):  # Line 18:  Initialize the bus with an empty registry and a lock for thread safety.
        # Line 19:  Maps agent_id → their dedicated queue.Queue instance.
        self._inboxes: Dict[str, "queue.Queue[MessageEnvelope]"] = (
            {}
        )  # Line 20:  Each agent gets its own FIFO queue so messages are never mixed up.
        # Line 21:  A lock to protect _inboxes from concurrent register/publish races.
        self._lock = (
            threading.Lock()
        )  # Line 22:  Without this, two agents registering simultaneously could corrupt the dict.
        # Line 23:  Counter for total messages published — useful for metrics and trace reporting.
        self._total_published: int = (
            0  # Line 24:  Incremented atomically under the lock to avoid lost updates.
        )

    def register(
        self, agent_id: str
    ) -> (
        None
    ):  # Line 26:  Create a dedicated inbox queue for an agent. Must be called before any message is sent to them.
        # Line 27:  Acquire the lock to safely mutate the shared _inboxes dict.
        with self._lock:  # Line 28:  Context manager ensures the lock is released even if an exception occurs inside.
            # Line 29:  Only create a new queue if this agent hasn't been registered yet (idempotent).
            if (
                agent_id not in self._inboxes
            ):  # Line 30:  Prevents accidentally overwriting an existing queue and losing pending messages.
                # Line 31:  Create an unbounded FIFO queue — messages wait until the agent polls them.
                self._inboxes[agent_id] = (
                    queue.Queue()
                )  # Line 32:  Unbounded means no backpressure; for a toy this is fine, production would use bounded queues.

    def publish(
        self, envelope: MessageEnvelope
    ) -> (
        None
    ):  # Line 34:  Place a message onto the recipient's inbox queue. Non-blocking (just a queue.put).
        # Line 35:  Acquire lock to safely read _inboxes and increment the counter.
        with self._lock:  # Line 36:  Protects both the dict lookup and the counter increment as an atomic pair.
            # Line 37:  Check if the recipient is actually registered — if not, we log a warning and drop the message.
            if (
                envelope.recipient_id not in self._inboxes
            ):  # Line 38:  This catches typos in agent IDs or messages sent before registration.
                # Line 39:  Print a visible warning so the developer knows a message was lost.
                print(
                    f"  [BUS] WARNING: No inbox for '{envelope.recipient_id}' — message dropped."
                )  # Line 40:  Using print here (not logger) ensures it's visible even if trace logging is off.
                # Line 41:  Return early — the message cannot be delivered to an unregistered agent.
                return  # Line 42:  (blank line)
            # Line 43:  Increment the global counter for observability.
            self._total_published += 1  # Line 44:  This number appears in the final trace report as a health metric.
        # Line 45:  Release the lock before calling queue.put() to minimize contention.
        # Line 46:  Actually place the envelope on the recipient's queue — this is the "non-blocking" part of delegation.
        self._inboxes[envelope.recipient_id].put(
            envelope
        )  # Line 47:  queue.put() on an unbounded queue never blocks, so the sender continues immediately.

    def poll(
        self, agent_id: str, timeout: float = 0.5
    ) -> Optional[
        MessageEnvelope
    ]:  # Line 49:  Retrieve the next message for this agent, waiting up to `timeout` seconds.
        # Line 50:  Acquire lock to safely look up the queue reference.
        with self._lock:  # Line 51:  We only hold the lock long enough to get the queue object, not during the potentially-blocking get().
            # Line 52:  Check if this agent has a registered inbox at all.
            if (
                agent_id not in self._inboxes
            ):  # Line 53:  An unregistered agent polling is a programming error — return None to signal "no message."
                # Line 54:  Return None to indicate no message available (agent should handle this gracefully).
                return None  # Line 55:  (blank line)
            # Line 56:  Grab a reference to the queue so we can call get() outside the lock.
            q = self._inboxes[
                agent_id
            ]  # Line 57:  Storing the reference avoids holding the lock during the blocking get() call.
        # Line 58:  Attempt to retrieve a message, blocking for up to `timeout` seconds if the queue is empty.
        try:  # Line 59:  Wrap in try/except because queue.get(timeout=...) raises queue.Empty on timeout.
            # Line 60:  Block until a message arrives or timeout expires — this is how the agent "waits for work."
            envelope = q.get(
                timeout=timeout
            )  # Line 61:  The timeout prevents an agent from hanging forever if no messages ever come.
            # Line 62:  Return the retrieved message so the agent can process it.
            return envelope  # Line 63:  (blank line)
        except (
            queue.Empty
        ):  # Line 64:  Timeout expired with no message — this is a normal condition, not an error.
            # Line 65:  Return None to signal "nothing to do right now" — the agent loop will check _running and re-poll.
            return None  # Line 66:  (blank line)

    @property  # Line 68:  Expose the total published count as a read-only property for trace reports.
    def total_published(
        self,
    ) -> (
        int
    ):  # Line 69:  Returns how many messages have been successfully placed on queues since startup.
        # Line 70:  Acquire lock to safely read the counter (it's being incremented by other threads).
        with self._lock:  # Line 71:  Even a simple int read needs the lock in a multi-threaded context for consistency.
            # Line 72:  Return the current count.
            return self._total_published  # Line 73:  (blank line)

    @property  # Line 75:  Expose the list of registered agent IDs for diagnostics and trace reporting.
    def registered_agents(
        self,
    ) -> (
        list
    ):  # Line 76:  Returns a snapshot list of all agent IDs that have inboxes on this bus.
        # Line 77:  Acquire lock to safely iterate over the dict keys.
        with self._lock:  # Line 78:  We copy the keys into a list so the caller can use it without holding our lock.
            # Line 79:  Return a new list (not a live view) to prevent external mutation of internal state.
            return list(self._inboxes.keys())  # Line 80:  (blank line)
