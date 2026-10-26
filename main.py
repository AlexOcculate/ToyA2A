# Line 1:  Import sys and os for path setup (ensures Harness/ is importable regardless of CWD).
import sys, os  # Line 2:  Add the script's directory to sys.path so "from Harness..." works.

sys.path.insert(
    0, os.path.dirname(os.path.abspath(__file__))
)  # Line 3:  This makes the module runnable from any working directory.

# Line 5:  Import time for sleep calls in the demo (giving agents time to process).
import time  #

# Line 8:  Import all Harness components needed to wire up the system.
from Harness.message_bus import MessageBus  # Line 9:  The central communication hub.
from Harness.dispatcher import (
    Dispatcher,
)  # Line 10:  Routes tasks to the correct agent by domain.
from Harness.agent import (
    Agent,
)  # Line 11:  The autonomous entity that processes messages.

#


def create_math_tools() -> (
    dict
):  # Line 14:  Factory function that creates and returns the math agent's tool registry.
    """Define the tools available to the math agent as plain Python functions."""

    # Line 17:  Define the add tool — takes two numbers, returns their sum.
    def add(
        a: float, b: float
    ) -> float:  # Line 18:  Simple binary addition with type hints for clarity.
        # Line 19:  Return the arithmetic result.
        return a + b  #

    # Line 21:  Define the subtract tool.
    def subtract(
        a: float, b: float
    ) -> (
        float
    ):  # Line 22:  Returns a minus b (order matters: "subtract 3 from 10" means 10-3).
        # Line 23:  Return the arithmetic result.
        return a - b  #

    # Line 25:  Define the multiply tool.
    def multiply(
        a: float, b: float
    ) -> float:  # Line 26:  Returns the product of two numbers.
        # Line 27:  Return the arithmetic result.
        return a * b  #

    # Line 29:  Return all tools as a name→function mapping for the agent's registry.
    return {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
    }  # Line 30:  The keys must match what SimulatedLM outputs in its TOOL instructions.


def create_memory_tools() -> (
    dict
):  # Line 32:  Factory function that creates and returns the memory agent's tool registry.
    """Define the tools available to the memory agent (simple in-memory key-value store)."""
    # Line 35:  Create a shared dictionary that acts as our "database" for stored values.
    store = (
        {}
    )  # Line 36:  This dict persists for the lifetime of the program (like a real database).

    #
    # Line 38:  Define the memory_store tool — saves a value under a key.
    def memory_store(
        key: str, value: str
    ) -> str:  # Line 39:  Stores a string value under a string key in the shared dict.
        # Line 40:  Assign the value to the key in our in-memory store.
        store[key] = (
            value  # Line 41:  This is the "write" operation — analogous to INSERT or SET in a real DB.
        )
        # Line 42:  Return a confirmation message (the agent will relay this to the user).
        return f"Stored '{value}' under key '{key}'."  # Line 43:  Human-readable confirmation for the trace and user.

    #
    # Line 45:  Define the memory_recall tool — retrieves a value by key.
    def memory_recall(
        key: str,
    ) -> str:  # Line 46:  Looks up a previously stored value by its key.
        # Line 47:  Check if the key exists in our store before trying to access it.
        if (
            key in store
        ):  # Line 48:  Avoids KeyError and gives a friendlier error message.
            # Line 49:  Return the stored value as a string.
            return f"Recalled '{store[key]}' from key '{key}'."  # Line 50:  Includes both the value and the key for clarity.
        # Line 51:  Key not found — return an informative error message (not an exception).
        return f"Key '{key}' not found in memory."  # Line 52:  The agent will relay this to the user as a normal response.

    #
    # Line 54:  Define the memory_list tool — shows all stored keys and values.
    def memory_list() -> (
        str
    ):  # Line 55:  Returns a formatted view of everything currently in memory.
        # Line 56:  If the store is empty, say so clearly.
        if (
            not store
        ):  # Line 57:  Empty dict is falsy — this catches the "nothing stored yet" case.
            # Line 58:  Return a message indicating empty state.
            return "Memory is empty."  #
        # Line 60:  Build a formatted string showing all key-value pairs.
        items = ", ".join(
            f"'{k}'={v}" for k, v in store.items()
        )  # Line 61:  Generator expression keeps this memory-efficient even with many entries.
        # Line 62:  Return the formatted list as a single string response.
        return f"Memory contents: {items}"  #

    # Line 64:  Return all tools as a name→function mapping.
    return {
        "memory_store": memory_store,
        "memory_recall": memory_recall,
        "memory_list": memory_list,
    }  # Line 65:  Keys must match SimulatedLM's TOOL output exactly.


def main():  # Line 67:  Entry point — wires up the system and runs a demo conversation.
    """Set up two agents (math + memory), connect them via a bus, and run demo tasks."""
    # Line 70:  Print a header to identify what's running.
    print("\n" + "=" * 60)  # Line 71:  Visual separator for terminal output.
    # Line 72:  Print the module title.
    print(
        "  TOYAGENTS #1 — ToyA2A: Message Passing + Delegation"
    )  # Line 73:  Identifies which curriculum module is running.
    # Line 74:  Print another separator.
    print("=" * 60 + "\n")  #
    # Line 76:  ─── Step 1: Create the shared infrastructure ──────────────────────
    # Line 77:  Create the message bus — the single communication channel for all agents.
    bus = (
        MessageBus()
    )  # Line 78:  One bus for the entire system (like one postal service for a town).
    # Line 79:  Create the dispatcher and register both domains.
    dispatcher = Dispatcher(
        bus
    )  # Line 80:  The dispatcher needs a reference to the bus to publish messages.
    # Line 81:  Tell the dispatcher that "math" domain is handled by "math_agent".
    dispatcher.register_domain(
        "math", "math_agent"
    )  # Line 82:  This registration enables automatic routing of math tasks.
    # Line 83:  Tell the dispatcher that "memory" domain is handled by "memory_agent".
    dispatcher.register_domain(
        "memory", "memory_agent"
    )  # Line 84:  Now both domains are routable.
    #
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
    #
    # Line 104:  ─── Step 3: Register ALL inboxes on the bus and start threads ─────
    # Line 105:  Register math_agent's inbox on the bus (creates its queue).
    bus.register(
        "math_agent"
    )  # Line 106:  Must be done before any message is sent to this agent.
    # Line 107:  Register memory_agent's inbox on the bus.
    bus.register("memory_agent")  # Line 108:  Now both agents can receive messages.
    # Line 109:  Register "user" on the bus so responses addressed to user are not dropped.
    bus.register(
        "user"
    )  # Line 110:  The "user" is external, but we give it a mailbox so the bus doesn't warn about unknown recipients.
    # Line 111:  Start the math agent's background thread (begins polling its inbox).
    math_agent.start()  # Line 112:  After this, math_agent is "alive" in a separate thread.
    # Line 113:  Start the memory agent's background thread.
    memory_agent.start()  # Line 114:  Both agents are now running concurrently, each polling their own inbox.
    # Line 115:  Small delay to ensure both threads have started before we send tasks.
    time.sleep(
        0.2
    )  # Line 116:  Without this, the first message might arrive before the thread is ready to poll.

    #
    # Line 118:  ─── Step 4: Run demo scenarios ─────────────────────────────────────
    # Line 119:  Helper function to display responses that arrived at the "user" inbox.
    def collect_user_responses(
        label: str,
    ):  # Line 120:  Polls the user's inbox and prints any pending responses.
        """Drain the user's inbox and print each response with a label."""
        # Line 123:  Keep polling until the user's inbox is empty (no more messages).
        while True:  # Line 124:  Loop until we get None (timeout = no more messages).
            # Line 125:  Try to get a message from the user's inbox with a short timeout.
            env = bus.poll(
                "user", timeout=0.3
            )  # Line 126:  0.3s is enough — if nothing arrives in that time, we're done.
            # Line 127:  If no message, break out of the drain loop.
            if env is None:  #
                # Line 129:  Stop draining — inbox is empty.
                break  #
            # Line 131:  Extract the result text from the response payload.
            result = env.payload.get(
                "result", "(no result)"
            )  # Line 132:  .get() with default in case payload is malformed.
            # Line 133:  Print the response with a clear label showing which scenario it belongs to.
            print(
                f"  ✓ {label}: {result}"
            )  # Line 134:  The checkmark makes it visually clear this is a successful result.

    #
    # Line 136:  ─── SCENARIO 1: Direct task (no delegation) ────────────────────────
    # Line 137:  Print a section header for the first scenario.
    print(f"\n{'─'*50}")  # Line 138:  Visual separator between scenarios.
    # Line 139:  Describe what we're about to do.
    print(
        "  SCENARIO 1: Direct task (math_agent handles 'add 5 and 3')"
    )  # Line 140:  This tests the simple path — no delegation needed.
    # Line 141:  Print another separator.
    print(f"{'─'*50}\n")  #
    # Line 143:  Send a math task directly to the math agent.
    math_agent.send_task(
        "add 5 and 3"
    )  # Line 144:  This publishes a message to math_agent's inbox; it will process it asynchronously.
    # Line 145:  Wait for the agents to process (giving them time to complete the round-trip).
    time.sleep(
        1.0
    )  # Line 146:  1 second is more than enough for a simple tool call + response.
    # Line 147:  Collect and display any responses that arrived at the user's inbox.
    collect_user_responses(
        "add 5 and 3"
    )  # Line 148:  Should print "✓ add 5 and 3: 8.0".
    #
    # Line 150:  ─── SCENARIO 2: Delegation (math → memory) ────────────────────────
    # Line 151:  Print header for the second scenario.
    print(f"\n{'─'*50}")  #
    # Line 153:  Describe the delegation scenario.
    print(
        "  SCENARIO 2: Delegation (math_agent delegates 'store 8 as result' to memory_agent)"
    )  # Line 154:  This tests the multi-agent path — math agent can't store, so it delegates.
    # Line 155:  Print separator.
    print(f"{'─'*50}\n")  #
    # Line 157:  Send a memory task to the MATH agent (out-of-domain → triggers delegation).
    math_agent.send_task(
        "store 8 as result"
    )  # Line 158:  The math agent's LM will see "store" and delegate to memory_agent.
    # Line 159:  Wait for the full delegation round-trip (send → receive → process → respond).
    time.sleep(
        2.0
    )  # Line 160:  Delegation takes longer because it involves two agents and two bus hops.
    # Line 161:  Collect responses — the memory_agent's response goes to math_agent,
    #   but math_agent also gets a response from user (the original task sender).
    #   Actually, the response chain is: user→math (task) → math delegates to memory
    #   → memory responds to math. The user never gets a direct response in this case.
    #   We check math_agent's responses list instead.
    if (
        math_agent.responses
    ):  # Line 166:  If the math agent received any responses (from memory_agent), display them.
        # Line 167:  Print each stored response with a label.
        for (
            r
        ) in (
            math_agent.responses
        ):  # Line 168:  Iterate over all responses collected by math_agent.
            # Line 169:  Display the delegated result.
            print(
                f"  ✓ [via delegation] {r}"
            )  # Line 170:  The "[via delegation]" tag makes it clear this went through another agent.
        # Line 171:  Clear the responses list so scenario 3 starts fresh.
        math_agent.responses.clear()  # Line 172:  Prevents cross-scenario contamination of results.
    #
    # Line 174:  ─── SCENARIO 3: Delegation (math → memory, recall) ────────────────
    # Line 175:  Print header for the third scenario.
    print(f"\n{'─'*50}")  #
    # Line 177:  Describe the recall scenario.
    print(
        "  SCENARIO 3: Delegation back (math_agent delegates 'recall result' to memory_agent)"
    )  # Line 178:  Tests that delegation works for read operations too.
    # Line 179:  Print separator.
    print(f"{'─'*50}\n")  #
    # Line 181:  Send a recall task to the math agent (triggers delegation again).
    math_agent.send_task(
        "recall result"
    )  # Line 182:  Memory agent will look up "result" and return "8".
    # Line 183:  Wait for the round-trip.
    time.sleep(2.0)  #
    # Line 185:  Collect and display the delegated recall result.
    if (
        math_agent.responses
    ):  # Line 186:  Check if math_agent got a response from memory_agent.
        # Line 187:  Display each stored response.
        for r in math_agent.responses:  #
            # Line 189:  Print with delegation tag.
            print(f"  ✓ [via delegation] {r}")  #
        # Line 191:  Clear for next scenario.
        math_agent.responses.clear()  #
    #
    # Line 194:  ─── SCENARIO 4: Direct task to memory_agent ───────────────────────
    # Line 195:  Print header for the fourth scenario.
    print(f"\n{'─'*50}")  #
    # Line 197:  Describe a task that goes directly to memory_agent (no delegation).
    print(
        "  SCENARIO 4: Direct task (memory_agent handles 'list all')"
    )  # Line 198:  Tests that direct tasks to memory_agent work without delegation.
    # Line 199:  Print separator.
    print(f"{'─'*50}\n")  #
    # Line 201:  Send a list task directly to the memory agent.
    memory_agent.send_task(
        "list all"
    )  # Line 202:  Memory agent handles this directly — no delegation needed.
    # Line 203:  Wait for processing.
    time.sleep(1.0)  #
    # Line 205:  Collect and display the response from memory_agent to user.
    collect_user_responses(
        "list all"
    )  # Line 206:  Should print "✓ list all: Memory contents: 'result'=8".
    #
    # Line 208:  ─── Step 5: Shutdown and report ───────────────────────────────────
    # Line 209:  Print a final separator before shutdown.
    print(f"\n{'─'*50}")  #
    # Line 211:  Announce that we're shutting down.
    print("  Shutting down agents...")  #
    # Line 213:  Stop the math agent (sets _running=False, joins thread).
    math_agent.stop()  # Line 214:  Graceful shutdown — waits for current operation to complete.
    # Line 215:  Stop the memory agent.
    memory_agent.stop()  #
    # Line 217:  Print a summary of bus statistics.
    # print(
    #     f"\n  Bus statistics: {bus.total_published} messages published to {len(bus.registered_agents())} agents."
    # )  # Line 218:  Quick health check — if this is 0, something went wrong.
    print(
        f"\n  Bus statistics: {bus.total_published} messages published to {len(bus.registered_agents)} agents."
    )
    #
    # Line 220:  Print the full trace report for each agent.
    math_agent.trace.report()  # Line 221:  Shows every event the math agent experienced, with timing.
    # Line 222:  Print the memory agent's trace report.
    memory_agent.trace.report()  # Line 223:  Together, these two reports show the complete multi-agent conversation.


# Line 225:  Standard Python entry point guard — only runs main() when executed directly (not imported).
if (
    __name__ == "__main__"
):  # Line 226:  Allows this file to be imported by test_adversarial.py without triggering the demo.
    # Line 227:  Call the main function to run the demo.
    main()  #
