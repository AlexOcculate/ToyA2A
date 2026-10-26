# Line 1:  Import threading so each agent can run its loop in a separate thread.
import threading  # Line 2:  Import time for sleep calls during polling (prevents busy-waiting).
import time  # Line 3:  Import json to parse tool arguments from the LM's output string.
import json  # Line 4:  Import typing for type hints.
from typing import Dict, Callable, Optional, List

# Line 7:  Import all Harness components that the agent depends on.
from Harness.envelope import (
    MessageEnvelope,
)

# Line 8  The message format the agent sends and receives.
from Harness.message_bus import (
    MessageBus,
)

# Line 9  The communication channel the agent polls and publishes to.
from Harness.dispatcher import (
    Dispatcher,
)

# Line 10  Routes delegation when the LM says "DELEGATE: ...".
from Harness.simulated_lm import (
    SimulatedLM,
)

# Line 11  The "brain" that decides what action to take.
from Harness.guardrails import (
    Guardrails,
)

# Line 12  Safety checks before processing any message.
from Harness.trace_logger import (
    TraceLogger,
)

# Line 13  Colored execution trace for observability.


class Agent:  # Line 15:  A single autonomous entity that processes tasks, calls tools, and delegates when needed.
    """An agent with a domain, a brain (LM), tools, and a connection to the bus.

    Analogy: A specialist doctor in a hospital. They handle their specialty
    (domain) directly. When a patient needs a different specialist, they write
    a referral (delegation message) and send it through the hospital switchboard
    (message bus). The patient doesn't need to know which rooms exist.

    Lifecycle: start() → [poll inbox → validate → think → act → respond]* → stop()
    """

    def __init__(
        self,
        agent_id: str,
        domain: str,
        tools: Dict[
            str, Callable
        ],  # Line 27:  Constructor takes all dependencies explicitly (dependency injection — no hidden globals).
        bus: MessageBus,
        dispatcher: Dispatcher,
    ):
        # Line 28  Bus and dispatcher are shared across agents (single instance each).
        # Line 29:  Store the unique identifier for this agent (used in messages and logs).
        self.agent_id = agent_id  # Line 30:  This string appears in every envelope this agent sends or receives.
        # Line 31:  Store the domain this agent specializes in.
        self.domain = (
            domain  # Line 32:  Passed to SimulatedLM so it knows when to delegate.
        )
        # Line 33:  Create the simulated brain for this agent, configured with its domain.
        self.lm = SimulatedLM(domain)
        # Line 34  Each agent gets its own LM instance — they make independent decisions.
        # Line 35:  Store the tool registry — maps tool names to callable functions.
        self.tools = tools  # Line 36:  Tools are plain Python functions; the agent doesn't care how they're implemented.
        # Line 37:  Bind to the shared message bus for sending and receiving messages.
        self.bus = bus  # Line 38:  All inter-agent communication goes through this single bus instance.
        # Line 39:  Bind to the shared dispatcher for routing delegation messages.
        self.dispatcher = dispatcher  # Line 40:  The agent asks the dispatcher "who handles this?" rather than hardcoding recipient IDs.
        # Line 41:  Create guardrails with default limits (can be overridden per-agent if needed).
        self.guardrails = Guardrails()
        # Line 42  Each agent validates its own inputs independently.
        # Line 43:  Create a trace logger for this agent (color-coded by agent_id).
        self.trace = TraceLogger(agent_id)
        # Line 44  The trace logger records every step for post-hoc analysis and the final report.
        # Line 45:  Flag to control the run loop — set to False to stop the agent thread.
        self._running = False  # Line 46:  Initially False; start() flips it to True.
        # Line 47:  Reference to the thread that runs this agent's loop (None until started).
        self._thread: Optional[threading.Thread] = (
            None  # Line 48:  Storing the reference lets us call .join() on stop() for clean shutdown.
        )
        # Line 49:  Counter for how many messages this agent has processed (for metrics).
        self.messages_processed: int = (
            0  # Line 50:  Incremented after each successful handle_message() call.
        )
        # Line 51:  Store incoming responses so the caller can retrieve them later.
        self.responses: List[str] = []

    # Line 52  When another agent sends us a "response" subject message, we collect it here.

    def start(
        self,
    ) -> None:
        # Line 54  Launch the agent's run loop in a new thread. Non-blocking — returns immediately.
        """Start the agent's event loop in a background thread."""
        # Line 57:  Set the running flag to True so the loop knows to keep going.
        self._running = True  # Line 58:  This is checked at the top of each loop iteration for graceful shutdown.
        # Line 59:  Create a new thread targeting our _run_loop method.
        self._thread = threading.Thread(
            target=self._run_loop, name=f"agent-{self.agent_id}"
        )
        # Line 60  Naming the thread makes it identifiable in debugging tools and crash dumps.
        # Line 61:  Set daemon=True so the thread dies automatically when the main program exits.
        self._thread.daemon = True  # Line 62:  Without this, a stuck agent thread would prevent Python from exiting cleanly.
        # Line 63:  Actually start the thread — it begins executing _run_loop() in parallel.
        self._thread.start()
        # Line 64  After this line, the agent is "alive" and polling its inbox.
        # Line 65:  Log that the agent has started (visible in trace output).
        self.trace.log(
            "loop", f"Agent '{self.agent_id}' started (domain={self.domain})"
        )

    # Line 66  The "loop" component tag means this is a lifecycle event, not a message event.

    def stop(
        self,
    ) -> None:  # Line 68:  Signal the agent to stop and wait for its thread to finish.
        """Gracefully stop the agent's run loop."""
        # Line 71:  Flip the running flag — the loop will exit on its next iteration.
        self._running = False  # Line 72:  This is a cooperative shutdown — we don't kill the thread, we ask it to stop.
        # Line 73:  If a thread exists, wait for it to finish (with a timeout to prevent hanging).
        if self._thread is not None:
            # Line 74  Guard against calling stop() before start().
            # Line 75:  Block until the thread finishes or 2 seconds pass (whichever comes first).
            self._thread.join(timeout=2.0)
        # Line 76  The timeout prevents a stuck agent from blocking program shutdown indefinitely.
        # Line 77:  Log that the agent has stopped.
        self.trace.log(
            "loop",
            f"Agent '{self.agent_id}' stopped (processed {self.messages_processed} messages)",
        )

    # Line 78  Including the count gives a quick health summary in the trace report.

    def _run_loop(
        self,
    ) -> None:
        # Line 80  The main event loop — runs forever until _running is set to False.
        """Continuously poll the inbox, process messages, and send responses."""
        # Line 83:  Loop while the agent should be running (checked each iteration for responsive shutdown).
        while self._running:
            # Line 84  This is the "heart" of the agent — it beats as long as _running is True.
            # Line 85:  Poll the bus for a message addressed to this agent (waits up to 0.5s).
            envelope = self.bus.poll(self.agent_id, timeout=0.5)
            # Line 86  The 0.5s timeout means we check _running at least twice per second (responsive shutdown).
            # Line 87:  If no message arrived within the timeout, just loop back and check _running again.
            if envelope is None:
                # Line 88  No work right now — sleep is implicit in the poll timeout.
                # Line 89:  Continue to next iteration (re-check _running flag).
                continue  # Line 90:  This is NOT a busy-wait — poll() already blocked for 0.5s.
            # Line 91:  We have a message to process — handle it.
            self.handle_message(envelope)

    # Line 92  All the real work happens inside this method.

    def handle_message(
        self, envelope: MessageEnvelope
    ) -> None:  # Line 94:  Process a single incoming message end-to-end.
        """Validate, think, act, and respond to a single message.

        IMPORTANT: Messages come in two flavors based on their subject:
          - "task" / "delegation" → full processing pipeline (validate → think → act)
          - "response"            → just store it (it's an answer to a prior delegation)
        """
        # Line 102:  Log that we received a message (for trace visibility).
        self.trace.log("loop", f"Received: {envelope}")
        # Line 103  The __str__ of envelope gives a compact one-line summary.
        # Line 104:  ─── BRANCH ON MESSAGE TYPE ───────────────────────────────────────
        # Line 105:  If this is a RESPONSE (answer to a prior delegation), just store it.
        if envelope.subject == "response":
            # Line 106  Responses are results coming back from another agent — they don't need validation or LM processing.
            # Line 107:  Extract the result text from the payload.
            result_text = envelope.payload.get("result", "")
            # Line 108  The sending agent puts its answer in payload["result"].
            # Line 109:  Store it in our responses list so the caller can retrieve it later.
            self.responses.append(result_text)
            # Line 110  This is how the "user" (or calling agent) gets the final answer after a delegation round-trip.
            # Line 111:  Log that we received a response (visible in trace).
            self.trace.log(
                "loop", f"Got response from '{envelope.sender_id}': {result_text[:60]}"
            )
            # Line 112  Truncate for readability in trace output.
            # Line 113:  Increment processed counter and return — no further processing needed.
            self.messages_processed += 1  # Line 114:  Count it as a processed message (it was handled, just differently).
            # Line 115:  Return early — responses are terminal events, not new tasks to process.
            return
        # Line 117:  ─── HOP COUNT CHECK (prevents infinite delegation loops) ─────────
        # Line 118:  Check if this message has a hop counter that exceeds our limit.
        hop_count = envelope.payload.get("_hop_count", 0)
        # Line 119  New messages start at 0; each delegation increments it.
        # Line 120:  If the hop count has reached or exceeded max_iterations, refuse to process further.
        if hop_count >= self.guardrails.max_iterations:
            # Line 121  This is the circuit breaker — no more delegations beyond this depth.
            # Line 122:  Log that we're stopping due to max depth (important for debugging runaway loops).
            self.trace.log(
                "guardrails",
                f"STOPPED: Max delegation depth ({self.guardrails.max_iterations}) reached at hop {hop_count}",
                level="error",
            )
            # Line 123  Clearly visible in trace output.
            # Line 124:  Send an error response back to the sender explaining why we stopped.
            self._send_response(
                envelope,
                f"ERROR: Max delegation depth ({self.guardrails.max_iterations}) exceeded. Task not completed.",
            )
            # Line 125  The original requester gets a clear failure message instead of silence.
            # Line 126:  Return early — we are NOT processing this task or delegating further.
            return
        # Line 128:  ─── FULL PROCESSING PIPELINE (for "task" and "delegation" subjects) ──
        # Line 129:  Extract the task text from the payload.
        task = envelope.payload.get("task", "")
        # Line 130  .get() with default "" prevents KeyError if payload is malformed.
        # Line 131:  Run guardrail validation on the task before doing anything else.
        valid, reason = self.guardrails.validate_input(task)
        # Line 132  This is the FIRST thing we do with any external input — security first.
        # Line 133:  If the input failed validation, reject it immediately.
        if not valid:  # Line 134:  Guardrails said NO — we must not process this task.
            # Line 135:  Log the rejection with the reason (important for debugging).
            self.trace.log("guardrails", f"BLOCKED: {reason}", level="error")
            # Line 136  Level "error" makes this stand out in colored output.
            # Line 137:  Send an error response back to whoever sent the message.
            self._send_response(envelope, f"ERROR: Input rejected — {reason}")
            # Line 138  The sender needs to know their task was rejected and why.
            # Line 139:  Return early — no further processing of an invalid input.
            return
        # Line 141:  Input is valid — ask the LM (brain) what to do.
        context = {
            "agent_id": self.agent_id,
            "domain": self.domain,
        }  # Line 142:  Provide minimal context so the LM knows who it's talking to.
        # Line 143:  Call the LM to get an action instruction (TOOL / DELEGATE / RESPONSE).
        action = self.lm.generate(task, context)
        # Line 144  This is the "think" step — in production this would be an API call to a real LLM.
        # Line 145:  Log what the LM decided (critical for debugging agent behavior).
        self.trace.log("lm", f"Decision: {action}")
        # Line 146  Seeing the raw LM output helps identify when the "brain" makes a wrong choice.
        # Line 147:  Parse the action string and execute the appropriate branch.
        if action.startswith("TOOL:"):
            # Line 148  The LM wants us to call one of our tools.
            # Line 149:  Execute the tool and send the result back.
            self._execute_tool(envelope, action)
        elif action.startswith("DELEGATE:"):
            # Line 151  The LM says this task belongs to another agent.
            # Line 152:  Forward the task to the appropriate agent via the bus.
            self._delegate(envelope, action)
        elif action.startswith("RESPONSE:"):
            # Line 154  The LM has a direct answer (or a polite refusal).
            # Line 155:  Extract the response text after "RESPONSE: ".
            response_text = action[
                len("RESPONSE: ") :
            ]  # Line 156:  String slicing to remove the prefix and get just the message.
            # Line 157:  Send the response back to the sender.
            self._send_response(envelope, response_text)
        else:  # Line 159:  Unrecognized action format — treat as an error.
            # Line 160:  Log a warning about the malformed LM output.
            self.trace.log(
                "lm", f"WARNING: Unrecognized action format: {action}", level="warn"
            )
            # Line 161  This shouldn't happen with our SimulatedLM but could with a real LLM.
            # Line 162:  Send an error response so the sender isn't left hanging.
            self._send_response(envelope, "ERROR: Agent produced unrecognized action.")
        # Line 164:  Increment our processed counter for metrics.
        self.messages_processed += 1  # Line 165:  Only count successfully handled messages (not rejected ones).

    def _execute_tool(
        self, envelope: MessageEnvelope, action: str
    ) -> None:  # Line 167:  Parse a TOOL instruction and execute the named tool.
        """Parse 'TOOL: name | ARGS: {json}' and call the tool with the arguments."""
        # Line 170:  Split the action string on " | ARGS: " to separate tool name from arguments.
        parts = action.split(" | ARGS: ", 1)
        # Line 171  maxsplit=1 ensures we only split once (args JSON might contain pipes).
        # Line 172:  If the format is malformed (missing " | ARGS: "), log and error out.
        if len(parts) != 2:
            # Line 173  Malformed action — can't extract both name and args.
            # Line 174:  Log the problem for debugging.
            self.trace.log("tools", f"Malformed tool action: {action}", level="error")
            # Line 176:  Send an error response to the sender.
            self._send_response(envelope, "ERROR: Malformed tool instruction from LM.")
            # Line 178:  Return without executing anything.
            return
        # Line 180:  Extract the tool name (first part, after "TOOL: ").
        tool_name = parts[0].replace("TOOL: ", "").strip()
        # Line 181  Remove the prefix and any extra whitespace.
        # Line 182:  Parse the JSON arguments string into a dictionary.
        try:  # Line 183:  Wrap in try/except because json.loads can raise on malformed JSON.
            # Line 184:  Convert the JSON string to a Python dict.
            args = json.loads(parts[1])
        # Line 185  This is where the LM's "structured output" becomes usable data.
        except (
            json.JSONDecodeError
        ) as e:  # Line 186:  If the JSON is broken, we can't call the tool with bad args.
            # Line 187:  Log the parse error with details.
            self.trace.log(
                "tools", f"JSON parse error in tool args: {e}", level="error"
            )
            # Line 189:  Send an error response explaining what went wrong.
            self._send_response(envelope, f"ERROR: Could not parse tool arguments: {e}")
            # Line 191:  Return without executing.
            return
        # Line 193:  Look up the tool in our registry by name.
        tool_fn = self.tools.get(tool_name)
        # Line 194  .get() returns None if the tool doesn't exist (rather than raising KeyError).
        # Line 195:  If the tool isn't registered, we can't execute it.
        if tool_fn is None:
            # Line 196  This catches typos in tool names or tools that weren't registered at startup.
            # Line 197:  Log which tool was requested but not found.
            self.trace.log(
                "tools",
                f"Tool '{tool_name}' not found in registry. Available: {list(self.tools.keys())}",
                level="error",
            )
            # Line 198  Listing available tools helps the developer spot the mismatch.
            # Line 199:  Send an error response to the sender.
            self._send_response(envelope, f"ERROR: Tool '{tool_name}' does not exist.")
            # Line 201:  Return without executing.
            return
        # Line 203:  Tool found — execute it with the parsed arguments.
        try:  # Line 204:  Wrap in try/except because tools can fail (div by zero, bad data, etc.).
            # Line 205:  Call the tool function with keyword arguments from the parsed JSON.
            result = tool_fn(**args)
            # Line 206  **args unpacks the dict into keyword arguments (e.g., {"a":5,"b":3} → a=5, b=3).
            # Line 207:  Log the successful tool execution with its result.
            self.trace.log("tools", f"Executed '{tool_name}'({args}) → {result}")
            # Line 208  Showing both input and output makes the trace self-documenting.
            # Line 209:  Send the result back to the sender as a response.
            self._send_response(envelope, str(result))
        # Line 210  Convert result to string since envelope payloads are text-based.
        except (
            Exception
        ) as e:  # Line 211:  Catch any exception from the tool — we must never crash the agent loop.
            # Line 212:  Log the tool failure with the exception details.
            self.trace.log(
                "tools",
                f"Tool '{tool_name}' raised: {type(e).__name__}: {e}",
                level="error",
            )
            # Line 213  Including the exception type helps distinguish bugs from expected failures.
            # Line 214:  Send an error response so the sender knows the tool failed.
            self._send_response(envelope, f"ERROR: Tool '{tool_name}' failed: {e}")

    # Line 215  The agent survives — only this one task fails.

    def _delegate(self, envelope: MessageEnvelope, action: str) -> None:
        # Line 217  Parse a DELEGATE instruction and forward the task to another agent.
        """Parse 'DELEGATE: agent_id' and publish a delegation message to that agent."""
        # Line 220:  Extract the target agent ID from the action string.
        target_agent = action.replace("DELEGATE: ", "").strip()
        # Line 221  Remove the prefix to get just the agent ID (e.g., "memory_agent").
        # Line 222:  Log that we're delegating and to whom.
        self.trace.log(
            "loop",
            f"Delegating to '{target_agent}': {envelope.payload.get('task', '')[:50]}",
        )
        # Line 223  Truncate task text to 50 chars to keep trace lines readable.
        # Line 224:  Get the current hop count from the incoming message (0 for new tasks).
        current_hop = envelope.payload.get("_hop_count", 0)
        # Line 225  This tracks how many times this task has been forwarded.
        # Line 226:  Increment the hop count for the outgoing delegation.
        next_hop = current_hop + 1
        # Line 227  Each delegation adds one "hop" to the chain.
        # Line 228:  Create a new envelope for the delegation (different from the original — it's a NEW message).
        delegation_envelope = MessageEnvelope(  # Line 229:  This is a fresh message, not a forward of the original.
            sender_id=self.agent_id,  # Line 230:  We are the sender of this delegation (the target needs to know who to respond to).
            recipient_id=target_agent,  # Line 231:  The agent that should handle this task.
            subject="delegation",  # Line 232:  Tag it as a delegation so the receiving agent can log it differently.
            payload={  # Line 233:  Build the payload with all necessary fields including the hop counter.
                "task": envelope.payload.get(
                    "task", ""
                ),  # Line 234:  Carry forward the original task text.
                "original_sender": envelope.sender_id,  # Line 235:  Track who originally asked (for response routing).
                "_hop_count": next_hop,  # Line 236:  THE KEY FIELD: incremented hop count that prevents infinite loops.
            },  # Line 237:  Close the payload dict.
            reply_to=envelope.message_id,  # Line 238:  Link this delegation to the original message for correlation in traces.
        )
        # Line 239  Close the constructor.
        # Line 240:  Publish the delegation to the bus — this is the non-blocking act.
        self.bus.publish(delegation_envelope)
        # Line 241  After this, the target agent will pick it up on its next poll cycle.
        # Line 242:  NOTE: We do NOT wait for a response here. The response will arrive
        #   as a separate message in our inbox (subject="response"), which we'll
        #   store in self.responses on a future loop iteration.
        pass  # Line 245:  No further action needed — the bus handles delivery.

    def _send_response(
        self, original_envelope: MessageEnvelope, response_text: str
    ) -> None:
        # Line 247  Create and publish a response message back to the sender of the original message.
        """Send a response envelope back to whoever sent us the original message."""
        # Line 250:  Determine who to send the response to (the original sender, not the bus).
        recipient = original_envelope.sender_id
        # Line 251  We always respond to the person who asked us, not to ourselves.
        # Line 252:  Create the response envelope.
        response_envelope = MessageEnvelope(  # Line 253:  A new message object — responses are separate from requests.
            sender_id=self.agent_id,  # Line 254:  We are the responder.
            recipient_id=recipient,  # Line 255:  Send back to whoever originally messaged us.
            subject="response",  # Line 256:  Tag as "response" so the receiving agent knows this is an answer, not a new task.
            payload={
                "result": response_text,
                "in_reply_to": original_envelope.message_id,
            },  # Line 257:  Include both the result text and a reference to the original message for correlation.
            reply_to=original_envelope.message_id,  # Line 258:  Set the reply_to field for trace correlation.
        )
        # Line 259  Close the constructor.
        # Line 260:  Log that we're sending a response (with a preview of the content).
        self.trace.log("loop", f"Responding to '{recipient}': {response_text[:60]}")
        # Line 261  Truncate long responses for trace readability.
        # Line 262:  Publish the response to the bus.
        self.bus.publish(response_envelope)

    # Line 263  The recipient will see this on their next poll cycle.

    def send_task(self, task_text: str) -> MessageEnvelope:
        # Line 265  External entry point — submit a task to this agent (used by main.py and tests).
        """Create an initial task envelope and publish it to this agent's own inbox.

        This simulates a user sending a message directly to the agent.
        In production, this might be an HTTP endpoint or CLI prompt.
        """
        # Line 272:  Create an envelope as if a "user" sent it to this agent.
        envelope = MessageEnvelope(  # Line 273:  The sender is "user" to distinguish external input from inter-agent messages.
            sender_id="user",  # Line 274:  Using "user" makes it clear in traces that this originated externally.
            recipient_id=self.agent_id,  # Line 275:  Deliver to ourselves (we'll pick it up on our next poll).
            subject="task",  # Line 276:  Tag as "task" — the initial request from a user.
            payload={
                "task": task_text
            },  # Line 277:  The actual task text goes in the payload. No _hop_count means hop=0 (fresh start).
        )
        # Line 278  Close the constructor.
        # Line 279:  Publish to our own inbox — we'll process it on the next loop iteration.
        self.bus.publish(envelope)
        # Line 280  This is non-blocking; the task will be handled asynchronously by our thread.
        # Line 281:  Return the envelope so the caller can track its message_id for correlation.
        return envelope  # Line 282:  The caller (main.py) uses this to know which response to wait for.
