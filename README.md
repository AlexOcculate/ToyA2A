# ToyA2A — Multi-Agent Message Passing & Delegation

> **Two agents talk through a message bus. One delegates to the other. No framework needed.**

---

## Prerequisite

Understand **ToyAgentNoBrain (#0)** — specifically, how an agent loop works (poll → think → act → respond) and why the harness is separated from the LLM.

---

## What Is This?

Imagine a hospital where each doctor specializes in one area. When a patient needs help outside their doctor's specialty, the doctor writes a **referral** and sends it through the hospital's internal mail system. The patient never has to figure out which building the cardiologist is in — the referral just arrives at the right desk.

This module builds that exact pattern in ~400 lines of pure Python: two agents (a "math doctor" and a "memory doctor") communicate through an in-memory message bus, and either one can delegate a task to the other when it's outside their expertise. No framework, no network, no external dependencies — just queues, threads, and if/else rules.

**The key insight you'll take away:** Multi-agent systems are not magic. They're *message passing* + a *delegation decision*. Everything else (Orchestrators, LangGraph, AutoGen) is engineering around this core pattern.

---

## Folder Structure

```
ToyA2A/
├── main.py                  # Demo: wires up 2 agents, runs 4 scenarios
├── test_adversarial.py      # 5 failure-mode tests (proves the system survives chaos)
├── README.md                # This file
└── harness/
    ├── __init__.py          # Package marker
    ├── envelope.py          # MessageEnvelope — the "letter" that travels between agents
    ├── message_bus.py       # MessageBus — the "post office" with one mailbox per agent
    ├── dispatcher.py        # Dispatcher — the "receptionist" that knows who handles what
    ├── simulated_lm.py      # SimulatedLM — keyword-based "brain" with domain awareness
    ├── guardrails.py        # Guardrails — input validation + iteration cap (safety net)
    ├── agent.py             # Agent — the loop: poll inbox → validate → think → act → respond
    └── trace_logger.py      # TraceLogger — colored execution trace for debugging
```

---

## Dependencies

**External:** None. Zero `pip install` required.

**Standard library used:**

| Module        | Why                                                       |
| ------------- | --------------------------------------------------------- |
| `queue`       | Thread-safe FIFO queues (the backbone of the message bus) |
| `threading`   | Each agent runs in its own thread (concurrent polling)    |
| `time`        | Timestamps + timeouts for polling                         |
| `uuid`        | Unique message IDs for correlation                        |
| `json`        | Parse tool arguments from LM output strings               |
| `re`          | Regex for number extraction and injection detection       |
| `dataclasses` | Clean MessageEnvelope definition                          |
| `typing`      | Type hints for readability                                |

**Internal import graph:**

```
main.py
  └── harness.agent.Agent
        ├── harness.envelope.MessageEnvelope
        ├── harness.message_bus.MessageBus
        ├── harness.dispatcher.Dispatcher
        ├── harness.simulated_lm.SimulatedLM
        ├── harness.guardrails.Guardrails
        └── harness.trace_logger.TraceLogger

test_adversarial.py
  ├── harness.* (same as above)
  └── main.create_math_tools / create_memory_tools
```

No circular imports. No cross-module dependencies. This folder is fully self-contained.

---

## Execution

```bash
# Navigate to the module folder
cd ToyA2A/

# Run the demo (4 scenarios: direct task, delegation, recall, list)
python main.py

# Run adversarial tests (proves the system survives failure conditions)
python test_adversarial.py
```

No virtual environment needed. No API keys. No configuration. Just `python`.

---

## Expected Output

```
============================================================
  TOYAGENTS #1 — ToyA2A: Message Passing + Delegation
============================================================

──────────────────────────────────────────────────
  SCENARIO 1: Direct task (math_agent handles 'add 5 and 3')
──────────────────────────────────────────────────

[loop] math_agent | Agent 'math_agent' started (domain=math)
[loop] memory_agent | Agent 'memory_agent' started (domain=memory)
[loop] math_agent | Received: [a3f1c2e9] user → math_agent [task]
[guardrails] math_agent | OK
[lm] math_agent | Decision: TOOL: add | ARGS: {"a": 5.0, "b": 3.0}
[tools] math_agent | Executed 'add'({'a': 5.0, 'b': 3.0}) → 8.0
[loop] math_agent | Responding to 'user': 8.0

──────────────────────────────────────────────────
  SCENARIO 2: Delegation (math_agent delegates 'store 8 as result' to memory_agent)
──────────────────────────────────────────────────

[loop] math_agent | Received: [b7d2e4f1] user → math_agent [task]
[guardrails] math_agent | OK
[lm] math_agent | Decision: DELEGATE: memory_agent
[loop] math_agent | Delegating to 'memory_agent': store 8 as result
[loop] memory_agent | Received: [c9a3b5d2] math_agent → memory_agent [delegation]
[guardrails] memory_agent | OK
[lm] memory_agent | Decision: TOOL: memory_store | ARGS: {"key": "result", "value": "8"}
[tools] memory_agent | Executed 'memory_store'({'key': 'result', 'value': '8'}) → Stored '8' under key 'result'.
[loop] memory_agent | Responding to 'math_agent': Stored '8' under key 'result'.

──────────────────────────────────────────────────
  SCENARIO 3: Delegation back (math_agent delegates 'recall result' to memory_agent)
──────────────────────────────────────────────────

[loop] math_agent | Received: [d1e4f6a3] user → math_agent [task]
[guardrails] math_agent | OK
[lm] math_agent | Decision: DELEGATE: memory_agent
[loop] math_agent | Delegating to 'memory_agent': recall result
[loop] memory_agent | Received: [e2f5a7b4] math_agent → memory_agent [delegation]
[guardrails] memory_agent | OK
[lm] memory_agent | Decision: TOOL: memory_recall | ARGS: {"key": "result"}
[tools] memory_agent | Executed 'memory_recall'({'key': 'result'}) → Recalled '8' from key 'result'.
[loop] memory_agent | Responding to 'math_agent': Recalled '8' from key 'result'.

──────────────────────────────────────────────────
  SCENARIO 4: Direct task (memory_agent handles 'list all')
──────────────────────────────────────────────────

[loop] memory_agent | Received: [f3a6b8c5] user → memory_agent [task]
[guardrails] memory_agent | OK
[lm] memory_agent | Decision: TOOL: memory_list | ARGS: {}
[tools] memory_agent | Executed 'memory_list'({}) → Memory contents: 'result'=8
[loop] memory_agent | Responding to 'user': Memory contents: 'result'=8

──────────────────────────────────────────────────
  Shutting down agents...

[loop] math_agent | Agent 'math_agent' stopped (processed 3 messages)
[loop] memory_agent | Agent 'memory_agent' stopped (processed 3 messages)

  Bus statistics: 12 messages published to 2 agents.

============================================================
  TRACE REPORT — math_agent
============================================================
  [+0.000s] [loop] Agent 'math_agent' started (domain=math)
  [+0.201s] [loop] Received: [a3f1c2e9] user → math_agent [task]
  [+0.201s] [lm] Decision: TOOL: add | ARGS: {"a": 5.0, "b": 3.0}
  [+0.201s] [tools] Executed 'add'({'a': 5.0, 'b': 3.0}) → 8.0
  [+0.202s] [loop] Responding to 'user': 8.0
  [+1.203s] [loop] Received: [b7d2e4f1] user → math_agent [task]
  [+1.203s] [lm] Decision: DELEGATE: memory_agent
  [+1.203s] [loop] Delegating to 'memory_agent': store 8 as result
  [+3.204s] [loop] Received: [d1e4f6a3] user → math_agent [task]
  [+3.204s] [lm] Decision: DELEGATE: memory_agent
  [+3.204s] [loop] Delegating to 'memory_agent': recall result
  [+5.205s] [loop] Agent 'math_agent' stopped (processed 3 messages)

  11 events, 0 errors

============================================================
  TRACE REPORT — memory_agent
============================================================
  [+0.000s] [loop] Agent 'memory_agent' started (domain=memory)
  [+1.405s] [loop] Received: [c9a3b5d2] math_agent → memory_agent [delegation]
  [+1.405s] [lm] Decision: TOOL: memory_store | ARGS: {"key": "result", "value": "8"}
  [+1.406s] [tools] Executed 'memory_store'({'key': 'result', 'value': '8'}) → Stored '8' under key 'result'.
  [+1.406s] [loop] Responding to 'math_agent': Stored '8' under key 'result'.
  [+3.407s] [loop] Received: [e2f5a7b4] math_agent → memory_agent [delegation]
  [+3.407s] [lm] Decision: TOOL: memory_recall | ARGS: {"key": "result"}
  [+3.407s] [tools] Executed 'memory_recall'({'key': 'result'}) → Recalled '8' from key 'result'.
  [+3.408s] [loop] Responding to 'math_agent': Recalled '8' from key 'result'.
  [+5.409s] [loop] Received: [f3a6b8c5] user → memory_agent [task]
  [+5.409s] [lm] Decision: TOOL: memory_list | ARGS: {}
  [+5.409s] [tools] Executed 'memory_list'({}) → Memory contents: 'result'=8
  [+5.410s] [loop] Responding to 'user': Memory contents: 'result'=8
  [+6.411s] [loop] Agent 'memory_agent' stopped (processed 3 messages)

  13 events, 0 errors
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MAIN THREAD (main.py)                             │
│                                                                             │
│   Creates bus, dispatcher, agents. Sends tasks. Waits. Collects results.    │
└──────────────┬──────────────────────────────────────────────┬───────────────┘
               │ start()                                      │ start()
               ▼                                              ▼
┌────────────────────────────────┐      ┌────────────────────────────────────┐
│   THREAD: math_agent           │      │   THREAD: memory_agent             │
│                                │      │                                    │
│  ┌──────────────────────────┐  │      │  ┌──────────────────────────────┐  │
│  │       AGENT LOOP         │  │      │  │        AGENT LOOP            │  │
│  │                          │  │      │  │                              │  │
│  │  ┌─────────┐             │  │      │  │  ┌─────────┐                 │  │
│  │  │ POLL    │◄────────────┼──┼──────┼────►│ POLL    │                 │  │
│  │  │ inbox   │             │  │      │  │  │ inbox   │                 │  │
│  │  └────┬────┘             │  │      │  │  └────┬────┘                 │  │
│  │       ▼                  │  │      │  │       ▼                      │  │
│  │  ┌─────────┐             │  │      │  │  ┌─────────┐                 │  │
│  │  │GUARD-   │──BLOCKED──► │  │      │  │  │GUARD-   │──BLOCKED──►     │  │
│  │  │RAILS    │             │  │      │  │  │RAILS    │                 │  │
│  │  └────┬────┘             │  │      │  │  └────┬────┘                 │  │
│  │       ▼ valid            │  │      │  │       ▼ valid                │  │
│  │  ┌─────────┐             │  │      │  │  ┌─────────┐                 │  │
│  │  │   LM    │ "TOOL:..."  │  │      │  │  │   LM    │ "TOOL:..."      │  │
│  │  │(brain)  │ "DELEGATE:" │  │      │  │  │(brain)  │ "DELEGATE:"     │  │
│  │  └────┬────┘             │  │      │  │  └────┬────┘                 │  │
│  │       ▼                  │  │      │  │       ▼                      │  │
│  │  ┌──────────────┐        │  │      │  │  ┌──────────────┐            │  │
│  │  │TOOL or DELEG?│        │  │      │  │  │TOOL or DELEG?│            │  │
│  │  └───┬──────┬───┘        │  │      │  │  └───┬──────┬───┘            │  │
│  │      ▼      ▼            │  │      │  │      ▼      ▼                │  │
│  │  ┌──────┐ ┌────────┐     │  │      │  │  ┌──────┐ ┌────────┐         │  │
│  │  │TOOLS │ │DELEGATE│     │  │      │  │  │TOOLS │ │DELEGATE│         │  │
│  │  │add,  │ │to mem_ │     │  │      │  │  │store,│ │to math_│         │  │
│  │  │sub,  │ │agent   │     │  │      │  │  │recall│ │agent   │         │  │
│  │  │mult  │ └───┬────┘     │  │      │  │  │list  │ └───┬────┘         │  │
│  │  └──┬───┘     │          │  │      │  │  └──┬───┘     │              │  │
│  │     │         │          │  │      │  │     │         │              │  │
│  │     ▼         │          │  │      │  │     ▼         │              │  │
│  │  ┌────────┐   │          │  │      │  │  ┌────────┐   │              │  │
│  │  │RESPOND │   │          │  │      │  │  │RESPOND │   │              │  │
│  │  └───┬────┘   │          │  │      │  │  └───┬────┘   │              │  │
│  └──────┼────────┼──────────┘  │      │  └──────┼────────┼──────────────┘  │
│         │        │             │      │         │        │                 │
└─────────┼────────┼─────────────┘      └─────────┼────────┼─────────────────┘
          │        │                              │        │
          │        │    ┌──────────────────────┐  │        │
          │        │    │                      │  │        │
          ▼        ▼    │   MESSAGE BUS        │  ▼        ▼
     ┌───────────────────────────────────────────────────────────┐
     │                                                           │
     │   ┌─────────────┐             ┌─────────────────┐         │
     │   │ math_agent  │             │ memory_agent    │         │
     │   │ inbox (Q)   │◄──publish──►│ inbox (Q)       │         │
     │   └─────────────┘             └─────────────────┘         │
     │                                                           │
     │   register() creates a queue per agent                    │
     │   publish() puts envelope on recipient's queue            │
     │   poll() blocks up to timeout waiting for a message       │
     │                                                           │
     └───────────────────────────────────────────────────────────┘
          ▲                              ▲
          │                              │
          │    ┌──────────────────┐      │
          └────│   DISPATCHER     │──────┘
               │                  │
               │ domain_map:      │
               │   "math" →       │
               │     math_agent   │
               │   "memory" →     │
               │     memory_agent │
               │                  │
               │ route(task) →    │
               │   detect domain  │
               │   look up agent  │
               │   publish env    │
               └──────────────────┘

LEGEND:
  ┌────────┐  = Component (box)
  ──►      = Message flow / data direction
  ◄──      = Response flow
  Q        = queue.Queue (FIFO, thread-safe)
```

**Key design decisions annotated:**

| Decision                                           | Why                                                                                                                                                                     |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One bus for all agents                             | Single point of communication. Agents never talk directly — they only talk to the bus. This is *decoupling*: you can add a third agent without modifying the first two. |
| One queue per agent (not one shared queue)         | Prevents message cross-contamination. Agent A's messages never land in Agent B's inbox by accident.                                                                     |
| Dispatcher is separate from agents                 | Adding a new domain = one line (`dispatcher.register_domain("x", "agent_x")`). Zero changes to existing agent code. This is the **Open/Closed Principle** in practice.  |
| Delegation is fire-and-forget at the message level | The sender publishes and continues. The response arrives as a *separate* message later. This is how real distributed systems work (HTTP, Kafka, AMQP).                  |
| Threads (not async/await)                          | Simpler to understand for non-IT audiences. Each agent "lives" in its own thread, just like a person working at their own desk.                                         |

---

## State Machine Diagram

Each agent operates as a finite state machine with 5 states:

```
                    ┌──────────────────────────────────────────────────────┐
                    │                                                      │
                    ▼                                                      │
            ┌───────────────┐     start()      ┌───────────────────┐       │
            │    IDLE       │─────────────────►│   POLLING         │       │
            │ (not running) │                  │ (waiting for msg) │       │
            └───────────────┘                  └────────┬──────────┘       │
                    ▲                                   │                  │
                    │ stop()                            │ message arrives  │
                    │                                   ▼                  │
                    │                          ┌───────────────────┐       │
                    │                          │   VALIDATING      │       │
                    │                          │ (guardrails check)│       │
                    │                          └───┬───────────┬───┘       │
                    │                              │           │           │
                    │                         valid      BLOCKED           │
                    │                              │           │           │
                    │                              ▼           ▼           │
                    │                     ┌──────────────┐  ┌────────┐     │
                    │                     │   THINKING   │  │REJECT  │     │
                    │                     │ (LM decides) │  │(send   │     │
                    │                     └──┬───────┬───┘  │error)  │     │
                    │                        │       │      └───┬────┘     │
                    │                 TOOL   │       │ DELEGATE │          │
                    │                        ▼       ▼          │          │
                    │               ┌──────────┐  ┌──────────┐  │          │
                    │               │EXECUTING │  │DELEGATING│  │          │
                    │               │  TOOL    │  │(publish) │  │          │
                    │               └────┬─────┘  └───┬──────┘  │          │
                    │                    │            │         │          │
                    │                    ▼            ▼         │          │
                    │              ┌────────────────────────┐   │          │
                    │              │      RESPONDING        │◄──┘          │
                    │              │ (send result/error     │              │
                    │              │  back via bus)         │              │
                    │              └───────────┬────────────┘              │
                    │                          │                           │
                    │                          │ done                      │
                    │                          ▼                           │
                    │                   (back to POLLING) ─────────────────┘
                    │
                    │
                    └──────────────────────────────────────────────────────┘


STATE DESCRIPTION TABLE:
┌─────────────────┬─────────────────────────────────────────────────────────────┐
│ STATE           │ DESCRIPTION                                                 │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ IDLE            │ Agent created but not yet started. No thread running.       │
│                 │ Analogy: Doctor is home, not at the hospital.               │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ POLLING         │ Thread is alive, calling bus.poll() with a 0.5s timeout.    │
│                 │ If no message arrives, loops back here (checks _running).   │
│                 │ Analogy: Doctor sitting at desk, checking the mail slot.    │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ VALIDATING      │ Guardrails check the incoming task text.                    │
│                 │ Checks: type, length, forbidden patterns (injection).       │
│                 │ Analogy: Security guard checking your badge at the door.    │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ THINKING        │ LM receives the task + context and decides what to do.      │
│                 │ Output: "TOOL: ...", "DELEGATE: ...", or "RESPONSE: ..."   │
│                 │ Analogy: Doctor reading your chart and deciding next step.  │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ EXECUTING       │ A tool function is called with parsed arguments.            │
│                 │ Result (or exception) is captured.                          │
│                 │ Analogy: Doctor performing the procedure.                   │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ DELEGATING      │ A delegation envelope is created and published to the bus.  │
│                 │ The sender does NOT wait — it returns to POLLING.           │
│                 │ Analogy: Doctor writes a referral and drops it in the       │
│                 │ internal mail slot. They go back to seeing other patients.  │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ REJECT          │ Input failed validation. Error response sent to sender.     │
│                 │ Agent returns to POLLING immediately.                       │
│                 │ Analogy: Security guard says "No entry" and you leave.      │
├─────────────────┼─────────────────────────────────────────────────────────────┤
│ RESPONDING      │ A response envelope is created and published back to the    │
│                 │ original sender. Agent returns to POLLING.                  │
│                 │ Analogy: Doctor writes results on your chart and the        │
│                 │ front desk delivers them to you.                            │
└─────────────────┴─────────────────────────────────────────────────────────────┘


TRANSITION GUARDS:
  IDLE → POLLING:        start() called, _running set to True
  POLLING → VALIDATING:  bus.poll() returned a non-None envelope
  POLLING → IDLE:        stop() called, _running set to False (detected on next loop check)
  VALIDATING → THINKING: guardrails.validate_input() returned (True, "OK")
  VALIDATING → REJECT:   guardrails.validate_input() returned (False, reason)
  THINKING → EXECUTING:  LM output starts with "TOOL:"
  THINKING → DELEGATING: LM output starts with "DELEGATE:"
  THINKING → RESPONDING: LM output starts with "RESPONSE:"
  EXECUTING → RESPONDING: tool returned a result (or raised, which becomes error response)
  DELEGATING → POLLING:  bus.publish() completed (always immediate for unbounded queue)
  REJECT → POLLING:      error response sent
  RESPONDING → POLLING:  response envelope published to bus


THE LOOP STRUCTURE (simplified pseudocode):

  while _running:                          ← outer loop (runs forever until stop())
      msg = bus.poll(timeout=0.5)          ← POLLING state
      if msg is None: continue             ← no work, re-check _running
      valid = guardrails.check(msg)        ← VALIDATING state
      if not valid: reject(msg); continue  ← REJECT → back to top
      action = lm.generate(msg)            ← THINKING state
      if action == TOOL:   execute(action) ← EXECUTING → RESPONDING
      if action == DELEGATE: forward(action) ← DELEGATING → back to top
      if action == RESPONSE: reply(action) ← RESPONDING → back to top
```

---

## File Reference

### `main.py`
The **orchestrator** — the "hospital administrator" who sets up the building (bus), hires the doctors (agents), tells them their specialties (domains), and then walks in patients (tasks). It runs 4 scenarios that demonstrate: a direct task, a delegation, a recall via delegation, and a direct memory query. This is the file you run first to see the system work end-to-end.

### `harness/envelope.py`
The **message format** — every piece of communication between agents is wrapped in a `MessageEnvelope`. Think of it as a standard postal form: sender, recipient, subject, payload, timestamp, and a correlation ID (so you can match a reply to its original request). Without this standardization, agents would need to know each other's internal data formats — with it, they only need to understand the envelope structure.

### `harness/message_bus.py`
The **communication infrastructure** — an in-memory pub/sub system built on `queue.Queue`. Each registered agent gets their own FIFO queue (mailbox). `publish()` drops a letter in the recipient's mailbox (non-blocking). `poll()` checks your mailbox, waiting up to a timeout for something to arrive. This is the simplest possible message bus — no network, no serialization, no broker process. Just Python objects in memory. In production, this would be Redis, RabbitMQ, or Kafka. The *concept* is identical.

### `harness/dispatcher.py`
The **routing brain** — knows which agent handles which domain. When a task arrives, it scans for keywords ("add" → math, "store" → memory) and publishes the message to the right agent's inbox. This is the component that makes the system *extensible*: to add a third agent (say, a "file_agent"), you just call `dispatcher.register_domain("files", "file_agent")` — no existing code changes.

### `harness/simulated_lm.py`
The **fake brain** — replaces a real LLM with deterministic keyword rules. It knows its own domain and makes three possible decisions: call a tool, delegate to another agent, or respond directly. This is the file you'd swap out for a real API call (OpenAI, Anthropic, etc.) in production. The interface is identical: `generate(task, context) → action_string`. Everything else in the system works unchanged. **This is the core lesson from Module #0 made concrete.**

### `harness/guardrails.py`
The **safety net** — validates every incoming task before it reaches the LM or tools. Checks for: non-string types, excessive length, empty content, and injection patterns (`__import__`, `os.system`, `eval(`, etc.). If validation fails, the task is rejected with a clear error message and never touches the "brain." This is your first line of defense against prompt injection and resource abuse.

### `harness/agent.py`
The **autonomous entity** — combines all the above into a single runnable unit with its own thread. Its loop is: poll inbox → validate → think (LM) → act (tool or delegate) → respond. It survives tool failures, malformed LM output, and invalid inputs without crashing. The `messages_processed` counter and trace logger give you observability into what the agent actually did.

### `harness/trace_logger.py`
The **flight recorder** — logs every significant event with ANSI colors so you can see at a glance what's happening: green = healthy loop, cyan = thinking/messaging, yellow = tool action, red = blocked/error. After execution, `report()` prints a timestamped summary showing the full conversation between agents. This is how you debug "why did the agent do that?" — just read the trace.

### `test_adversarial.py`
The **torture test** — proves the system doesn't crash under failure conditions. Five tests: (1) a broken LM returning garbage, (2) hostile inputs (injection, oversized, empty), (3) a tool that raises an exception, (4) an infinite delegation loop hitting the iteration cap, (5) sending a message to an unregistered agent. If all 5 pass, you know the harness is robust enough to handle real-world messiness.

---

## What This Teaches

| Concept                                  | Where to Look                                                                                                 | Key Insight                                                                                                                                                                                       |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Message passing**                      | `message_bus.py` → `publish()` / `poll()`                                                                     | Agents never call each other directly. They drop messages in mailboxes. This *decoupling* is what makes systems scalable — add more agents without touching existing ones.                        |
| **Delegation**                           | `agent.py` → `_delegate()` + `simulated_lm.py` → `_should_delegate()`                                         | The decision to delegate comes from the "brain" (LM). The act of delegating is just publishing a message. In production, the LM decides; here, keywords decide. Same pattern.                     |
| **Domain routing**                       | `dispatcher.py` → `route()` + `_detect_domain()`                                                              | A central registry maps domains to agents. New capability = new registration line. This is how MCP (Module #2) generalizes the idea to *external* tool servers.                                   |
| **Concurrency without frameworks**       | `agent.py` → `start()` / `_run_loop()`                                                                        | Each agent is a thread polling a queue. No asyncio, no Celery, no gRPC. Just `threading.Thread` + `queue.Queue`. The complexity of "distributed systems" starts here — in your own process.       |
| **Fire-and-forget vs. request-response** | `agent.py` → `_delegate()` (no wait) vs. `_send_response()` (reply arrives later)                             | Delegation is async at the message level. The sender doesn't block. The response is a *separate* message that arrives on a future loop iteration. This is exactly how HTTP, Kafka, and AMQP work. |
| **Guardrails before intelligence**       | `guardrails.py` → `validate_input()` called BEFORE `lm.generate()`                                            | Safety checks run before the "brain" sees anything. A bad input never reaches the LM or tools. This ordering (validate → think → act) is a universal pattern in agent design.                     |
| **Swappable brains**                     | `simulated_lm.py` — replace with any function that returns `"TOOL:..."` / `"DELEGATE:..."` / `"RESPONSE:..."` | The entire multi-agent infrastructure works with ANY decision-maker. Keywords today, GPT-4 tomorrow, a rules engine next week. The harness doesn't care.                                          |
| **Observability**                        | `trace_logger.py` → colored output + `report()`                                                               | You can't debug what you can't see. Every state transition is logged. The trace report shows the full conversation with timestamps — like reading a phone call transcript between two agents.     |

---

## How This Connects to the Next Module

In **Module #2 (ToyMCP)**, the Dispatcher's "domain map" gets replaced by a **protocol** (JSON-RPC). Instead of hardcoding which agent handles which domain, the agent *discovers* available tools from external servers at runtime. The message bus pattern stays — only the discovery mechanism changes.

Think of it this way:
- **Module #1 (this):** The hospital has 2 doctors. The receptionist knows their specialties by heart.
- **Module #2:** The hospital has a *directory service*. New doctors can register themselves, and the receptionist looks them up dynamically. No need to retrain the receptionist when a new specialist joins.

---

## Parent Curriculum

Part of the **TOYAGENTS** series — standalone toy projects that isolate one agentic AI concept each.

👉 [https://github.com/AlexOcculate/TOYAGENTS](https://github.com/AlexOcculate/TOYAGENTS)