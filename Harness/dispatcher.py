# Line 1:  Import the envelope class — the dispatcher creates envelopes for delegation.
from Harness.envelope import (
    MessageEnvelope,
)  # Line 2:  Import the bus type for type hints (we don't instantiate it here, just reference it).
from Harness.message_bus import (
    MessageBus,
)  # Line 3:  Import typing for the domain registry dict.
from typing import Dict, Optional  # Line 4:  (blank line)


class Dispatcher:  # Line 6:  Decides WHERE a task should go and publishes the delegation message non-blockingly.
    """Routes tasks to the correct agent based on domain knowledge.

    Analogy: A receptionist at a hospital. You say "I need a dentist" and they
    point you to the right office. They don't perform the dental work themselves —
    they just know who does what and get you in front of the right person.

    Key design decision: The dispatcher is SEPARATE from the agents. This means
    adding a new agent + domain only requires registering here, not modifying
    existing agent code. Open/closed principle in action.
    """

    def __init__(
        self, bus: MessageBus
    ):  # Line 17:  Bind to the shared bus so we can publish messages on behalf of agents.
        # Line 18:  Store a reference to the bus — all publishing goes through this single object.
        self.bus = bus  # Line 19:  (blank line)
        # Line 20:  Maps domain name → agent_id that handles it (e.g. "math" → "math_agent").
        self._domain_map: Dict[str, str] = (
            {}
        )  # Line 21:  This is the "routing table" — add a new entry to support a new agent type.

    def register_domain(
        self, domain: str, agent_id: str
    ) -> None:  # Line 23:  Tell the dispatcher which agent handles which domain.
        # Line 24:  Store the mapping so future route() calls can look up the right recipient.
        self._domain_map[domain] = (
            agent_id  # Line 25:  If two agents claim the same domain, the last registration wins (documented behavior).
        )

    def route(
        self, task_text: str, sender_id: str
    ) -> Optional[
        MessageEnvelope
    ]:  # Line 27:  Determine which agent should handle this task and publish a delegation if needed.
        """Analyze the task text and route it to the appropriate agent.

        Returns the envelope if a delegation was sent, or None if the sender
        already handles this domain (no delegation needed).
        """
        # Line 34:  Determine which domain this task belongs to based on keyword matching.
        target_domain = self._detect_domain(
            task_text
        )  # Line 35:  This is a simplified router — in production you'd use an LLM or intent classifier.
        # Line 36:  If we can't determine the domain, return None (sender handles it or rejects).
        if (
            target_domain is None
        ):  # Line 37:  Unknown task type — let the receiving agent decide what to do.
            # Line 38:  Return None to signal "no routing decision made."
            return None  # Line 39:  (blank line)
        # Line 40:  Look up which agent is responsible for this domain.
        target_agent = self._domain_map.get(
            target_domain
        )  # Line 41:  .get() returns None if the domain isn't registered (e.g. new domain not yet mapped).
        # Line 42:  If the domain exists but no agent is registered for it, we can't route.
        if (
            target_agent is None
        ):  # Line 43:  This is a configuration error — the domain was detected but no agent claims it.
            # Line 44:  Print a warning so the developer knows to register an agent for this domain.
            print(
                f"  [DISPATCHER] WARNING: Domain '{target_domain}' has no registered agent."
            )  # Line 45:  Visible in terminal even without trace logging enabled.
            # Line 46:  Return None — we cannot complete the routing.
            return None  # Line 47:  (blank line)
        # Line 48:  If the target is the same as the sender, no delegation needed.
        if (
            target_agent == sender_id
        ):  # Line 49:  The agent that received the task is already the right one — no forwarding.
            # Line 50:  Return None to indicate "you handle this yourself."
            return None  # Line 51:  (blank line)
        # Line 52:  Create a delegation envelope addressed to the target agent.
        envelope = MessageEnvelope(  # Line 53:  Construct the message that will travel through the bus.
            sender_id=sender_id,  # Line 54:  Record who is delegating so the target can send a response back.
            recipient_id=target_agent,  # Line 55:  The agent that should pick this up and process it.
            subject="delegation",  # Line 56:  Subject tag lets the receiving agent know this is a forwarded task, not a direct user query.
            payload={
                "task": task_text,
                "original_sender": sender_id,
            },  # Line 57:  Carry the original task text and who asked for it (for response routing).
        )  # Line 58:  Close the constructor call.
        # Line 59:  Publish the envelope to the bus — this is the non-blocking delegation act.
        self.bus.publish(
            envelope
        )  # Line 60:  After this line returns, the sender is free to do other work (or wait for a response).
        # Line 61:  Return the envelope so the caller can log it or track the correlation ID.
        return envelope  # Line 62:  (blank line)

    def _detect_domain(
        self, task_text: str
    ) -> Optional[
        str
    ]:  # Line 64:  Simple keyword-based domain detection — maps task text to a domain string.
        """Determine which domain a task belongs to using keyword matching.

        In production this would be an LLM call or NLP classifier. Here we use
        simple keywords to keep the toy dependency-free and transparent.
        """
        # Line 71:  Normalize input to lowercase for case-insensitive matching.
        text = (
            task_text.lower()
        )  # Line 72:  "Store" and "store" should both match — normalization prevents missed delegations.
        # Line 73:  Check for math-domain keywords first (order matters if a word appears in multiple lists).
        math_keywords = [
            "add",
            "subtract",
            "multiply",
            "sum",
            "difference",
            "product",
        ]  # Line 74:  These words strongly indicate a mathematical operation is requested.
        # Line 75:  If any math keyword is present, classify as "math" domain.
        if any(
            kw in text for kw in math_keywords
        ):  # Line 76:  Using `any()` short-circuits on first match — efficient for small keyword lists.
            # Line 77:  Return the domain tag that the dispatcher's _domain_map will recognize.
            return "math"  # Line 78:  (blank line)
        # Line 79:  Check for memory-domain keywords.
        memory_keywords = [
            "store",
            "recall",
            "remember",
            "forget",
            "list",
            "save",
            "retrieve",
        ]  # Line 80:  These words indicate the user wants to interact with persistent state.
        # Line 81:  If any memory keyword is present, classify as "memory" domain.
        if any(
            kw in text for kw in memory_keywords
        ):  # Line 82:  Same short-circuit pattern as above.
            # Line 83:  Return the memory domain tag.
            return "memory"  # Line 84:  (blank line)
        # Line 85:  No known keywords matched — we can't determine the domain.
        return None  # Line 86:  The receiving agent will handle this as an unknown/unsupported request.
