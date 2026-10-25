# Line 1:  Import threading so each agent can run its loop in a separate thread.
import threading  # Line 2:  Import time for sleep calls during polling (prevents busy-waiting).
import time  # Line 3:  Import json to parse tool arguments from the LM's output string.
import json  # Line 4:  Import typing for type hints.
from typing import Dict, Callable, Optional  # Line 5:  (blank line)

# Line 7:  Import all Harness components that the agent depends on.
from Harness.envelope import (
    MessageEnvelope,
)  # Line 8:  The message format the agent sends and receives.
from Harness.message_bus import (
    MessageBus,
)  # Line 9:  The communication channel the agent polls and publishes to.
from Harness.dispatcher import (
    Dispatcher,
)  # Line 10:  Routes delegation when the LM says "DELEGATE: ...".
from Harness.simulated_lm import (
    SimulatedLM,
)  # Line 11:  The "brain" that decides what action to take.
from Harness.guardrails import (
    Guardrails,
)  # Line 12:  Safety checks before processing any message.
from Harness.trace_logger import (
    TraceLogger,
)  # Line 13:  Colored execution trace for observability.


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
    ):  # Line 28:  Bus and dispatcher are shared across agents (single instance each).
        # Line 29:  Store the unique identifier for this agent (used in messages and logs).
        self.agent_id = agent_id  # Line 30:  This string appears in every envelope this agent sends or receives.
        # Line 31:  Store the domain this agent specializes in.
        self.domain = (
            domain  # Line 32:  Passed to SimulatedLM so it knows when to delegate.
        )
        # Line 33:  Create the simulated brain for this agent, configured with its domain.
        self.lm = SimulatedLM(
            domain
        )  # Line 34:  Each agent gets its own LM instance — they make independent decisions.
        # Line 35:  Store the tool registry — maps tool names to callable functions.
        self.tools = tools  # Line 36:  Tools are plain Python functions; the agent doesn't care how they're implemented.
        # Line 37:  Bind to the shared message bus for sending and receiving messages.
        self.bus = bus  # Line 38:  All inter-agent communication goes through this single bus instance.
        # Line 39:  Bind to the shared dispatcher for routing delegation messages.
        self.dispatcher = dispatcher  # Line 40:  The agent asks the dispatcher "who handles this?" rather than hardcoding recipient IDs.
        # Line 41:  Create guardrails with default limits (can be overridden per-agent if needed).
        self.guardrails = (
            Guardrails()
        )  # Line 42:  Each agent validates its own inputs independently.
        # Line 43:  Create a trace logger for this agent (color-coded by agent_id).
        self.trace = TraceLogger(
            agent_id
        )  # Line 44:  The trace logger records every step for post-hoc analysis and the final report.
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

    def start(
        self,
    ) -> (
        None
    ):  # Line 52:  Launch the agent's run loop in a new thread. Non-blocking — returns immediately.
        """Start the agent's event loop in a background thread."""
        # Line 55:  Set the running flag to True so the loop knows to keep going.
        self._running = True  # Line 56:  This is checked at the top of each loop iteration for graceful shutdown.
        # Line 57:  Create a new thread targeting our _run_loop method.
        self._thread = threading.Thread(
            target=self._run_loop, name=f"agent-{self.agent_id}"
        )  # Line 58:  Naming the thread makes it identifiable in debugging tools and crash dumps.
        # Line 59:  Set daemon=True so the thread dies automatically when the main program exits.
        self._thread.daemon = True  # Line 60:  Without this, a stuck agent thread would prevent Python from exiting cleanly.
        # Line 61:  Actually start the thread — it begins executing _run_loop() in parallel.
        self._thread.start()  # Line 62:  After this line, the agent is "alive" and polling its inbox.
        # Line 63:  Log that the agent has started (visible in trace output).
        self.trace.log(
            "loop", f"Agent '{self.agent_id}' started (domain={self.domain})"
        )  # Line 64:  The "loop" component tag means this is a lifecycle event, not a message event.

    def stop(
        self,
    ) -> None:  # Line 66:  Signal the agent to stop and wait for its thread to finish.
        """Gracefully stop the agent's run loop."""
        # Line 69:  Flip the running flag — the loop will exit on its next iteration.
        self._running = False  # Line 70:  This is a cooperative shutdown — we don't kill the thread, we ask it to stop.
        # Line 71:  If a thread exists, wait for it to finish (with a timeout to prevent hanging).
        if (
            self._thread is not None
        ):  # Line 72:  Guard against calling stop() before start().
            # Line 73:  Block until the thread finishes or 2 seconds pass (whichever comes first).
            self._thread.join(
                timeout=2.0
            )  # Line 74:  The timeout prevents a stuck agent from blocking program shutdown indefinitely.
        # Line 75:  Log that the agent has stopped.
        self.trace.log(
            "loop",
            f"Agent '{self.agent_id}' stopped (processed {self.messages_processed} messages)",
        )  # Line 76:  Including the count gives a quick health summary in the trace report.

    def _run_loop(
        self,
    ) -> (
        None
    ):  # Line 78:  The main event loop — runs forever until _running is set to False.
        """Continuously poll the inbox, process messages, and send responses."""
        # Line 81:  Loop while the agent should be running (checked each iteration for responsive shutdown).
        while (
            self._running
        ):  # Line 82:  This is the "heart" of the agent — it beats as long as _running is True.
            # Line 83:  Poll the bus for a message addressed to this agent (waits up to 0.5s).
            envelope = self.bus.poll(
                self.agent_id, timeout=0.5
            )  # Line 84:  The 0.5s timeout means we check _running at least twice per second (responsive shutdown).
            # Line 85:  If no message arrived within the timeout, just loop back and check _running again.
            if (
                envelope is None
            ):  # Line 86:  No work right now — sleep is implicit in the poll timeout.
                # Line 87:  Continue to next iteration (re-check _running flag).
                continue  # Line 88:  This is NOT a busy-wait — poll() already blocked for 0.5s.
            # Line 89:  We have a message to process — handle it.
            self.handle_message(
                envelope
            )  # Line 90:  All the real work happens inside this method.

    def handle_message(
        self, envelope: MessageEnvelope
    ) -> None:  # Line 92:  Process a single incoming message end-to-end.
        """Validate, think, act, and respond to a single message."""
        # Line 95:  Log that we received a message (for trace visibility).
        self.trace.log(
            "loop", f"Received: {envelope}"
        )  # Line 96:  The __str__ of envelope gives a compact one-line summary.
        # Line 97:  Extract the task text from the payload (the actual content to process).
        task = envelope.payload.get(
            "task", ""
        )  # Line 98:  .get() with default "" prevents KeyError if payload is malformed.
        # Line 99:  Run guardrail validation on the task before doing anything else.
        valid, reason = self.guardrails.validate_input(
            task
        )  # Line 100:  This is the FIRST thing we do with any external input — security first.
        # Line 101:  If the input failed validation, reject it immediately.
        if not valid:  # Line 102:  Guardrails said NO — we must not process this task.
            # Line 103:  Log the rejection with the reason (important for debugging).
            self.trace.log(
                "guardrails", f"BLOCKED: {reason}", level="error"
            )  # Level "error" makes this stand out in colored output.
            # Line 104:  Send an error response back to whoever sent the message.
            self._send_response(
                envelope, f"ERROR: Input rejected — {reason}"
            )  # Line 105:  The sender needs to know their task was rejected and why.
            # Line 106:  Return early — no further processing of an invalid input.
            return  # Line 107:  (blank line)
        # Line 108:  Input is valid — ask the LM (brain) what to do.
        context = {
            "agent_id": self.agent_id,
            "domain": self.domain,
        }  # Line 109:  Provide minimal context so the LM knows who it's talking to.
        # Line 110:  Call the LM to get an action instruction (TOOL / DELEGATE / RESPONSE).
        action = self.lm.generate(
            task, context
        )  # Line 111:  This is the "think" step — in production this would be an API call to a real LLM.
        # Line 112:  Log what the LM decided (critical for debugging agent behavior).
        self.trace.log(
            "lm", f"Decision: {action}"
        )  # Line 113:  Seeing the raw LM output helps identify when the "brain" makes a wrong choice.
        # Line 114:  Parse the action string and execute the appropriate branch.
        if action.startswith(
            "TOOL:"
        ):  # Line 115:  The LM wants us to call one of our tools.
            # Line 116:  Execute the tool and send the result back.
            self._execute_tool(envelope, action)  # Line 117:  (blank line)
        elif action.startswith(
            "DELEGATE:"
        ):  # Line 118:  The LM says this task belongs to another agent.
            # Line 119:  Forward the task to the appropriate agent via the bus.
            self._delegate(envelope, action)  # Line 120:  (blank line)
        elif action.startswith(
            "RESPONSE:"
        ):  # Line 121:  The LM has a direct answer (or a polite refusal).
            # Line 122:  Extract the response text after "RESPONSE: ".
            response_text = action[
                len("RESPONSE: ") :
            ]  # Line 123:  String slicing to remove the prefix and get just the message.
            # Line 124:  Send the response back to the sender.
            self._send_response(envelope, response_text)  # Line 125:  (blank line)
        else:  # Line 126:  Unrecognized action format — treat as an error.
            # Line 127:  Log a warning about the malformed LM output.
            self.trace.log(
                "lm", f"WARNING: Unrecognized action format: {action}", level="warn"
            )  # Line 128:  This shouldn't happen with our SimulatedLM but could with a real LLM.
            # Line 129:  Send an error response so the sender isn't left hanging.
            self._send_response(
                envelope, "ERROR: Agent produced unrecognized action."
            )  # Line 130:  (blank line)
        # Line 131:  Increment our processed counter for metrics.
        self.messages_processed += 1  # Line 132:  Only count successfully handled messages (not rejected ones).

    def _execute_tool(
        self, envelope: MessageEnvelope, action: str
    ) -> None:  # Line 134:  Parse a TOOL instruction and execute the named tool.
        """Parse 'TOOL: name | ARGS: {json}' and call the tool with the arguments."""
        # Line 137:  Split the action string on " | ARGS: " to separate tool name from arguments.
        parts = action.split(
            " | ARGS: ", 1
        )  # maxsplit=1 ensures we only split once (args JSON might contain pipes).
        # Line 138:  If the format is malformed (missing " | ARGS: "), log and error out.
        if (
            len(parts) != 2
        ):  # Line 139:  Malformed action — can't extract both name and args.
            # Line 140:  Log the problem for debugging.
            self.trace.log(
                "tools", f"Malformed tool action: {action}", level="error"
            )  # Line 141:  (blank line)
            # Line 142:  Send an error response to the sender.
            self._send_response(
                envelope, "ERROR: Malformed tool instruction from LM."
            )  # Line 143:  (blank line)
            # Line 144:  Return without executing anything.
            return  # Line 145:  (blank line)
        # Line 146:  Extract the tool name (first part, after "TOOL: ").
        tool_name = (
            parts[0].replace("TOOL: ", "").strip()
        )  # Line 147:  Remove the prefix and any extra whitespace.
        # Line 148:  Parse the JSON arguments string into a dictionary.
        try:  # Line 149:  Wrap in try/except because json.loads can raise on malformed JSON.
            # Line 150:  Convert the JSON string to a Python dict.
            args = json.loads(
                parts[1]
            )  # Line 151:  This is where the LM's "structured output" becomes usable data.
        except (
            json.JSONDecodeError
        ) as e:  # Line 152:  If the JSON is broken, we can't call the tool with bad args.
            # Line 153:  Log the parse error with details.
            self.trace.log(
                "tools", f"JSON parse error in tool args: {e}", level="error"
            )  # Line 154:  (blank line)
            # Line 155:  Send an error response explaining what went wrong.
            self._send_response(
                envelope, f"ERROR: Could not parse tool arguments: {e}"
            )  # Line 156:  (blank line)
            # Line 157:  Return without executing.
            return  # Line 158:  (blank line)
        # Line 159:  Look up the tool in our registry by name.
        tool_fn = self.tools.get(
            tool_name
        )  # Line 160:  .get() returns None if the tool doesn't exist (rather than raising KeyError).
        # Line 161:  If the tool isn't registered, we can't execute it.
        if (
            tool_fn is None
        ):  # Line 162:  This catches typos in tool names or tools that weren't registered at startup.
            # Line 163:  Log which tool was requested but not found.
            self.trace.log(
                "tools",
                f"Tool '{tool_name}' not found in registry. Available: {list(self.tools.keys())}",
                level="error",
            )  # Line 164:  Listing available tools helps the developer spot the mismatch.
            # Line 165:  Send an error response to the sender.
            self._send_response(
                envelope, f"ERROR: Tool '{tool_name}' does not exist."
            )  # Line 166:  (blank line)
            # Line 167:  Return without executing.
            return  # Line 168:  (blank line)
        # Line 169:  Tool found — execute it with the parsed arguments.
        try:  # Line 170:  Wrap in try/except because tools can fail (div by zero, bad data, etc.).
            # Line 171:  Call the tool function with keyword arguments from the parsed JSON.
            result = tool_fn(
                **args
            )  # Line 172:  **args unpacks the dict into keyword arguments (e.g., {"a":5,"b":3} → a=5, b=3).
            # Line 173:  Log the successful tool execution with its result.
            self.trace.log(
                "tools", f"Executed '{tool_name}'({args}) → {result}"
            )  # Line 174:  Showing both input and output makes the trace self-documenting.
            # Line 175:  Send the result back to the sender as a response.
            self._send_response(
                envelope, str(result)
            )  # Line 176:  Convert result to string since envelope payloads are text-based.
        except (
            Exception
        ) as e:  # Line 177:  Catch any exception from the tool — we must never crash the agent loop.
            # Line 178:  Log the tool failure with the exception details.
            self.trace.log(
                "tools",
                f"Tool '{tool_name}' raised: {type(e).__name__}: {e}",
                level="error",
            )  # Line 179:  Including the exception type helps distinguish bugs from expected failures.
            # Line 180:  Send an error response so the sender knows the tool failed.
            self._send_response(
                envelope, f"ERROR: Tool '{tool_name}' failed: {e}"
            )  # Line 181:  The agent survives — only this one task fails.

    def _delegate(
        self, envelope: MessageEnvelope, action: str
    ) -> (
        None
    ):  # Line 183:  Parse a DELEGATE instruction and forward the task to another agent.
        """Parse 'DELEGATE: agent_id' and publish a delegation message to that agent."""
        # Line 186:  Extract the target agent ID from the action string.
        target_agent = action.replace(
            "DELEGATE: ", ""
        ).strip()  # Line 187:  Remove the prefix to get just the agent ID (e.g., "memory_agent").
        # Line 188:  Log that we're delegating and to whom.
        self.trace.log(
            "loop",
            f"Delegating to '{target_agent}': {envelope.payload.get('task', '')[:50]}",
        )  # Line 189:  Truncate task text to 50 chars to keep trace lines readable.
        # Line 190:  Create a new envelope for the delegation (different from the original — it's a NEW message).
        delegation_envelope = MessageEnvelope(  # Line 191:  This is a fresh message, not a forward of the original.
            sender_id=self.agent_id,  # Line 192:  We are the sender of this delegation (the target needs to know who to respond to).
            recipient_id=target_agent,  # Line 193:  The agent that should handle this task.
            subject="delegation",  # Line 194:  Tag it as a delegation so the receiving agent can log it differently.
            payload={
                "task": envelope.payload.get("task", ""),
                "original_sender": envelope.sender_id,
            },  # Line 195:  Carry forward the task AND who originally asked (for multi-hop response routing).
            reply_to=envelope.message_id,  # Line 196:  Link this delegation to the original message for correlation in traces.
        )  # Line 197:  Close the constructor.
        # Line 198:  Publish the delegation to the bus — this is the non-blocking act.
        self.bus.publish(
            delegation_envelope
        )  # Line 199:  After this, the target agent will pick it up on its next poll cycle.
        # Line 200:  NOTE: We do NOT wait for a response here. The response will arrive
        #   as a separate message in our inbox, which we'll process on a future loop iteration.
        #   This is the key insight: delegation is fire-and-forget at the message level.
        pass  # Line 203:  No further action needed — the bus handles delivery.

    def _send_response(
        self, original_envelope: MessageEnvelope, response_text: str
    ) -> (
        None
    ):  # Line 205:  Create and publish a response message back to the sender of the original message.
        """Send a response envelope back to whoever sent us the original message."""
        # Line 208:  Determine who to send the response to (the original sender, not the bus).
        recipient = (
            original_envelope.sender_id
        )  # Line 209:  We always respond to the person who asked us, not to ourselves.
        # Line 210:  Create the response envelope.
        response_envelope = MessageEnvelope(  # Line 211:  A new message object — responses are separate from requests.
            sender_id=self.agent_id,  # Line 212:  We are the responder.
            recipient_id=recipient,  # Line 213:  Send back to whoever originally messaged us.
            subject="response",  # Line 214:  Tag as "response" so the receiving agent knows this is an answer, not a new task.
            payload={
                "result": response_text,
                "in_reply_to": original_envelope.message_id,
            },  # Line 215:  Include both the result text and a reference to the original message for correlation.
            reply_to=original_envelope.message_id,  # Line 216:  Set the reply_to field for trace correlation.
        )  # Line 217:  Close the constructor.
        # Line 218:  Log that we're sending a response (with a preview of the content).
        self.trace.log(
            "loop", f"Responding to '{recipient}': {response_text[:60]}"
        )  # Line 219:  Truncate long responses for trace readability.
        # Line 220:  Publish the response to the bus.
        self.bus.publish(
            response_envelope
        )  # Line 221:  The recipient will see this on their next poll cycle.

    def send_task(
        self, task_text: str
    ) -> (
        MessageEnvelope
    ):  # Line 223:  External entry point — submit a task to this agent (used by main.py and tests).
        """Create an initial task envelope and publish it to this agent's own inbox.

        This simulates a user sending a message directly to the agent.
        In production, this might be an HTTP endpoint or CLI prompt.
        """
        # Line 230:  Create an envelope as if a "user" sent it to this agent.
        envelope = MessageEnvelope(  # Line 231:  The sender is "user" to distinguish external input from inter-agent messages.
            sender_id="user",  # Line 232:  Using "user" makes it clear in traces that this originated externally.
            recipient_id=self.agent_id,  # Line 233:  Deliver to ourselves (we'll pick it up on our next poll).
            subject="task",  # Line 234:  Tag as "task" — the initial request from a user.
            payload={
                "task": task_text
            },  # Line 235:  The actual task text goes in the payload.
        )  # Line 236:  Close the constructor.
        # Line 237:  Publish to our own inbox — we'll process it on the next loop iteration.
        self.bus.publish(
            envelope
        )  # Line 238:  This is non-blocking; the task will be handled asynchronously by our thread.
        # Line 239:  Return the envelope so the caller can track its message_id for correlation.
        return envelope  # Line 240:  The caller (main.py) uses this to know which response to wait for.
