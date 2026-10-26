# Line 1:  Import sys and os for path setup (ensures Harness/ is importable from this file's location).
import sys, os  # Line 2:  Add the script's directory to sys.path so imports work regardless of CWD.

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# LINE 3:  Makes "from Harness..." and "from main import ..." work.

# Line 5:  Import time for sleep calls between async operations in tests.
import time

# Line 8:  Import the module's main components under test.
from Harness.message_bus import (
    MessageBus,
)

# LINE 9:  The bus we'll stress-test with malformed messages.
from Harness.dispatcher import (
    Dispatcher,
)

# LINE 10:  Test routing logic with edge cases.
from Harness.agent import (
    Agent,
)

# LINE 11:  The agent itself — test its resilience to bad inputs.
from Harness.guardrails import (
    Guardrails,
)

# LINE 12:  Test that guardrails actually block bad input.
from Harness.simulated_lm import (
    SimulatedLM,
)

# LINE 13:  Test the LM with garbage inputs.
from Harness.envelope import (
    MessageEnvelope,
)

# LINE 14:  Needed to craft malformed envelopes directly.
from main import (
    create_math_tools,
    create_memory_tools,
)

# LINE 15:  Reuse the same tool factories as main.py for consistency.


# ──────────────────────────────────────────────
#  TEST 1: Broken / Chaotic LM
#  Proves: the system doesn't crash on malformed output
# ──────────────────────────────────────────────
def test_broken_lm():  # Line 21:  Feed garbage responses from a mock LM. System must not raise any exception.
    """Feed garbage responses. System must not raise."""
    # Line 24:  Create a fresh bus and dispatcher for isolation (each test gets its own system).
    bus = MessageBus()
    # LINE 25:  Isolated bus — no cross-test contamination.
    dispatcher = Dispatcher(bus)
    # LINE 26:  Fresh dispatcher with no domains registered yet.
    # Line 27:  Register a minimal domain so the agent can start without errors.
    dispatcher.register_domain("math", "broken_agent")
    # LINE 28:  We need at least one domain for the agent to function.
    # Line 29:  Create an agent with a BROKEN LM (we'll monkey-patch its generate method).
    agent = Agent(  # Line 30:  Standard construction — we'll break it after creation.
        agent_id="broken_agent",
        domain="math",
        tools=create_math_tools(),  # Line 33:  Normal tools — the problem is in the LM, not the tools.
        bus=bus,
        dispatcher=dispatcher,
    )
    # LINE 36:  Close constructor.

    # Line 37:  Monkey-patch the LM's generate method to return garbage strings.
    def broken_generate(
        task, context
    ):  # Line 38:  This simulates an LLM that produces malformed output.
        # Line 39:  Return a string that doesn't match any expected format (TOOL/DELEGATE/RESPONSE).
        return "COMPLETE GARBAGE ### $$$$ ??? not a valid action"  # Line 40:  The agent should log a warning and send an error, NOT crash.

    # Line 41:  Replace the agent's LM generate method with our broken version.
    agent.lm.generate = broken_generate  # Line 42:  Python allows attribute assignment on instances — this is our "fault injection."
    # Line 43:  Register the agent on the bus and start it.
    bus.register("broken_agent")
    # LINE 44:  Must register before sending messages.
    bus.register("user")
    # LINE 45:  Register user so error responses aren't dropped (prevents bus warnings).
    agent.start()
    # LINE 46:  Start the broken agent's thread.
    time.sleep(0.1)
    # LINE 47:  Give the thread time to start polling.
    # Line 48:  Send a normal task — the broken LM will produce garbage, but the agent must survive.
    agent.send_task("add 2 and 2")
    # LINE 49:  This should trigger the "unrecognized action" path in handle_message.
    time.sleep(0.5)
    # LINE 50:  Wait for the agent to process (and not crash).
    # Line 51:  Stop the agent cleanly.
    agent.stop()
    # LINE 52:  If we get here without an exception, the test passes.
    # Line 53:  Assert that the agent processed at least one message (proving it didn't crash on the first iteration).
    assert (
        agent.messages_processed >= 1
    ), f"Agent should have processed at least 1 message, got {agent.messages_processed}"  # Line 54:  This proves the loop continued past the garbage LM output.


# ──────────────────────────────────────────────
#  TEST 2: Invalid / Hostile Input
#  Proves: guardrails block bad input before it reaches the core
# ──────────────────────────────────────────────
def test_hostile_input():  # Line 60:  Oversized, empty, or forbidden-pattern inputs must be blocked by guardrails.
    """Oversized, empty, or forbidden-pattern inputs must be blocked."""
    # Line 63:  Create guardrails with tight limits for testing.
    gr = Guardrails(max_iterations=5, max_input_length=50)
    # LINE 64:  Small max_input_length makes it easy to trigger the length check.
    # Line 65:  Test 2a: Oversized input should be blocked.
    oversized = "A" * 1000  # Line 66:  1000 characters exceeds our 50-char limit.
    valid, reason = gr.validate_input(oversized)
    # LINE 67:  Run validation on the oversized string.
    assert (
        not valid
    ), "Oversized input should be rejected"  # Line 68:  If it's not rejected, guardrails are broken.
    assert (
        "too long" in reason.lower()
    ), f"Reason should mention length, got: {reason}"  # Line 69:  Verify the rejection reason is specific (helps debugging).
    # Line 70:  Test 2b: Empty input should be blocked.
    valid, reason = gr.validate_input("")
    # LINE 71:  Empty string has no content to process.
    assert not valid, "Empty input should be rejected"
    # Line 73:  Test 2c: Whitespace-only input should be blocked.
    valid, reason = gr.validate_input("   \t\n  ")
    # LINE 74:  Looks like it has content but doesn't.
    assert not valid, "Whitespace-only input should be rejected"
    # Line 76:  Test 2d: Injection pattern should be blocked.
    injection = "add 1 and __import__('os').system('rm -rf /')"  # Line 77:  Classic Python code injection attempt.
    valid, reason = gr.validate_input(injection)
    # LINE 78:  The guardrails should catch "__import__" in the forbidden patterns.
    assert (
        not valid
    ), "Injection pattern should be rejected"  # Line 79:  If this passes validation, we have a security hole.
    assert (
        "forbidden" in reason.lower()
    ), f"Reason should mention forbidden pattern, got: {reason}"
    # Line 81:  Test 2e: Non-string input should be blocked.
    valid, reason = gr.validate_input(12345)
    # LINE 82:  An integer is not a valid task string.
    assert not valid, "Non-string input should be rejected"
    # Line 84:  Test 2f: Normal input should PASS validation (positive control).
    valid, reason = gr.validate_input("add 5 and 3")
    # LINE 85:  A perfectly normal task must not be blocked.
    assert (
        valid
    ), f"Normal input should pass validation, got: {reason}"  # Line 86:  If this fails, guardrails are too aggressive (false positives).


# ──────────────────────────────────────────────
#  TEST 3: Tool Execution Failure
#  Proves: a failing tool doesn't crash the loop; error is handled
# ──────────────────────────────────────────────
def test_tool_failure():  # Line 92:  A tool that raises must be caught and reported, not propagated.
    """A tool that raises must be caught and reported, not propagated."""
    # Line 95:  Create a bus and dispatcher for isolation.
    bus = MessageBus()

    dispatcher = Dispatcher(bus)

    dispatcher.register_domain("math", "failing_agent")
    # LINE 98:  Register the domain so routing works.

    # Line 99:  Create a tool registry where the "add" tool always raises an exception.
    def exploding_add(
        a, b
    ):  # Line 100:  This tool simulates a crash (e.g., division by zero, DB connection lost).
        # Line 101:  Always raise — this is our fault injection.
        raise RuntimeError("Simulated tool crash: database connection lost")

    # LINE 102:  A realistic error message to verify it appears in the response.

    # Line 103:  Build a tools dict with the exploding tool.
    bad_tools = {"add": exploding_add}  # Line 104:  Only one tool, and it always fails.
    # Line 105:  Create an agent with the failing tool.
    agent = Agent(
        agent_id="failing_agent",
        domain="math",
        tools=bad_tools,  # Line 109:  Inject the broken tool registry.
        bus=bus,
        dispatcher=dispatcher,
    )
    # LINE 112:  Close constructor.
    # Line 113:  Register on bus and start.
    bus.register("failing_agent")

    bus.register("user")
    # LINE 115:  So error responses don't get dropped.
    agent.start()

    time.sleep(0.1)
    # LINE 117:  Let the thread start.
    # Line 118:  Send a task that will trigger the exploding tool.
    agent.send_task("add 1 and 1")
    # LINE 119:  The LM will say "TOOL: add", which will raise RuntimeError.
    time.sleep(0.5)
    # LINE 120:  Wait for processing.
    # Line 121:  Stop the agent.
    agent.stop()
    # LINE 122:  If we get here, the agent survived the tool crash.
    # Line 123:  Assert the agent processed the message (it handled the error internally).
    assert (
        agent.messages_processed >= 1
    ), f"Agent should have processed 1 message despite tool failure, got {agent.messages_processed}"  # Line 124:  The loop must continue after a tool exception.


# ──────────────────────────────────────────────
#  TEST 4: Infinite Loop / Max Iterations
#  Proves: the iteration guardrail stops runaway loops
# ──────────────────────────────────────────────
def test_infinite_loop():  # Line 130:  An LM that always delegates must eventually be stopped by the iteration cap.
    """An LM that always calls a tool must hit the iteration cap."""
    # Line 133:  Create a bus and dispatcher.
    bus = MessageBus()

    dispatcher = Dispatcher(bus)

    dispatcher.register_domain("math", "loop_agent")

    # Line 137:  Create an agent with a normal tool set.
    agent = Agent(
        agent_id="loop_agent",
        domain="math",
        tools=create_math_tools(),  # Line 141:  Normal tools — the problem is the LM keeps delegating.
        bus=bus,
        dispatcher=dispatcher,
    )
    # LINE 144:  Close constructor.

    # Line 145:  Monkey-patch the LM to ALWAYS return a delegation (simulating a runaway agent).
    def always_delegate(
        task, context
    ):  # Line 146:  This simulates an LLM that can't decide and keeps forwarding.
        # Line 147:  Always delegate — this would create an infinite ping-pong between agents without a cap.
        return "DELEGATE: loop_agent"  # Line 148:  Delegate to itself! This is the worst case — self-delegation loop.

    # Line 149:  Replace the LM with our infinite-loop version.
    agent.lm.generate = always_delegate
    # Line 151:  Reduce the max_iterations to a small number so the test runs fast.
    agent.guardrails.max_iterations = (
        3  # Line 152:  After 3 iterations, the guardrail should stop the loop.
    )
    # Line 153:  Register and start.
    bus.register("loop_agent")

    bus.register("user")

    agent.start()

    time.sleep(0.1)
    # LINE 157:  Let the thread start.
    # Line 158:  Send a task — the agent will delegate to itself repeatedly until the cap is hit.
    agent.send_task("add 1 and 1")
    # LINE 159:  This triggers the infinite delegation loop.
    time.sleep(2.0)
    # LINE 160:  Wait long enough for several iterations to occur (and the cap to be hit).
    # Line 161:  Stop the agent.
    agent.stop()
    # LINE 162:  Must not hang — the thread should be stoppable even after a loop.
    # Line 163:  Assert that the agent did NOT process an unreasonably large number of messages.
    #   With max_iterations=3, it should process at most a handful before the guardrail kicks in.
    assert (
        agent.messages_processed < 20
    ), f"Agent processed {agent.messages_processed} messages — iteration cap may not be working (expected < 20)"  # Line 165:  The exact number depends on timing, but it must be bounded, not infinite.


# ──────────────────────────────────────────────
#  TEST 5: Message to Unknown Agent (module-specific)
#  Proves: sending a message to an unregistered agent doesn't crash the system
# ──────────────────────────────────────────────
def test_module_specific():  # Line 171:  Publishing to an unregistered agent ID must not crash the bus or any agent.
    """Message to unknown agent (should error gracefully)."""
    # Line 174:  Create a bus with only ONE registered agent.
    bus = MessageBus()

    dispatcher = Dispatcher(bus)

    dispatcher.register_domain("math", "known_agent")
    # LINE 177:  Only "known_agent" will be registered.
    # Line 178:  Create the known agent.
    agent = Agent(
        agent_id="known_agent",
        domain="math",
        tools=create_math_tools(),
        bus=bus,
        dispatcher=dispatcher,
    )
    # LINE 185:  Close constructor.
    # Line 186:  Register ONLY the known agent on the bus.
    bus.register("known_agent")
    # LINE 187:  "ghost_agent" is intentionally NOT registered.
    # Line 188:  Start the known agent.
    agent.start()

    time.sleep(0.1)
    # LINE 190:  Let it start polling.
    # Line 191:  Now try to publish a message directly to an UNREGISTERED agent.
    ghost_envelope = MessageEnvelope(  # Line 192:  Craft a message addressed to "ghost_agent" which doesn't exist.
        sender_id="known_agent",  # Line 193:  The known agent is the sender.
        recipient_id="ghost_agent",  # Line 194:  This agent was never registered on the bus.
        subject="task",
        payload={
            "task": "add 1 and 2"
        },  # Line 196:  A normal task, but it will be dropped by the bus.
    )
    # LINE 197:  Close constructor.
    # Line 198:  Publish to the ghost — the bus should warn and drop, NOT raise an exception.
    bus.publish(ghost_envelope)
    # LINE 199:  This must not crash. The bus prints a WARNING and returns.
    # Line 200:  Also test: what if we try to poll an unregistered agent?
    result = bus.poll("ghost_agent", timeout=0.1)
    # LINE 201:  Polling an unregistered agent should return None, not raise.
    assert (
        result is None
    ), f"Polling unregistered agent should return None, got: {result}"
    # Line 203:  Verify the known agent is still alive and functional after the ghost publish.
    agent.send_task("add 5 and 5")
    # LINE 204:  Send a normal task to the known agent.
    time.sleep(0.5)
    # LINE 205:  Wait for processing.
    # Line 206:  Stop the agent.
    agent.stop()

    # Line 208:  Assert the known agent still processed its task normally (wasn't affected by the ghost).
    assert (
        agent.messages_processed >= 1
    ), f"Known agent should still work after ghost publish, got {agent.messages_processed} messages"  # Line 209:  The system is resilient — one bad message doesn't take down healthy agents.


# ──────────────────────────────────────────────
#  RUNNER
# ──────────────────────────────────────────────
if (
    __name__ == "__main__"
):  # Line 215:  Only run tests when this file is executed directly (not imported).
    # Line 216:  Print a header to identify the test suite.
    print("\n" + "=" * 60)
    # LINE 217:  Visual separator.
    # Line 218:  Title for the adversarial test run.
    print("  TOYAGENTS #1 — ToyA2A: Adversarial Tests")
    # LINE 219:  Identifies which module's tests are running.
    # Line 220:  Print separator.
    print("=" * 60 + "\n")

    # Line 222:  Define the list of tests to run, in order.
    tests = [  # Line 223:  Each entry is a (display_name, test_function) tuple.
        (
            "Broken LM / Chaotic output",
            test_broken_lm,
        ),  # Line 224:  Test 1: garbage LM output doesn't crash the agent.
        (
            "Hostile / Invalid input",
            test_hostile_input,
        ),  # Line 225:  Test 2: guardrails block bad inputs.
        (
            "Tool execution failure",
            test_tool_failure,
        ),  # Line 226:  Test 3: a crashing tool doesn't kill the loop.
        (
            "Infinite loop / Max iterations",
            test_infinite_loop,
        ),  # Line 227:  Test 4: runaway delegation is capped.
        (
            "Message to unknown agent",
            test_module_specific,
        ),  # Line 228:  Test 5: publishing to a ghost agent is handled gracefully.
    ]  # Line 229:  Close the list.
    # Line 230:  Counter for passed tests.
    passed = 0  # Line 231:  Incremented for each test that doesn't raise an exception.
    # Line 232:  Iterate through all tests and run them.
    for (
        name,
        fn,
    ) in tests:  # Line 233:  Unpack the tuple into the display name and the callable.
        # Line 234:  Wrap each test in try/except so one failure doesn't prevent others from running.
        try:
            # Line 236:  Execute the test function. If it raises, we catch it below.
            fn()
            # LINE 237:  The test either passes (no exception) or fails (assertion/exception raised).
            # Line 238:  Print a PASS line with the test name.
            print(f"  \033[92mPASS\033[0m  {name}")
            # LINE 239:  Green "PASS" for visual clarity in terminal.
            # Line 240:  Increment the passed counter.
            passed += 1
        except (
            Exception
        ) as e:  # Line 242:  Catch ANY exception — assertion errors, runtime errors, etc.
            # Line 243:  Print a FAIL line with the test name and the error message.
            print(f"  \033[91mFAIL\033[0m  {name}: {type(e).__name__}: {e}")
    # LINE 244:  Red "FAIL" + exception type + message for quick diagnosis.
    # Line 245:  Print a final summary line.
    print(f"\n  {passed}/{len(tests)} tests passed.")
    # LINE 246:  At-a-glance result (e.g., "5/5 tests passed.").
    # Line 247:  If any test failed, exit with a non-zero code (useful for CI pipelines).
    if passed < len(
        tests
    ):  # Line 248:  Non-zero exit signals failure to shell scripts and CI systems.
        # Line 249:  Exit with code 1 (conventional "failure" exit code).
        sys.exit(1)
    # LINE 250:  The script ends here without further output.
    # Line 251:  All tests passed — implicit exit with code 0 (success).
    print(f"\n  \033[92mAll adversarial tests passed.\033[0m")
# LINE 252:  Green confirmation message for the developer.
