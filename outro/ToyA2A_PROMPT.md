# Module #1: ToyA2A — Message Passing + Delegation

## a. Folder Structure

```
ToyA2A/
├── main.py
├── test_adversarial.py
├── README.md
└── Harness/
    ├── __init__.py
    ├── envelope.py          # MessageEnvelope dataclass
    ├── message_bus.py       # In-memory pub/sub queue per agent
    ├── dispatcher.py        # Routes delegation messages (non-blocking)
    ├── simulated_lm.py      # Domain-aware keyword LM with delegate rules
    ├── guardrails.py        # Input validation + iteration cap
    ├── agent.py             # Agent loop: poll inbox → think → act → respond
    └── trace_logger.py      # ANSI-colored execution trace
```

---

## b. Source Code

### `Harness/__init__.py`

```python
# Line 1:  Mark the Harness directory as a Python package so relative imports work.
__all__ = ["envelope", "message_bus", "dispatcher", "simulated_lm", "guardrails", "agent", "trace_logger"]  # Line 2:  Explicitly list public submodules for clarity in IDEs and docs.
```

---

### `Harness/envelope.py`

```python
# Line 1:  Import dataclass decorator to build the message structure with type hints.
from dataclasses import dataclass, field  # Line 2:  Also import field() for mutable defaults (lists/dicts).
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
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # Line 15:  Auto-generate a UUID so no two messages collide even under concurrent load.
    # Line 16:  The ID of the agent that sent this message (e.g. "math_agent").
    sender_id: str = ""  # Line 17:  Empty string default so we can detect unset senders during validation.
    # Line 18:  The ID of the agent that should receive and process this message.
    recipient_id: str = ""  # Line 19:  Must match a registered agent on the bus or it will be dropped.
    # Line 20:  A short human-readable subject line (e.g. "delegation", "response", "task").
    subject: str = ""  # Line 21:  Used by the trace logger to quickly categorize the message type.
    # Line 22:  The actual data being passed — a dict so it can hold arbitrary key-value pairs.
    payload: dict = field(default_factory=dict)  # Line 23:  Mutable default via factory to avoid the shared-list bug across instances.
    # Line 24:  Unix timestamp of when this envelope was created.
    timestamp: float = field(default_factory=time.time)  # Line 25:  Used for timeout calculations and ordering in the trace report.
    # Line 26:  Optional reference to a prior message_id (for request→response correlation).
    reply_to: str = ""  # Line 27:  When agent B responds to agent A, it sets reply_to = A's original message_id.

    def __str__(self) -> str:  # Line 29:  Human-readable summary for logging without dumping the full payload.
        # Line 30:  Format as "msg_id[:8] sender→recipient [subject]" to keep trace lines compact.
        return f"[{self.message_id[:8]}] {self.sender_id} → {self.recipient_id} [{self.subject}]"  # Line 31:  Truncate UUID to 8 chars for readability; full ID available in payload if needed.
```

---

### `Harness/message_bus.py`

```python
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

    def __init__(self):  # Line 18:  Initialize the bus with an empty registry and a lock for thread safety.
        # Line 19:  Maps agent_id → their dedicated queue.Queue instance.
        self._inboxes: Dict[str, "queue.Queue[MessageEnvelope]"] = {}  # Line 20:  Each agent gets its own FIFO queue so messages are never mixed up.
        # Line 21:  A lock to protect _inboxes from concurrent register/publish races.
        self._lock = threading.Lock()  # Line 22:  Without this, two agents registering simultaneously could corrupt the dict.
        # Line 23:  Counter for total messages published — useful for metrics and trace reporting.
        self._total_published: int = 0  # Line 24:  Incremented atomically under the lock to avoid lost updates.

    def register(self, agent_id: str) -> None:  # Line 26:  Create a dedicated inbox queue for an agent. Must be called before any message is sent to them.
        # Line 27:  Acquire the lock to safely mutate the shared _inboxes dict.
        with self._lock:  # Line 28:  Context manager ensures the lock is released even if an exception occurs inside.
            # Line 29:  Only create a new queue if this agent hasn't been registered yet (idempotent).
            if agent_id not in self._inboxes:  # Line 30:  Prevents accidentally overwriting an existing queue and losing pending messages.
                # Line 31:  Create an unbounded FIFO queue — messages wait until the agent polls them.
                self._inboxes[agent_id] = queue.Queue()  # Line 32:  Unbounded means no backpressure; for a toy this is fine, production would use bounded queues.

    def publish(self, envelope: MessageEnvelope) -> None:  # Line 34:  Place a message onto the recipient's inbox queue. Non-blocking (just a queue.put).
        # Line 35:  Acquire lock to safely read _inboxes and increment the counter.
        with self._lock:  # Line 36:  Protects both the dict lookup and the counter increment as an atomic pair.
            # Line 37:  Check if the recipient is actually registered — if not, we log a warning and drop the message.
            if envelope.recipient_id not in self._inboxes:  # Line 38:  This catches typos in agent IDs or messages sent before registration.
                # Line 39:  Print a visible warning so the developer knows a message was lost.
                print(f"  [BUS] WARNING: No inbox for '{envelope.recipient_id}' — message dropped.")  # Line 40:  Using print here (not logger) ensures it's visible even if trace logging is off.
                # Line 41:  Return early — the message cannot be delivered to an unregistered agent.
                return  # Line 42:  (blank line)
            # Line 43:  Increment the global counter for observability.
            self._total_published += 1  # Line 44:  This number appears in the final trace report as a health metric.
        # Line 45:  Release the lock before calling queue.put() to minimize contention.
        # Line 46:  Actually place the envelope on the recipient's queue — this is the "non-blocking" part of delegation.
        self._inboxes[envelope.recipient_id].put(envelope)  # Line 47:  queue.put() on an unbounded queue never blocks, so the sender continues immediately.

    def poll(self, agent_id: str, timeout: float = 0.5) -> Optional[MessageEnvelope]:  # Line 49:  Retrieve the next message for this agent, waiting up to `timeout` seconds.
        # Line 50:  Acquire lock to safely look up the queue reference.
        with self._lock:  # Line 51:  We only hold the lock long enough to get the queue object, not during the potentially-blocking get().
            # Line 52:  Check if this agent has a registered inbox at all.
            if agent_id not in self._inboxes:  # Line 53:  An unregistered agent polling is a programming error — return None to signal "no message."
                # Line 54:  Return None to indicate no message available (agent should handle this gracefully).
                return None  # Line 55:  (blank line)
            # Line 56:  Grab a reference to the queue so we can call get() outside the lock.
            q = self._inboxes[agent_id]  # Line 57:  Storing the reference avoids holding the lock during the blocking get() call.
        # Line 58:  Attempt to retrieve a message, blocking for up to `timeout` seconds if the queue is empty.
        try:  # Line 59:  Wrap in try/except because queue.get(timeout=...) raises queue.Empty on timeout.
            # Line 60:  Block until a message arrives or timeout expires — this is how the agent "waits for work."
            envelope = q.get(timeout=timeout)  # Line 61:  The timeout prevents an agent from hanging forever if no messages ever come.
            # Line 62:  Return the retrieved message so the agent can process it.
            return envelope  # Line 63:  (blank line)
        except queue.Empty:  # Line 64:  Timeout expired with no message — this is a normal condition, not an error.
            # Line 65:  Return None to signal "nothing to do right now" — the agent loop will check _running and re-poll.
            return None  # Line 66:  (blank line)

    @property  # Line 68:  Expose the total published count as a read-only property for trace reports.
    def total_published(self) -> int:  # Line 69:  Returns how many messages have been successfully placed on queues since startup.
        # Line 70:  Acquire lock to safely read the counter (it's being incremented by other threads).
        with self._lock:  # Line 71:  Even a simple int read needs the lock in a multi-threaded context for consistency.
            # Line 72:  Return the current count.
            return self._total_published  # Line 73:  (blank line)

    @property  # Line 75:  Expose the list of registered agent IDs for diagnostics and trace reporting.
    def registered_agents(self) -> list:  # Line 76:  Returns a snapshot list of all agent IDs that have inboxes on this bus.
        # Line 77:  Acquire lock to safely iterate over the dict keys.
        with self._lock:  # Line 78:  We copy the keys into a list so the caller can use it without holding our lock.
            # Line 79:  Return a new list (not a live view) to prevent external mutation of internal state.
            return list(self._inboxes.keys())  # Line 80:  (blank line)
```

---

### `Harness/dispatcher.py`

```python
# Line 1:  Import the envelope class — the dispatcher creates envelopes for delegation.
from Harness.envelope import MessageEnvelope  # Line 2:  Import the bus type for type hints (we don't instantiate it here, just reference it).
from Harness.message_bus import MessageBus  # Line 3:  Import typing for the domain registry dict.
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

    def __init__(self, bus: MessageBus):  # Line 17:  Bind to the shared bus so we can publish messages on behalf of agents.
        # Line 18:  Store a reference to the bus — all publishing goes through this single object.
        self.bus = bus  # Line 19:  (blank line)
        # Line 20:  Maps domain name → agent_id that handles it (e.g. "math" → "math_agent").
        self._domain_map: Dict[str, str] = {}  # Line 21:  This is the "routing table" — add a new entry to support a new agent type.

    def register_domain(self, domain: str, agent_id: str) -> None:  # Line 23:  Tell the dispatcher which agent handles which domain.
        # Line 24:  Store the mapping so future route() calls can look up the right recipient.
        self._domain_map[domain] = agent_id  # Line 25:  If two agents claim the same domain, the last registration wins (documented behavior).

    def route(self, task_text: str, sender_id: str) -> Optional[MessageEnvelope]:  # Line 27:  Determine which agent should handle this task and publish a delegation if needed.
        """Analyze the task text and route it to the appropriate agent.

        Returns the envelope if a delegation was sent, or None if the sender
        already handles this domain (no delegation needed).
        """
        # Line 34:  Determine which domain this task belongs to based on keyword matching.
        target_domain = self._detect_domain(task_text)  # Line 35:  This is a simplified router — in production you'd use an LLM or intent classifier.
        # Line 36:  If we can't determine the domain, return None (sender handles it or rejects).
        if target_domain is None:  # Line 37:  Unknown task type — let the receiving agent decide what to do.
            # Line 38:  Return None to signal "no routing decision made."
            return None  # Line 39:  (blank line)
        # Line 40:  Look up which agent is responsible for this domain.
        target_agent = self._domain_map.get(target_domain)  # Line 41:  .get() returns None if the domain isn't registered (e.g. new domain not yet mapped).
        # Line 42:  If the domain exists but no agent is registered for it, we can't route.
        if target_agent is None:  # Line 43:  This is a configuration error — the domain was detected but no agent claims it.
            # Line 44:  Print a warning so the developer knows to register an agent for this domain.
            print(f"  [DISPATCHER] WARNING: Domain '{target_domain}' has no registered agent.")  # Line 45:  Visible in terminal even without trace logging enabled.
            # Line 46:  Return None — we cannot complete the routing.
            return None  # Line 47:  (blank line)
        # Line 48:  If the target is the same as the sender, no delegation needed.
        if target_agent == sender_id:  # Line 49:  The agent that received the task is already the right one — no forwarding.
            # Line 50:  Return None to indicate "you handle this yourself."
            return None  # Line 51:  (blank line)
        # Line 52:  Create a delegation envelope addressed to the target agent.
        envelope = MessageEnvelope(  # Line 53:  Construct the message that will travel through the bus.
            sender_id=sender_id,  # Line 54:  Record who is delegating so the target can send a response back.
            recipient_id=target_agent,  # Line 55:  The agent that should pick this up and process it.
            subject="delegation",  # Line 56:  Subject tag lets the receiving agent know this is a forwarded task, not a direct user query.
            payload={"task": task_text, "original_sender": sender_id},  # Line 57:  Carry the original task text and who asked for it (for response routing).
        )  # Line 58:  Close the constructor call.
        # Line 59:  Publish the envelope to the bus — this is the non-blocking delegation act.
        self.bus.publish(envelope)  # Line 60:  After this line returns, the sender is free to do other work (or wait for a response).
        # Line 61:  Return the envelope so the caller can log it or track the correlation ID.
        return envelope  # Line 62:  (blank line)

    def _detect_domain(self, task_text: str) -> Optional[str]:  # Line 64:  Simple keyword-based domain detection — maps task text to a domain string.
        """Determine which domain a task belongs to using keyword matching.

        In production this would be an LLM call or NLP classifier. Here we use
        simple keywords to keep the toy dependency-free and transparent.
        """
        # Line 71:  Normalize input to lowercase for case-insensitive matching.
        text = task_text.lower()  # Line 72:  "Store" and "store" should both match — normalization prevents missed delegations.
        # Line 73:  Check for math-domain keywords first (order matters if a word appears in multiple lists).
        math_keywords = ["add", "subtract", "multiply", "sum", "difference", "product"]  # Line 74:  These words strongly indicate a mathematical operation is requested.
        # Line 75:  If any math keyword is present, classify as "math" domain.
        if any(kw in text for kw in math_keywords):  # Line 76:  Using `any()` short-circuits on first match — efficient for small keyword lists.
            # Line 77:  Return the domain tag that the dispatcher's _domain_map will recognize.
            return "math"  # Line 78:  (blank line)
        # Line 79:  Check for memory-domain keywords.
        memory_keywords = ["store", "recall", "remember", "forget", "list", "save", "retrieve"]  # Line 80:  These words indicate the user wants to interact with persistent state.
        # Line 81:  If any memory keyword is present, classify as "memory" domain.
        if any(kw in text for kw in memory_keywords):  # Line 82:  Same short-circuit pattern as above.
            # Line 83:  Return the memory domain tag.
            return "memory"  # Line 84:  (blank line)
        # Line 85:  No known keywords matched — we can't determine the domain.
        return None  # Line 86:  The receiving agent will handle this as an unknown/unsupported request.
```

---

### `Harness/simulated_lm.py`

```python
# Line 1:  Import re module for regex-based number extraction from task text.
import re  # Line 2:  (blank line)


class SimulatedLM:  # Line 4:  A fake "brain" that uses keyword rules instead of neural networks to decide actions.
    """Simulates an LLM's decision-making using deterministic keyword matching.

    Analogy: A very literal robot butler. You say "add 2 and 3" and it mechanically
    calls the add tool. You say "store my name" and it says 'I don't do that,
    ask the memory person.' It has no creativity — just if/elif rules.

    The KEY INSIGHT: This class is swappable. Replace it with a real LLM API call
    (same interface: generate(task, context) → action_string) and the entire
    agent infrastructure works unchanged. That's the point of Module #0.
    """

    def __init__(self, domain: str):  # Line 16:  Each LM instance knows its own domain so it can decide when to delegate.
        # Line 17:  Store the domain this agent specializes in ("math" or "memory").
        self.domain = domain  # Line 18:  Used in _should_delegate() to check if a task is out-of-domain.

    def generate(self, task: str, context: dict) -> str:  # Line 20:  Main entry point — given a task and context, return an action instruction string.
        """Produce an action string that the agent loop will parse and execute.

        Output format (one of):
          TOOL: <name> | ARGS: {json}    → execute a tool
          DELEGATE: <agent_id>           → forward to another agent
          RESPONSE: <text>               → final answer to return to user
        """
        # Line 29:  Normalize the task text for matching.
        text = task.lower().strip()  # Line 30:  Remove whitespace and lowercase so "Add 5 and 3" matches "add".
        # Line 31:  If this task is outside our domain, immediately delegate.
        if self._should_delegate(text):  # Line 32:  This check happens FIRST — we don't waste effort trying to handle what we can't.
            # Line 33:  Determine which agent should handle this (opposite of our domain for this 2-agent toy).
            target = "memory_agent" if self.domain == "math" else "math_agent"  # Line 34:  In a larger system, this would come from the dispatcher's domain map.
            # Line 35:  Return the delegation instruction in the format the agent loop expects to parse.
            return f"DELEGATE: {target}"  # Line 36:  The agent will extract "memory_agent" or "math_agent" from this string.
        # Line 37:  We're in-domain — now figure out which specific tool to call.
        action = self._match_tool(text)  # Line 38:  This returns a formatted TOOL instruction or None if no tool matches.
        # Line 39:  If a tool matched, return the tool-call instruction.
        if action is not None:  # Line 40:  Non-None means we found a specific tool to execute.
            # Line 41:  Return the formatted instruction for the agent to parse and execute.
            return action  # Line 42:  (blank line)
        # Line 43:  No tool matched — generate a polite refusal response.
        return f"RESPONSE: I ({self.domain}) don't understand that task. Try a {'math' if self.domain == 'memory' else 'memory'} command."  # Line 44:  The response tells the user what domain we handle so they can rephrase.

    def _should_delegate(self, text: str) -> bool:  # Line 46:  Check if the task text indicates an out-of-domain request.
        """Return True if the task clearly belongs to a different domain."""
        # Line 49:  Define keywords that signal each domain (same lists as dispatcher for consistency).
        math_keywords = ["add", "subtract", "multiply", "sum", "difference", "product"]  # Line 50:  Mathematical operation indicators.
        memory_keywords = ["store", "recall", "remember", "forget", "list", "save", "retrieve"]  # Line 51:  State-management operation indicators.
        # Line 52:  If we're the math agent and the text has memory keywords, delegate.
        if self.domain == "math" and any(kw in text for kw in memory_keywords):  # Line 53:  Cross-domain detection — this is the trigger for multi-agent coordination.
            # Line 54:  Signal that delegation is needed.
            return True  # Line 55:  (blank line)
        # Line 56:  If we're the memory agent and the text has math keywords, delegate.
        if self.domain == "memory" and any(kw in text for kw in math_keywords):  # Line 57:  Symmetric check — either agent can delegate to the other.
            # Line 58:  Signal that delegation is needed.
            return True  # Line 59:  (blank line)
        # Line 60:  Task is in our domain (or ambiguous) — handle it ourselves.
        return False  # Line 61:  (blank line)

    def _match_tool(self, text: str) -> "str | None":  # Line 63:  Try to match the task text to a specific tool call within our domain.
        """Return a formatted TOOL instruction string, or None if no tool matches."""
        # Line 66:  Extract all numbers from the text (handles integers and simple floats).
        numbers = re.findall(r"-?\d+\.?\d*", text)  # Line 67:  Regex captures optional negative sign, digits, optional decimal point + digits.
        # Line 68:  If we're the math agent, check for math operations.
        if self.domain == "math":  # Line 69:  Branch into math-specific tool matching.
            # Line 70:  Check for addition (most common — check first).
            if "add" in text or "sum" in text:  # Line 71:  Both "add 5 and 3" and "what is the sum of 5 and 3" should trigger add.
                # Line 72:  We need at least 2 numbers for a binary operation.
                if len(numbers) >= 2:  # Line 73:  Guard against "add something" with no numbers — would crash the tool.
                    # Line 74:  Convert string numbers to floats for the tool (tools expect numeric args).
                    a, b = float(numbers[0]), float(numbers[1])  # Line 75:  Take the first two numbers found in the text.
                    # Line 76:  Return the formatted instruction with JSON-encoded arguments.
                    return f'TOOL: add | ARGS: {{"a": {a}, "b": {b}}}'  # Line 77:  The agent loop will json.loads() the ARGS portion to get a dict.
            # Line 78:  Check for subtraction.
            if "subtract" in text or "difference" in text:  # Line 79:  "subtract 10 from 20" or "what is the difference between 20 and 10".
                # Line 80:  Same guard — need two numbers.
                if len(numbers) >= 2:  # Line 81:  (blank line)
                    # Line 82:  Convert to floats.
                    a, b = float(numbers[0]), float(numbers[1])  # Line 83:  (blank line)
                    # Line 84:  Return subtraction instruction.
                    return f'TOOL: subtract | ARGS: {{"a": {a}, "b": {b}}}'  # Line 85:  (blank line)
            # Line 86:  Check for multiplication.
            if "multiply" in text or "product" in text:  # Line 87:  "multiply 4 by 5" or "what is the product of 4 and 5".
                # Line 88:  Need two numbers.
                if len(numbers) >= 2:  # Line 89:  (blank line)
                    # Line 90:  Convert to floats.
                    a, b = float(numbers[0]), float(numbers[1])  # Line 91:  (blank line)
                    # Line 92:  Return multiplication instruction.
                    return f'TOOL: multiply | ARGS: {{"a": {a}, "b": {b}}}'  # Line 93:  (blank line)
            # Line 94:  No math tool matched — fall through to None.
            return None  # Line 95:  (blank line)
        # Line 96:  If we're the memory agent, check for memory operations.
        if self.domain == "memory":  # Line 97:  Branch into memory-specific tool matching.
            # Line 98:  Check for store/save operation.
            if "store" in text or "save" in text or "remember" in text:  # Line 99:  Multiple synonyms for the same operation.
                # Line 100:  Try to extract a key-value pair from the text.
                kv = self._extract_key_value(text)  # Line 101:  This parses patterns like "store X as Y" or "save X under Y".
                # Line 102:  If we found a valid key-value pair, create the tool instruction.
                if kv is not None:  # Line 103:  Non-None means we successfully parsed both key and value.
                    # Line 104:  Unpack the tuple into named variables for clarity.
                    key, value = kv  # Line 105:  (blank line)
                    # Line 106:  Return the store instruction with JSON args.
                    return f'TOOL: memory_store | ARGS: {{"key": "{key}", "value": "{value}"}}'  # Line 107:  Values are stringified — the memory tool stores them as-is.
                # Line 108:  Couldn't parse key-value but keyword matched — use a default pattern.
                return 'TOOL: memory_store | ARGS: {"key": "default", "value": "' + text.replace('"', '\\"') + '"}'  # Line 109:  Fallback: store the entire task text as the value under key "default".
            # Line 110:  Check for recall/retrieve operation.
            if "recall" in text or "retrieve" in text:  # Line 111:  User wants to read back a previously stored value.
                # Line 112:  Try to extract the key they want to recall.
                key = self._extract_key(text)  # Line 113:  Parses "recall X" → key = "X".
                # Line 114:  If we found a key, create the recall instruction.
                if key is not None:  # Line 115:  (blank line)
                    # Line 116:  Return the recall instruction.
                    return f'TOOL: memory_recall | ARGS: {{"key": "{key}"}}'  # Line 117:  (blank line)
                # Line 118:  No specific key found — default to "default" key.
                return 'TOOL: memory_recall | ARGS: {"key": "default"}'  # Line 119:  (blank line)
            # Line 120:  Check for list operation.
            if "list" in text:  # Line 121:  User wants to see all stored keys.
                # Line 122:  List takes no arguments — return an empty args object.
                return 'TOOL: memory_list | ARGS: {}'  # Line 123:  (blank line)
            # Line 124:  No memory tool matched.
            return None  # Line 125:  (blank line)
        # Line 126:  Unknown domain — should never reach here if _should_delegate worked correctly.
        return None  # Line 127:  Safety net to prevent crashes on unexpected domain values.

    def _extract_key_value(self, text: str) -> "tuple | None":  # Line 129:  Parse "store X as Y" or "save X under Y" patterns into (key, value).
        """Extract a key-value pair from natural language store commands."""
        # Line 132:  Try pattern: "store <value> as <key>" (most common phrasing).
        m = re.search(r'(?:store|save|remember)\s+(.+?)\s+(?:as|under)\s+(.+)', text)  # Line 133:  Non-greedy (.+?) ensures we capture the shortest match between keywords.
        # Line 134:  If the pattern matched, extract and return the groups.
        if m:  # Line 135:  (blank line)
            # Line 136:  Return (key=group2, value=group1) — note the order swap!
            return (m.group(2).strip(), m.group(1).strip())  # Line 137:  "store hello as greeting" → key="greeting", value="hello".
        # Line 138:  Try alternate pattern: "<key> = <value>" or "key: value".
        m2 = re.search(r'(\w+)\s*[=:]\s*(.+)', text)  # Line 139:  Catches programming-style assignments like "name = Alice".
        # Line 140:  If this pattern matched, return the groups in (key, value) order.
        if m2:  # Line 141:  (blank line)
            # Line 142:  Return with key first, value second (no swap needed here).
            return (m2.group(1).strip(), m2.group(2).strip())  # Line 143:  (blank line)
        # Line 144:  No pattern matched — we can't reliably extract key and value.
        return None  # Line 145:  Caller will use a fallback strategy.

    def _extract_key(self, text: str) -> "str | None":  # Line 147:  Extract just the key from a recall command like "recall greeting".
        """Extract the key name from a recall/retrieve command."""
        # Line 150:  Pattern: "recall <key>" or "retrieve <key>".
        m = re.search(r'(?:recall|retrieve)\s+(.+)', text)  # Line 151:  Greedy match to capture everything after the verb as the key.
        # Line 152:  If matched, return the captured key string.
        if m:  # Line 153:  (blank line)
            # Line 154:  Strip whitespace and return the key.
            return m.group(1).strip()  # Line 155:  (blank line)
        # Line 156:  No key found in the text.
        return None  # Line 157:  Caller will use a default key.
```

---

### `Harness/guardrails.py`

```python
# Line 1:  Import re for pattern-based input validation (detecting injection attempts).
import re  # Line 2:  (blank line)


class Guardrails:  # Line 4:  Safety checks that run BEFORE any task reaches the LM or tools.
    """Validates inputs and enforces limits to prevent abuse or crashes.

    Analogy: Airport security. Every passenger (task) goes through screening
    before boarding. Oversized luggage (too-long inputs), forbidden items
    (injection patterns), and too many carry-ons (iteration cap) are all caught here.

    Design principle: Fail closed. If we can't validate, we reject. It's better
    to refuse a task than to process something dangerous.
    """

    def __init__(self, max_iterations: int = 10, max_input_length: int = 500):  # Line 15:  Configure the limits that define "safe" behavior.
        # Line 16:  Maximum number of loop iterations before we force-stop (prevents infinite loops).
        self.max_iterations = max_iterations  # Line 17:  In practice, a task needing >10 iterations is likely stuck in a cycle.
        # Line 18:  Maximum character length for any single input string.
        self.max_input_length = max_input_length  # Line 19:  Prevents memory exhaustion from gigabyte-sized inputs.
        # Line 20:  Patterns that indicate potential injection or malicious intent.
        self._forbidden_patterns = [  # Line 21:  List of regex patterns — any match means the input is BLOCKED.
            r"__import__",  # Line 22:  Python dynamic import — classic code injection vector.
            r"os\.system",  # Line 23:  Shell command execution — never allowed in agent inputs.
            r"eval\(",  # Line 24:  Dynamic code evaluation — same risk as exec.
            r"exec\(",  # Line 25:  Execute arbitrary string as Python code.
            r"<script",  # Line 26:  HTML/JS injection if output is ever rendered in a browser.
            r";\s*DROP\s+TABLE",  # Line 27:  SQL injection pattern (defensive, even though we don't use SQL).
        ]  # Line 28:  Close the list. Add new patterns here as threats are identified.

    def validate_input(self, text: str) -> tuple:  # Line 30:  Check an input string against all guardrail rules.
        """Returns (is_valid: bool, reason: str). If invalid, reason explains why."""
        # Line 33:  First check: is the input even a string? (Defensive — could be None or int from bad code.)
        if not isinstance(text, str):  # Line 34:  Non-string inputs are always rejected — we don't know how to validate them.
            # Line 35:  Return failure with a clear reason for debugging.
            return (False, f"Input is not a string (got {type(text).__name__})")  # Line 36:  Type name helps the developer identify where the bad data came from.
        # Line 37:  Second check: length limit.
        if len(text) > self.max_input_length:  # Line 38:  Inputs longer than the cap are almost certainly accidental or malicious.
            # Line 39:  Return failure with the actual vs. allowed length for context.
            return (False, f"Input too long: {len(text)} chars (max {self.max_input_length})")  # Line 40:  Showing both numbers makes it easy to tune the limit if needed.
        # Line 41:  Third check: empty or whitespace-only input.
        if not text.strip():  # Line 42:  An empty string has no semantic content — processing it would waste a loop iteration.
            # Line 43:  Return failure for empty input.
            return (False, "Input is empty or whitespace-only")  # Line 44:  (blank line)
        # Line 45:  Fourth check: scan for forbidden patterns (injection attempts).
        for pattern in self._forbidden_patterns:  # Line 46:  Check each dangerous pattern against the input.
            # Line 47:  Use re.search with IGNORECASE so "OS.SYSTEM" is caught too.
            if re.search(pattern, text, re.IGNORECASE):  # Line 48:  If any forbidden pattern matches, this input is BLOCKED immediately.
                # Line 49:  Return failure identifying which pattern triggered the block.
                return (False, f"Forbidden pattern detected: {pattern}")  # Line 50:  Showing the pattern helps developers understand what was flagged.
        # Line 51:  All checks passed — the input is safe to process.
        return (True, "OK")  # Line 52:  "OK" is a conventional success marker that's easy to grep in logs.

    def check_iteration(self, current: int) -> bool:  # Line 54:  Check whether we've exceeded the maximum allowed loop iterations.
        """Returns True if we should STOP (limit reached), False if we can continue."""
        # Line 57:  If current iteration count meets or exceeds the cap, we must stop.
        return current >= self.max_iterations  # Line 58:  Using >= (not >) means the agent gets exactly max_iterations chances, not max+1.
```

---

### `Harness/agent.py`

```python
# Line 1:  Import threading so each agent can run its loop in a separate thread.
import threading  # Line 2:  Import time for sleep calls during polling (prevents busy-waiting).
import time  # Line 3:  Import json to parse tool arguments from the LM's output string.
import json  # Line 4:  Import typing for type hints.
from typing import Dict, Callable, Optional  # Line 5:  (blank line)

# Line 7:  Import all Harness components that the agent depends on.
from Harness.envelope import MessageEnvelope  # Line 8:  The message format the agent sends and receives.
from Harness.message_bus import MessageBus  # Line 9:  The communication channel the agent polls and publishes to.
from Harness.dispatcher import Dispatcher  # Line 10:  Routes delegation when the LM says "DELEGATE: ...".
from Harness.simulated_lm import SimulatedLM  # Line 11:  The "brain" that decides what action to take.
from Harness.guardrails import Guardrails  # Line 12:  Safety checks before processing any message.
from Harness.trace_logger import TraceLogger  # Line 13:  Colored execution trace for observability.


class Agent:  # Line 15:  A single autonomous entity that processes tasks, calls tools, and delegates when needed.
    """An agent with a domain, a brain (LM), tools, and a connection to the bus.

    Analogy: A specialist doctor in a hospital. They handle their specialty
    (domain) directly. When a patient needs a different specialist, they write
    a referral (delegation message) and send it through the hospital switchboard
    (message bus). The patient doesn't need to know which rooms exist.

    Lifecycle: start() → [poll inbox → validate → think → act → respond]* → stop()
    """

    def __init__(self, agent_id: str, domain: str, tools: Dict[str, Callable],  # Line 27:  Constructor takes all dependencies explicitly (dependency injection — no hidden globals).
                 bus: MessageBus, dispatcher: Dispatcher):  # Line 28:  Bus and dispatcher are shared across agents (single instance each).
        # Line 29:  Store the unique identifier for this agent (used in messages and logs).
        self.agent_id = agent_id  # Line 30:  This string appears in every envelope this agent sends or receives.
        # Line 31:  Store the domain this agent specializes in.
        self.domain = domain  # Line 32:  Passed to SimulatedLM so it knows when to delegate.
        # Line 33:  Create the simulated brain for this agent, configured with its domain.
        self.lm = SimulatedLM(domain)  # Line 34:  Each agent gets its own LM instance — they make independent decisions.
        # Line 35:  Store the tool registry — maps tool names to callable functions.
        self.tools = tools  # Line 36:  Tools are plain Python functions; the agent doesn't care how they're implemented.
        # Line 37:  Bind to the shared message bus for sending and receiving messages.
        self.bus = bus  # Line 38:  All inter-agent communication goes through this single bus instance.
        # Line 39:  Bind to the shared dispatcher for routing delegation messages.
        self.dispatcher = dispatcher  # Line 40:  The agent asks the dispatcher "who handles this?" rather than hardcoding recipient IDs.
        # Line 41:  Create guardrails with default limits (can be overridden per-agent if needed).
        self.guardrails = Guardrails()  # Line 42:  Each agent validates its own inputs independently.
        # Line 43:  Create a trace logger for this agent (color-coded by agent_id).
        self.trace = TraceLogger(agent_id)  # Line 44:  The trace logger records every step for post-hoc analysis and the final report.
        # Line 45:  Flag to control the run loop — set to False to stop the agent thread.
        self._running = False  # Line 46:  Initially False; start() flips it to True.
        # Line 47:  Reference to the thread that runs this agent's loop (None until started).
        self._thread: Optional[threading.Thread] = None  # Line 48:  Storing the reference lets us call .join() on stop() for clean shutdown.
        # Line 49:  Counter for how many messages this agent has processed (for metrics).
        self.messages_processed: int = 0  # Line 50:  Incremented after each successful handle_message() call.

    def start(self) -> None:  # Line 52:  Launch the agent's run loop in a new thread. Non-blocking — returns immediately.
        """Start the agent's event loop in a background thread."""
        # Line 55:  Set the running flag to True so the loop knows to keep going.
        self._running = True  # Line 56:  This is checked at the top of each loop iteration for graceful shutdown.
        # Line 57:  Create a new thread targeting our _run_loop method.
        self._thread = threading.Thread(target=self._run_loop, name=f"agent-{self.agent_id}")  # Line 58:  Naming the thread makes it identifiable in debugging tools and crash dumps.
        # Line 59:  Set daemon=True so the thread dies automatically when the main program exits.
        self._thread.daemon = True  # Line 60:  Without this, a stuck agent thread would prevent Python from exiting cleanly.
        # Line 61:  Actually start the thread — it begins executing _run_loop() in parallel.
        self._thread.start()  # Line 62:  After this line, the agent is "alive" and polling its inbox.
        # Line 63:  Log that the agent has started (visible in trace output).
        self.trace.log("loop", f"Agent '{self.agent_id}' started (domain={self.domain})")  # Line 64:  The "loop" component tag means this is a lifecycle event, not a message event.

    def stop(self) -> None:  # Line 66:  Signal the agent to stop and wait for its thread to finish.
        """Gracefully stop the agent's run loop."""
        # Line 69:  Flip the running flag — the loop will exit on its next iteration.
        self._running = False  # Line 70:  This is a cooperative shutdown — we don't kill the thread, we ask it to stop.
        # Line 71:  If a thread exists, wait for it to finish (with a timeout to prevent hanging).
        if self._thread is not None:  # Line 72:  Guard against calling stop() before start().
            # Line 73:  Block until the thread finishes or 2 seconds pass (whichever comes first).
            self._thread.join(timeout=2.0)  # Line 74:  The timeout prevents a stuck agent from blocking program shutdown indefinitely.
        # Line 75:  Log that the agent has stopped.
        self.trace.log("loop", f"Agent '{self.agent_id}' stopped (processed {self.messages_processed} messages)")  # Line 76:  Including the count gives a quick health summary in the trace report.

    def _run_loop(self) -> None:  # Line 78:  The main event loop — runs forever until _running is set to False.
        """Continuously poll the inbox, process messages, and send responses."""
        # Line 81:  Loop while the agent should be running (checked each iteration for responsive shutdown).
        while self._running:  # Line 82:  This is the "heart" of the agent — it beats as long as _running is True.
            # Line 83:  Poll the bus for a message addressed to this agent (waits up to 0.5s).
            envelope = self.bus.poll(self.agent_id, timeout=0.5)  # Line 84:  The 0.5s timeout means we check _running at least twice per second (responsive shutdown).
            # Line 85:  If no message arrived within the timeout, just loop back and check _running again.
            if envelope is None:  # Line 86:  No work right now — sleep is implicit in the poll timeout.
                # Line 87:  Continue to next iteration (re-check _running flag).
                continue  # Line 88:  This is NOT a busy-wait — poll() already blocked for 0.5s.
            # Line 89:  We have a message to process — handle it.
            self.handle_message(envelope)  # Line 90:  All the real work happens inside this method.

    def handle_message(self, envelope: MessageEnvelope) -> None:  # Line 92:  Process a single incoming message end-to-end.
        """Validate, think, act, and respond to a single message."""
        # Line 95:  Log that we received a message (for trace visibility).
        self.trace.log("loop", f"Received: {envelope}")  # Line 96:  The __str__ of envelope gives a compact one-line summary.
        # Line 97:  Extract the task text from the payload (the actual content to process).
        task = envelope.payload.get("task", "")  # Line 98:  .get() with default "" prevents KeyError if payload is malformed.
        # Line 99:  Run guardrail validation on the task before doing anything else.
        valid, reason = self.guardrails.validate_input(task)  # Line 100:  This is the FIRST thing we do with any external input — security first.
        # Line 101:  If the input failed validation, reject it immediately.
        if not valid:  # Line 102:  Guardrails said NO — we must not process this task.
            # Line 103:  Log the rejection with the reason (important for debugging).
            self.trace.log("guardrails", f"BLOCKED: {reason}", level="error")  # Level "error" makes this stand out in colored output.
            # Line 104:  Send an error response back to whoever sent the message.
            self._send_response(envelope, f"ERROR: Input rejected — {reason}")  # Line 105:  The sender needs to know their task was rejected and why.
            # Line 106:  Return early — no further processing of an invalid input.
            return  # Line 107:  (blank line)
        # Line 108:  Input is valid — ask the LM (brain) what to do.
        context = {"agent_id": self.agent_id, "domain": self.domain}  # Line 109:  Provide minimal context so the LM knows who it's talking to.
        # Line 110:  Call the LM to get an action instruction (TOOL / DELEGATE / RESPONSE).
        action = self.lm.generate(task, context)  # Line 111:  This is the "think" step — in production this would be an API call to a real LLM.
        # Line 112:  Log what the LM decided (critical for debugging agent behavior).
        self.trace.log("lm", f"Decision: {action}")  # Line 113:  Seeing the raw LM output helps identify when the "brain" makes a wrong choice.
        # Line 114:  Parse the action string and execute the appropriate branch.
        if action.startswith("TOOL:"):  # Line 115:  The LM wants us to call one of our tools.
            # Line 116:  Execute the tool and send the result back.
            self._execute_tool(envelope, action)  # Line 117:  (blank line)
        elif action.startswith("DELEGATE:"):  # Line 118:  The LM says this task belongs to another agent.
            # Line 119:  Forward the task to the appropriate agent via the bus.
            self._delegate(envelope, action)  # Line 120:  (blank line)
        elif action.startswith("RESPONSE:"):  # Line 121:  The LM has a direct answer (or a polite refusal).
            # Line 122:  Extract the response text after "RESPONSE: ".
            response_text = action[len("RESPONSE: "):]  # Line 123:  String slicing to remove the prefix and get just the message.
            # Line 124:  Send the response back to the sender.
            self._send_response(envelope, response_text)  # Line 125:  (blank line)
        else:  # Line 126:  Unrecognized action format — treat as an error.
            # Line 127:  Log a warning about the malformed LM output.
            self.trace.log("lm", f"WARNING: Unrecognized action format: {action}", level="warn")  # Line 128:  This shouldn't happen with our SimulatedLM but could with a real LLM.
            # Line 129:  Send an error response so the sender isn't left hanging.
            self._send_response(envelope, "ERROR: Agent produced unrecognized action.")  # Line 130:  (blank line)
        # Line 131:  Increment our processed counter for metrics.
        self.messages_processed += 1  # Line 132:  Only count successfully handled messages (not rejected ones).

    def _execute_tool(self, envelope: MessageEnvelope, action: str) -> None:  # Line 134:  Parse a TOOL instruction and execute the named tool.
        """Parse 'TOOL: name | ARGS: {json}' and call the tool with the arguments."""
        # Line 137:  Split the action string on " | ARGS: " to separate tool name from arguments.
        parts = action.split(" | ARGS: ", 1)  # maxsplit=1 ensures we only split once (args JSON might contain pipes).
        # Line 138:  If the format is malformed (missing " | ARGS: "), log and error out.
        if len(parts) != 2:  # Line 139:  Malformed action — can't extract both name and args.
            # Line 140:  Log the problem for debugging.
            self.trace.log("tools", f"Malformed tool action: {action}", level="error")  # Line 141:  (blank line)
            # Line 142:  Send an error response to the sender.
            self._send_response(envelope, "ERROR: Malformed tool instruction from LM.")  # Line 143:  (blank line)
            # Line 144:  Return without executing anything.
            return  # Line 145:  (blank line)
        # Line 146:  Extract the tool name (first part, after "TOOL: ").
        tool_name = parts[0].replace("TOOL: ", "").strip()  # Line 147:  Remove the prefix and any extra whitespace.
        # Line 148:  Parse the JSON arguments string into a dictionary.
        try:  # Line 149:  Wrap in try/except because json.loads can raise on malformed JSON.
            # Line 150:  Convert the JSON string to a Python dict.
            args = json.loads(parts[1])  # Line 151:  This is where the LM's "structured output" becomes usable data.
        except json.JSONDecodeError as e:  # Line 152:  If the JSON is broken, we can't call the tool with bad args.
            # Line 153:  Log the parse error with details.
            self.trace.log("tools", f"JSON parse error in tool args: {e}", level="error")  # Line 154:  (blank line)
            # Line 155:  Send an error response explaining what went wrong.
            self._send_response(envelope, f"ERROR: Could not parse tool arguments: {e}")  # Line 156:  (blank line)
            # Line 157:  Return without executing.
            return  # Line 158:  (blank line)
        # Line 159:  Look up the tool in our registry by name.
        tool_fn = self.tools.get(tool_name)  # Line 160:  .get() returns None if the tool doesn't exist (rather than raising KeyError).
        # Line 161:  If the tool isn't registered, we can't execute it.
        if tool_fn is None:  # Line 162:  This catches typos in tool names or tools that weren't registered at startup.
            # Line 163:  Log which tool was requested but not found.
            self.trace.log("tools", f"Tool '{tool_name}' not found in registry. Available: {list(self.tools.keys())}", level="error")  # Line 164:  Listing available tools helps the developer spot the mismatch.
            # Line 165:  Send an error response to the sender.
            self._send_response(envelope, f"ERROR: Tool '{tool_name}' does not exist.")  # Line 166:  (blank line)
            # Line 167:  Return without executing.
            return  # Line 168:  (blank line)
        # Line 169:  Tool found — execute it with the parsed arguments.
        try:  # Line 170:  Wrap in try/except because tools can fail (div by zero, bad data, etc.).
            # Line 171:  Call the tool function with keyword arguments from the parsed JSON.
            result = tool_fn(**args)  # Line 172:  **args unpacks the dict into keyword arguments (e.g., {"a":5,"b":3} → a=5, b=3).
            # Line 173:  Log the successful tool execution with its result.
            self.trace.log("tools", f"Executed '{tool_name}'({args}) → {result}")  # Line 174:  Showing both input and output makes the trace self-documenting.
            # Line 175:  Send the result back to the sender as a response.
            self._send_response(envelope, str(result))  # Line 176:  Convert result to string since envelope payloads are text-based.
        except Exception as e:  # Line 177:  Catch any exception from the tool — we must never crash the agent loop.
            # Line 178:  Log the tool failure with the exception details.
            self.trace.log("tools", f"Tool '{tool_name}' raised: {type(e).__name__}: {e}", level="error")  # Line 179:  Including the exception type helps distinguish bugs from expected failures.
            # Line 180:  Send an error response so the sender knows the tool failed.
            self._send_response(envelope, f"ERROR: Tool '{tool_name}' failed: {e}")  # Line 181:  The agent survives — only this one task fails.

    def _delegate(self, envelope: MessageEnvelope, action: str) -> None:  # Line 183:  Parse a DELEGATE instruction and forward the task to another agent.
        """Parse 'DELEGATE: agent_id' and publish a delegation message to that agent."""
        # Line 186:  Extract the target agent ID from the action string.
        target_agent = action.replace("DELEGATE: ", "").strip()  # Line 187:  Remove the prefix to get just the agent ID (e.g., "memory_agent").
        # Line 188:  Log that we're delegating and to whom.
        self.trace.log("loop", f"Delegating to '{target_agent}': {envelope.payload.get('task', '')[:50]}")  # Line 189:  Truncate task text to 50 chars to keep trace lines readable.
        # Line 190:  Create a new envelope for the delegation (different from the original — it's a NEW message).
        delegation_envelope = MessageEnvelope(  # Line 191:  This is a fresh message, not a forward of the original.
            sender_id=self.agent_id,  # Line 192:  We are the sender of this delegation (the target needs to know who to respond to).
            recipient_id=target_agent,  # Line 193:  The agent that should handle this task.
            subject="delegation",  # Line 194:  Tag it as a delegation so the receiving agent can log it differently.
            payload={"task": envelope.payload.get("task", ""), "original_sender": envelope.sender_id},  # Line 195:  Carry forward the task AND who originally asked (for multi-hop response routing).
            reply_to=envelope.message_id,  # Line 196:  Link this delegation to the original message for correlation in traces.
        )  # Line 197:  Close the constructor.
        # Line 198:  Publish the delegation to the bus — this is the non-blocking act.
        self.bus.publish(delegation_envelope)  # Line 199:  After this, the target agent will pick it up on its next poll cycle.
        # Line 200:  NOTE: We do NOT wait for a response here. The response will arrive
        #   as a separate message in our inbox, which we'll process on a future loop iteration.
        #   This is the key insight: delegation is fire-and-forget at the message level.
        pass  # Line 203:  No further action needed — the bus handles delivery.

    def _send_response(self, original_envelope: MessageEnvelope, response_text: str) -> None:  # Line 205:  Create and publish a response message back to the sender of the original message.
        """Send a response envelope back to whoever sent us the original message."""
        # Line 208:  Determine who to send the response to (the original sender, not the bus).
        recipient = original_envelope.sender_id  # Line 209:  We always respond to the person who asked us, not to ourselves.
        # Line 210:  Create the response envelope.
        response_envelope = MessageEnvelope(  # Line 211:  A new message object — responses are separate from requests.
            sender_id=self.agent_id,  # Line 212:  We are the responder.
            recipient_id=recipient,  # Line 213:  Send back to whoever originally messaged us.
            subject="response",  # Line 214:  Tag as "response" so the receiving agent knows this is an answer, not a new task.
            payload={"result": response_text, "in_reply_to": original_envelope.message_id},  # Line 215:  Include both the result text and a reference to the original message for correlation.
            reply_to=original_envelope.message_id,  # Line 216:  Set the reply_to field for trace correlation.
        )  # Line 217:  Close the constructor.
        # Line 218:  Log that we're sending a response (with a preview of the content).
        self.trace.log("loop", f"Responding to '{recipient}': {response_text[:60]}")  # Line 219:  Truncate long responses for trace readability.
        # Line 220:  Publish the response to the bus.
        self.bus.publish(response_envelope)  # Line 221:  The recipient will see this on their next poll cycle.

    def send_task(self, task_text: str) -> MessageEnvelope:  # Line 223:  External entry point — submit a task to this agent (used by main.py and tests).
        """Create an initial task envelope and publish it to this agent's own inbox.

        This simulates a user sending a message directly to the agent.
        In production, this might be an HTTP endpoint or CLI prompt.
        """
        # Line 230:  Create an envelope as if a "user" sent it to this agent.
        envelope = MessageEnvelope(  # Line 231:  The sender is "user" to distinguish external input from inter-agent messages.
            sender_id="user",  # Line 232:  Using "user" makes it clear in traces that this originated externally.
            recipient_id=self.agent_id,  # Line 233:  Deliver to ourselves (we'll pick it up on our next poll).
            subject="task",  # Line 234:  Tag as "task" — the initial request from a user.
            payload={"task": task_text},  # Line 235:  The actual task text goes in the payload.
        )  # Line 236:  Close the constructor.
        # Line 237:  Publish to our own inbox — we'll process it on the next loop iteration.
        self.bus.publish(envelope)  # Line 238:  This is non-blocking; the task will be handled asynchronously by our thread.
        # Line 239:  Return the envelope so the caller can track its message_id for correlation.
        return envelope  # Line 240:  The caller (main.py) uses this to know which response to wait for.
```

---

### `Harness/trace_logger.py`

```python
# Line 1:  Import time for timestamping trace entries.
import time  # Line 2:  Import typing for the log entry list type hint.
from typing import List, Tuple  # Line 3:  (blank line)

# Line 5:  ─── ANSI Color Codes (no external packages needed) ───────────────────────
# Line 6:  These are escape sequences that terminal emulators interpret as color instructions.
RESET = "\033[0m"  # Line 8:  Resets all formatting back to default — always append after colored text.
BOLD = "\033[1m"  # Line 9:  Makes text bold for emphasis (used on headers).
# Line 10:  Foreground colors for component labels.
RED = "\033[91m"  # Line 11:  Bright red — used for guardrails and errors (danger/safety).
GREEN = "\033[92m"  # Line 12:  Bright green — used for loop lifecycle events (healthy operation).
YELLOW = "\033[93m"  # Line 13:  Bright yellow — used for tool execution (action being taken).
BLUE = "\033[94m"  # Line 14:  Bright blue — used for agent A (math_agent) identification.
MAGENTA = "\033[95m"  # Line 15:  Bright magenta — used for agent B (memory_agent) identification.
CYAN = "\033[96m"  # Line 16:  Bright cyan — used for LM decisions and bus events (information flow).
WHITE = "\033[97m"  # Line 17:  Bright white — used for dispatcher events (routing decisions).
# Line 18:  Background colors for status indicators.
BG_GREEN = "\033[42;30m"  # Line 19:  Green background + black text — used for "valid=True" / success states.
BG_RED = "\033[41;97m"  # Line 20:  Red background + white text — used for "BLOCKED" / failure states.
BG_YELLOW = "\033[43;30m"  # Line 21:  Yellow background + black text — used for warnings and errors.


class TraceLogger:  # Line 24:  Records every significant event during agent execution with color-coded output.
    """A colored execution trace that makes agent behavior visible and debuggable.

    Analogy: A flight recorder (black box). It records everything that happened
    so you can replay it after the fact. The colors let you quickly spot problems
    (red = blocked, yellow = tool action, green = healthy loop) without reading
    every line in detail.
    """

    # Line 33:  Map component names to their ANSI color codes for consistent coloring.
    COMPONENT_COLORS = {  # Line 34:  Central registry — add new components here and they get automatic coloring.
        "loop": GREEN,  # Line 35:  Loop events (start/stop/receive/respond) are green = healthy operation.
        "lm": CYAN,  # Line 36:  LM decisions are cyan = "thinking" / information processing.
        "tools": YELLOW,  # Line 37:  Tool executions are yellow = action being performed on the outside world.
        "guardrails": RED,  # Line 38:  Guardrail events are red = safety/security boundary.
        "bus": CYAN,  # Line 39:  Bus events share cyan with LM (both are about message flow).
        "dispatcher": WHITE,  # Line 40:  Dispatcher events are white = neutral routing decisions.
    }  # Line 41:  Close the color map.

    def __init__(self, agent_id: str):  # Line 43:  Create a trace logger for a specific agent.
        # Line 44:  Store the agent ID so we can color-code by agent in multi-agent scenarios.
        self.agent_id = agent_id  # Line 45:  Used to select the right agent color (blue for math, magenta for memory).
        # Line 46:  List of all log entries as (timestamp, component, message, level) tuples.
        self.entries: List[Tuple[float, str, str, str]] = []  # Line 47:  Stored in memory for the report() method; also printed live.
        # Line 48:  Determine the color for this agent's name based on its ID.
        self._agent_color = BLUE if "math" in agent_id else MAGENTA  # Line 49:  Simple heuristic — contains "math" → blue, otherwise magenta.

    def log(self, component: str, message: str, level: str = "info") -> None:  # Line 51:  Record and print a single trace entry.
        """Log a colored message tagged with a component name and severity level."""
        # Line 54:  Get the current time for timestamping (monotonic would be better for durations, but wall-clock is more readable).
        ts = time.time()  # Line 55:  Unix timestamp — in report() we'll show relative offsets from start.
        # Line 56:  Look up the color for this component (default to white if unknown).
        color = self.COMPONENT_COLORS.get(component, WHITE)  # Line 57:  .get() with default prevents KeyError on new/unexpected component names.
        # Line 58:  Determine the color for the level indicator.
        level_color = BG_RED if level == "error" else (BG_YELLOW if level == "warn" else "")  # Line 59:  Errors get red bg, warnings get yellow bg, info gets no special bg.
        # Line 60:  Build the colored output string.
        line = f"{color}[{component}] {self._agent_color}{self.agent_id}{RESET} | {message}"  # Line 61:  Format: [component] agent_id | message, each part in its own color.
        # Line 62:  If there's a level indicator (error/warn), prepend it with background color.
        if level_color:  # Line 63:  Only add the level badge for non-info messages.
            # Line 64:  Insert the colored level tag at the beginning of the message portion.
            line = f"{color}[{component}] {self._agent_color}{self.agent_id}{RESET} | {level_color}{level.upper()}{RESET} {message}"  # Line 65:  Rebuild with the level badge included.
        # Line 66:  Print the colored line to stdout (live output during execution).
        print(line)  # Line 67:  This gives real-time visibility — you see events as they happen.
        # Line 68:  Store the entry in memory for the final report().
        self.entries.append((ts, component, message, level))  # Line 69:  The stored version is plain (no ANSI codes) for programmatic analysis.

    def report(self) -> None:  # Line 71:  Print a summary report of all logged events after execution completes.
        """Display a formatted summary of the full execution trace."""
        # Line 74:  Print a header to visually separate the report from live output.
        print(f"\n{BOLD}{'='*60}")  # Line 75:  Bold separator line for visual clarity.
        # Line 76:  Print the report title with the agent ID.
        print(f"{BOLD}  TRACE REPORT — {self.agent_id}{RESET}")  # Line 77:  Identify which agent this report belongs to.
        # Line 78:  Print another separator.
        print(f"{BOLD}{'='*60}{RESET}\n")  # Line 79:  (blank line)
        # Line 80:  If there are no entries, say so and return.
        if not self.entries:  # Line 81:  Edge case: agent was created but never processed anything.
            # Line 82:  Print a message indicating no activity occurred.
            print("  (no events logged)")  # Line 83:  (blank line)
            # Line 84:  Return early — nothing to report.
            return  # Line 85:  (blank line)
        # Line 86:  Get the timestamp of the first entry as our reference point for relative times.
        start_time = self.entries[0][0]  # Line 87:  All subsequent times will be shown as "+X.XXs" from this moment.
        # Line 88:  Iterate through all entries and print them with relative timestamps.
        for ts, component, message, level in self.entries:  # Line 89:  Unpack each tuple for clean access to its fields.
            # Line 90:  Calculate how many seconds after the first event this occurred.
            offset = ts - start_time  # Line 91:  Relative time is more useful than absolute Unix timestamps for understanding flow.
            # Line 92:  Get the color for this component.
            color = self.COMPONENT_COLORS.get(component, WHITE)  # Line 93:  Same lookup as in log() — consistent coloring throughout.
            # Line 94:  Format and print the entry with its relative timestamp.
            print(f"  {color}[+{offset:.3f}s] [{component}] {message}{RESET}")  # Line 95:  Three decimal places gives millisecond precision without being noisy.
        # Line 96:  Print a summary line with total event count and any errors.
        error_count = sum(1 for e in self.entries if e[3] == "error")  # Line 97:  Count how many entries were at error level.
        # Line 98:  Print the summary with color coding (green if no errors, red if there were).
        summary_color = BG_GREEN if error_count == 0 else BG_RED  # Line 99:  At-a-glance health indicator.
        # Line 100:  Format and print the final summary line.
        print(f"\n  {summary_color}{len(self.entries)} events, {error_count} errors{RESET}")  # Line 101:  Quick stats for the developer to assess run health.
```

---

### `main.py`

```python
# Line 1:  Import sys and os for path setup (ensures Harness/ is importable regardless of CWD).
import sys, os  # Line 2:  Add the script's directory to sys.path so "from Harness..." works.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # Line 3:  This makes the module runnable from any working directory.

# Line 5:  Import time for sleep calls in the demo (giving agents time to process).
import time  # Line 6:  (blank line)

# Line 8:  Import all Harness components needed to wire up the system.
from Harness.message_bus import MessageBus  # Line 9:  The central communication hub.
from Harness.dispatcher import Dispatcher  # Line 10:  Routes tasks to the correct agent by domain.
from Harness.agent import Agent  # Line 11:  The autonomous entity that processes messages.
# Line 12:  (blank line)


def create_math_tools() -> dict:  # Line 14:  Factory function that creates and returns the math agent's tool registry.
    """Define the tools available to the math agent as plain Python functions."""
    # Line 17:  Define the add tool — takes two numbers, returns their sum.
    def add(a: float, b: float) -> float:  # Line 18:  Simple binary addition with type hints for clarity.
        # Line 19:  Return the arithmetic result.
        return a + b  # Line 20:  (blank line)
    # Line 21:  Define the subtract tool.
    def subtract(a: float, b: float) -> float:  # Line 22:  Returns a minus b (order matters: "subtract 3 from 10" means 10-3).
        # Line 23:  Return the arithmetic result.
        return a - b  # Line 24:  (blank line)
    # Line 25:  Define the multiply tool.
    def multiply(a: float, b: float) -> float:  # Line 26:  Returns the product of two numbers.
        # Line 27:  Return the arithmetic result.
        return a * b  # Line 28:  (blank line)
    # Line 29:  Return all tools as a name→function mapping for the agent's registry.
    return {"add": add, "subtract": subtract, "multiply": multiply}  # Line 30:  The keys must match what SimulatedLM outputs in its TOOL instructions.


def create_memory_tools() -> dict:  # Line 32:  Factory function that creates and returns the memory agent's tool registry.
    """Define the tools available to the memory agent (simple in-memory key-value store)."""
    # Line 35:  Create a shared dictionary that acts as our "database" for stored values.
    store = {}  # Line 36:  This dict persists for the lifetime of the program (like a real database).
    # Line 37:  (blank line)
    # Line 38:  Define the memory_store tool — saves a value under a key.
    def memory_store(key: str, value: str) -> str:  # Line 39:  Stores a string value under a string key in the shared dict.
        # Line 40:  Assign the value to the key in our in-memory store.
        store[key] = value  # Line 41:  This is the "write" operation — analogous to INSERT or SET in a real DB.
        # Line 42:  Return a confirmation message (the agent will relay this to the user).
        return f"Stored '{value}' under key '{key}'."  # Line 43:  Human-readable confirmation for the trace and user.
    # Line 44:  (blank line)
    # Line 45:  Define the memory_recall tool — retrieves a value by key.
    def memory_recall(key: str) -> str:  # Line 46:  Looks up a previously stored value by its key.
        # Line 47:  Check if the key exists in our store before trying to access it.
        if key in store:  # Line 48:  Avoids KeyError and gives a friendlier error message.
            # Line 49:  Return the stored value as a string.
            return f"Recalled '{store[key]}' from key '{key}'."  # Line 50:  Includes both the value and the key for clarity.
        # Line 51:  Key not found — return an informative error message (not an exception).
        return f"Key '{key}' not found in memory."  # Line 52:  The agent will relay this to the user as a normal response.
    # Line 53:  (blank line)
    # Line 54:  Define the memory_list tool — shows all stored keys and values.
    def memory_list() -> str:  # Line 55:  Returns a formatted view of everything currently in memory.
        # Line 56:  If the store is empty, say so clearly.
        if not store:  # Line 57:  Empty dict is falsy — this catches the "nothing stored yet" case.
            # Line 58:  Return a message indicating empty state.
            return "Memory is empty."  # Line 59:  (blank line)
        # Line 60:  Build a formatted string showing all key-value pairs.
        items = ", ".join(f"'{k}'={v}" for k, v in store.items())  # Line 61:  Generator expression keeps this memory-efficient even with many entries.
        # Line 62:  Return the formatted list as a single string response.
        return f"Memory contents: {items}"  # Line 63:  (blank line)
    # Line 64:  Return all tools as a name→function mapping.
    return {"memory_store": memory_store, "memory_recall": memory_recall, "memory_list": memory_list}  # Line 65:  Keys must match SimulatedLM's TOOL output exactly.


def main():  # Line 67:  Entry point — wires up the system and runs a demo conversation.
    """Set up two agents (math + memory), connect them via a bus, and run demo tasks."""
    # Line 70:  Print a header to identify what's running.
    print("\n" + "=" * 60)  # Line 71:  Visual separator for terminal output.
    # Line 72:  Print the module title.
    print("  TOYAGENTS #1 — ToyA2A: Message Passing + Delegation")  # Line 73:  Identifies which curriculum module is running.
    # Line 74:  Print another separator.
    print("=" * 60 + "\n")  # Line 75:  (blank line)
    # Line 76:  ─── Step 1: Create the shared infrastructure ──────────────────────
    # Line 77:  Create the message bus — the single communication channel for all agents.
    bus = MessageBus()  # Line 78:  One bus for the entire system (like one postal service for a town).
    # Line 79:  Create the dispatcher and register both domains.
    dispatcher = Dispatcher(bus)  # Line 80:  The dispatcher needs a reference to the bus to publish messages.
    # Line 81:  Tell the dispatcher that "math" domain is handled by "math_agent".
    dispatcher.register_domain("math", "math_agent")  # Line 82:  This registration enables automatic routing of math tasks.
    # Line 83:  Tell the dispatcher that "memory" domain is handled by "memory_agent".
    dispatcher.register_domain("memory", "memory_agent")  # Line 84:  Now both domains are routable.
    # Line 85:  (blank line)
    # Line 86:  ─── Step 2: Create the agents ──────────────────────────────────────
    # Line 87:  Create the math agent with its tools, connected to the shared bus and dispatcher.
    math_agent = Agent(  # Line 88:  This agent handles arithmetic operations.
        agent_id="math_agent",  # Line 89:  Unique ID used in all messages and logs.
        domain="math",  # Line 90:  Tells the LM this agent specializes in math.
        tools=create_math_tools(),  # Line 91:  Inject the math tool registry (add, subtract, multiply).
        bus=bus,  # Line 92:  Shared bus — same object as memory_agent's bus (single point of communication).
        dispatcher=dispatcher,  # Line 93:  Shared dispatcher — both agents use the same routing logic.
    )  # Line 94:  Close the constructor call.
    # Line 95:  Create the memory agent with its tools.
    memory_agent = Agent(  # Line 96:  This agent handles key-value storage operations.
        agent_id="memory_agent",  # Line 97:  Unique ID for this agent.
        domain="memory",  # Line 98:  Tells the LM this agent specializes in memory management.
        tools=create_memory_tools(),  # Line 99:  Inject the memory tool registry (store, recall, list).
        bus=bus,  # Line 100:  Same shared bus instance — this is what makes them "connected."
        dispatcher=dispatcher,  # Line 101:  Same shared dispatcher.
    )  # Line 102:  Close the constructor call.
    # Line 103:  (blank line)
    # Line 104:  ─── Step 3: Register agents on the bus and start their threads ───
    # Line 105:  Register math_agent's inbox on the bus (creates its queue).
    bus.register("math_agent")  # Line 106:  Must be done before any message is sent to this agent.
    # Line 107:  Register memory_agent's inbox on the bus.
    bus.register("memory_agent")  # Line 108:  Now both agents can receive messages.
    # Line 109:  Start the math agent's background thread (begins polling its inbox).
    math_agent.start()  # Line 110:  After this, math_agent is "alive" in a separate thread.
    # Line 111:  Start the memory agent's background thread.
    memory_agent.start()  # Line 112:  Both agents are now running concurrently, each polling their own inbox.
    # Line 113:  Small delay to ensure both threads have started before we send tasks.
    time.sleep(0.2)  # Line 114:  Without this, the first message might arrive before the thread is ready to poll.
    # Line 115:  (blank line)
    # Line 116:  ─── Step 4: Run demo scenarios ─────────────────────────────────────
    # Line 117:  Print a section header for the first scenario.
    print(f"\n{'─'*50}")  # Line 118:  Visual separator between scenarios.
    # Line 119:  Describe what we're about to do.
    print("  SCENARIO 1: Direct task (math_agent handles 'add 5 and 3')")  # Line 120:  This tests the simple path — no delegation needed.
    # Line 121:  Print another separator.
    print(f"{'─'*50}\n")  # Line 122:  (blank line)
    # Line 123:  Send a math task directly to the math agent.
    math_agent.send_task("add 5 and 3")  # Line 124:  This publishes a message to math_agent's inbox; it will process it asynchronously.
    # Line 125:  Wait for the agents to process (giving them time to complete the round-trip).
    time.sleep(1.0)  # Line 126:  1 second is more than enough for a simple tool call + response.
    # Line 127:  (blank line)
    # Line 128:  Print header for the second scenario.
    print(f"\n{'─'*50}")  # Line 129:  (blank line)
    # Line 130:  Describe the delegation scenario.
    print("  SCENARIO 2: Delegation (math_agent delegates 'store 8 as result' to memory_agent)")  # Line 131:  This tests the multi-agent path — math agent can't store, so it delegates.
    # Line 132:  Print separator.
    print(f"{'─'*50}\n")  # Line 133:  (blank line)
    # Line 134:  Send a memory task to the MATH agent (out-of-domain → triggers delegation).
    math_agent.send_task("store 8 as result")  # Line 135:  The math agent's LM will see "store" and delegate to memory_agent.
    # Line 136:  Wait for the full delegation round-trip (send → receive → process → respond).
    time.sleep(2.0)  # Line 137:  Delegation takes longer because it involves two agents and two bus hops.
    # Line 138:  (blank line)
    # Line 139:  Print header for the third scenario.
    print(f"\n{'─'*50}")  # Line 140:  (blank line)
    # Line 141:  Describe the recall scenario.
    print("  SCENARIO 3: Delegation back (math_agent delegates 'recall result' to memory_agent)")  # Line 142:  Tests that delegation works for read operations too.
    # Line 143:  Print separator.
    print(f"{'─'*50}\n")  # Line 144:  (blank line)
    # Line 145:  Send a recall task to the math agent (triggers delegation again).
    math_agent.send_task("recall result")  # Line 146:  Memory agent will look up "result" and return "8".
    # Line 147:  Wait for the round-trip.
    time.sleep(2.0)  # Line 148:  (blank line)
    # Line 149:  Print header for the fourth scenario.
    print(f"\n{'─'*50}")  # Line 150:  (blank line)
    # Line 151:  Describe a task that goes directly to memory_agent (no delegation).
    print("  SCENARIO 4: Direct task (memory_agent handles 'list all')")  # Line 152:  Tests that direct tasks to memory_agent work without delegation.
    # Line 153:  Print separator.
    print(f"{'─'*50}\n")  # Line 154:  (blank line)
    # Line 154:  Send a list task directly to the memory agent.
    memory_agent.send_task("list all")  # Line 155:  Memory agent handles this directly — no delegation needed.
    # Line 156:  Wait for processing.
    time.sleep(1.0)  # Line 157:  (blank line)
    # Line 158:  ─── Step 5: Shutdown and report ───────────────────────────────────
    # Line 159:  Print a final separator before shutdown.
    print(f"\n{'─'*50}")  # Line 160:  (blank line)
    # Line 161:  Announce that we're shutting down.
    print("  Shutting down agents...")  # Line 162:  (blank line)
    # Line 163:  Stop the math agent (sets _running=False, joins thread).
    math_agent.stop()  # Line 164:  Graceful shutdown — waits for current operation to complete.
    # Line 165:  Stop the memory agent.
    memory_agent.stop()  # Line 166:  (blank line)
    # Line 167:  Print a summary of bus statistics.
    print(f"\n  Bus statistics: {bus.total_published} messages published to {len(bus.registered_agents())} agents.")  # Line 168:  Quick health check — if this is 0, something went wrong.
    # Line 169:  (blank line)
    # Line 170:  Print the full trace report for each agent.
    math_agent.trace.report()  # Line 171:  Shows every event the math agent experienced, with timing.
    # Line 172:  Print the memory agent's trace report.
    memory_agent.trace.report()  # Line 173:  Together, these two reports show the complete multi-agent conversation.


# Line 175:  Standard Python entry point guard — only runs main() when executed directly (not imported).
if __name__ == "__main__":  # Line 176:  Allows this file to be imported by test_adversarial.py without triggering the demo.
    # Line 177:  Call the main function to run the demo.
    main()  # Line 178:  (blank line)
```

---

## c. `test_adversarial.py`

```python
# Line 1:  Import sys and os for path setup (ensures Harness/ is importable from this file's location).
import sys, os  # Line 2:  Add the script's directory to sys.path so imports work regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # Line 3:  Makes "from Harness..." and "from main import ..." work.

# Line 5:  Import time for sleep calls between async operations in tests.
import time  # Line 6:  (blank line)

# Line 8:  Import the module's main components under test.
from Harness.message_bus import MessageBus  # Line 9:  The bus we'll stress-test with malformed messages.
from Harness.dispatcher import Dispatcher  # Line 10:  Test routing logic with edge cases.
from Harness.agent import Agent  # Line 11:  The agent itself — test its resilience to bad inputs.
from Harness.guardrails import Guardrails  # Line 12:  Test that guardrails actually block bad input.
from Harness.simulated_lm import SimulatedLM  # Line 13:  Test the LM with garbage inputs.
from main import create_math_tools, create_memory_tools  # Line 14:  Reuse the same tool factories as main.py for consistency.


# ──────────────────────────────────────────────
#  TEST 1: Broken / Chaotic LM
#  Proves: the system doesn't crash on malformed output
# ──────────────────────────────────────────────
def test_broken_lm():  # Line 20:  Feed garbage responses from a mock LM. System must not raise any exception.
    """Feed garbage responses. System must not raise."""
    # Line 23:  Create a fresh bus and dispatcher for isolation (each test gets its own system).
    bus = MessageBus()  # Line 24:  Isolated bus — no cross-test contamination.
    dispatcher = Dispatcher(bus)  # Line 25:  Fresh dispatcher with no domains registered yet.
    # Line 26:  Register a minimal domain so the agent can start without errors.
    dispatcher.register_domain("math", "broken_agent")  # Line 27:  We need at least one domain for the agent to function.
    # Line 28:  Create an agent with a BROKEN LM (we'll monkey-patch its generate method).
    agent = Agent(  # Line 29:  Standard construction — we'll break it after creation.
        agent_id="broken_agent",  # Line 30:  (blank line)
        domain="math",  # Line 31:  (blank line)
        tools=create_math_tools(),  # Line 32:  Normal tools — the problem is in the LM, not the tools.
        bus=bus,  # Line 33:  (blank line)
        dispatcher=dispatcher,  # Line 34:  (blank line)
    )  # Line 35:  Close constructor.
    # Line 36:  Monkey-patch the LM's generate method to return garbage strings.
    def broken_generate(task, context):  # Line 37:  This simulates an LLM that produces malformed output.
        # Line 38:  Return a string that doesn't match any expected format (TOOL/DELEGATE/RESPONSE).
        return "COMPLETE GARBAGE ### $$$$ ??? not a valid action"  # Line 39:  The agent should log a warning and send an error, NOT crash.
    # Line 40:  Replace the agent's LM generate method with our broken version.
    agent.lm.generate = broken_generate  # Line 41:  Python allows attribute assignment on instances — this is our "fault injection."
    # Line 42:  Register the agent on the bus and start it.
    bus.register("broken_agent")  # Line 43:  Must register before sending messages.
    agent.start()  # Line 44:  Start the broken agent's thread.
    time.sleep(0.1)  # Line 45:  Give the thread time to start polling.
    # Line 46:  Send a normal task — the broken LM will produce garbage, but the agent must survive.
    agent.send_task("add 2 and 2")  # Line 47:  This should trigger the "unrecognized action" path in handle_message.
    time.sleep(0.5)  # Line 48:  Wait for the agent to process (and not crash).
    # Line 49:  Stop the agent cleanly.
    agent.stop()  # Line 50:  If we get here without an exception, the test passes.
    # Line 51:  Assert that the agent processed at least one message (proving it didn't crash on the first iteration).
    assert agent.messages_processed >= 1, f"Agent should have processed at least 1 message, got {agent.messages_processed}"  # Line 52:  This proves the loop continued past the garbage LM output.


# ──────────────────────────────────────────────
#  TEST 2: Invalid / Hostile Input
#  Proves: guardrails block bad input before it reaches the core
# ──────────────────────────────────────────────
def test_hostile_input():  # Line 58:  Oversized, empty, or forbidden-pattern inputs must be blocked by guardrails.
    """Oversized, empty, or forbidden-pattern inputs must be blocked."""
    # Line 61:  Create guardrails with tight limits for testing.
    gr = Guardrails(max_iterations=5, max_input_length=50)  # Line 62:  Small max_input_length makes it easy to trigger the length check.
    # Line 63:  Test 2a: Oversized input should be blocked.
    oversized = "A" * 1000  # Line 64:  1000 characters exceeds our 50-char limit.
    valid, reason = gr.validate_input(oversized)  # Line 65:  Run validation on the oversized string.
    assert not valid, "Oversized input should be rejected"  # Line 66:  If it's not rejected, guardrails are broken.
    assert "too long" in reason.lower(), f"Reason should mention length, got: {reason}"  # Line 67:  Verify the rejection reason is specific (helps debugging).
    # Line 68:  Test 2b: Empty input should be blocked.
    valid, reason = gr.validate_input("")  # Line 69:  Empty string has no content to process.
    assert not valid, "Empty input should be rejected"  # Line 70:  (blank line)
    # Line 71:  Test 2c: Whitespace-only input should be blocked.
    valid, reason = gr.validate_input("   \t\n  ")  # Line 72:  Looks like it has content but doesn't.
    assert not valid, "Whitespace-only input should be rejected"  # Line 73:  (blank line)
    # Line 74:  Test 2d: Injection pattern should be blocked.
    injection = "add 1 and __import__('os').system('rm -rf /')"  # Line 75:  Classic Python code injection attempt.
    valid, reason = gr.validate_input(injection)  # Line 76:  The guardrails should catch "__import__" in the forbidden patterns.
    assert not valid, "Injection pattern should be rejected"  # Line 77:  If this passes validation, we have a security hole.
    assert "forbidden" in reason.lower(), f"Reason should mention forbidden pattern, got: {reason}"  # Line 78:  (blank line)
    # Line 79:  Test 2e: Non-string input should be blocked.
    valid, reason = gr.validate_input(12345)  # Line 80:  An integer is not a valid task string.
    assert not valid, "Non-string input should be rejected"  # Line 81:  (blank line)
    # Line 82:  Test 2f: Normal input should PASS validation (positive control).
    valid, reason = gr.validate_input("add 5 and 3")  # Line 83:  A perfectly normal task must not be blocked.
    assert valid, f"Normal input should pass validation, got: {reason}"  # Line 84:  If this fails, guardrails are too aggressive (false positives).


# ──────────────────────────────────────────────
#  TEST 3: Tool Execution Failure
#  Proves: a failing tool doesn't crash the loop; error is handled
# ─────────────────