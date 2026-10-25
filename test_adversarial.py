# Line 1:  Import sys and os for path setup (ensures Harness/ is importable from this file's location).
import sys, os  # Line 2:  Add the script's directory to sys.path so imports work regardless of CWD.

sys.path.insert(
    0, os.path.dirname(os.path.abspath(__file__))
)  # Line 3:  Makes "from Harness..." and "from main import ..." work.

# Line 5:  Import time for sleep calls between async operations in tests.
import time  # Line 6:  (blank line)

# Line 8:  Import the module's main components under test.
from Harness.message_bus import (
    MessageBus,
)  # Line 9:  The bus we'll stress-test with malformed messages.
from Harness.dispatcher import (
    Dispatcher,
)  # Line 10:  Test routing logic with edge cases.
from Harness.agent import (
    Agent,
)  # Line 11:  The agent itself — test its resilience to bad inputs.
from Harness.guardrails import (
    Guardrails,
)  # Line 12:  Test that guardrails actually block bad input.
from Harness.simulated_lm import (
    SimulatedLM,
)  # Line 13:  Test the LM with garbage inputs.
from main import (
    create_math_tools,
    create_memory_tools,
)  # Line 14:  Reuse the same tool factories as main.py for consistency.


# ──────────────────────────────────────────────
#  TEST 1: Broken / Chaotic LM
#  Proves: the system doesn't crash on malformed output
# ──────────────────────────────────────────────
def test_broken_lm():  # Line 20:  Feed garbage responses from a mock LM. System must not raise any exception.
    """Feed garbage responses. System must not raise."""
    # Line 23:  Create a fresh bus and dispatcher for isolation (each test gets its own system).
    bus = MessageBus()  # Line 24:  Isolated bus — no cross-test contamination.
    dispatcher = Dispatcher(
        bus
    )  # Line 25:  Fresh dispatcher with no domains registered yet.
    # Line 26:  Register a minimal domain so the agent can start without errors.
    dispatcher.register_domain(
        "math", "broken_agent"
    )  # Line 27:  We need at least one domain for the agent to function.
    # Line 28:  Create an agent with a BROKEN LM (we'll monkey-patch its generate method).
    agent = Agent(  # Line 29:  Standard construction — we'll break it after creation.
        agent_id="broken_agent",  # Line 30:  (blank line)
        domain="math",  # Line 31:  (blank line)
        tools=create_math_tools(),  # Line 32:  Normal tools — the problem is in the LM, not the tools.
        bus=bus,  # Line 33:  (blank line)
        dispatcher=dispatcher,  # Line 34:  (blank line)
    )  # Line 35:  Close constructor.

    # Line 36:  Monkey-patch the LM's generate method to return garbage strings.
    def broken_generate(
        task, context
    ):  # Line 37:  This simulates an LLM that produces malformed output.
        # Line 38:  Return a string that doesn't match any expected format (TOOL/DELEGATE/RESPONSE).
        return "COMPLETE GARBAGE ### $$$$ ??? not a valid action"  # Line 39:  The agent should log a warning and send an error, NOT crash.

    # Line 40:  Replace the agent's LM generate method with our broken version.
    agent.lm.generate = broken_generate  # Line 41:  Python allows attribute assignment on instances — this is our "fault injection."
    # Line 42:  Register the agent on the bus and start it.
    bus.register("broken_agent")  # Line 43:  Must register before sending messages.
    agent.start()  # Line 44:  Start the broken agent's thread.
    time.sleep(0.1)  # Line 45:  Give the thread time to start polling.
    # Line 46:  Send a normal task — the broken LM will produce garbage, but the agent must survive.
    agent.send_task(
        "add 2 and 2"
    )  # Line 47:  This should trigger the "unrecognized action" path in handle_message.
    time.sleep(0.5)  # Line 48:  Wait for the agent to process (and not crash).
    # Line 49:  Stop the agent cleanly.
    agent.stop()  # Line 50:  If we get here without an exception, the test passes.
    # Line 51:  Assert that the agent processed at least one message (proving it didn't crash on the first iteration).
    assert (
        agent.messages_processed >= 1
    ), f"Agent should have processed at least 1 message, got {agent.messages_processed}"  # Line 52:  This proves the loop continued past the garbage LM output.


# ──────────────────────────────────────────────
#  TEST 2: Invalid / Hostile Input
#  Proves: guardrails block bad input before it reaches the core
# ──────────────────────────────────────────────
def test_hostile_input():  # Line 58:  Oversized, empty, or forbidden-pattern inputs must be blocked by guardrails.
    """Oversized, empty, or forbidden-pattern inputs must be blocked."""
    # Line 61:  Create guardrails with tight limits for testing.
    gr = Guardrails(
        max_iterations=5, max_input_length=50
    )  # Line 62:  Small max_input_length makes it easy to trigger the length check.
    # Line 63:  Test 2a: Oversized input should be blocked.
    oversized = "A" * 1000  # Line 64:  1000 characters exceeds our 50-char limit.
    valid, reason = gr.validate_input(
        oversized
    )  # Line 65:  Run validation on the oversized string.
    assert (
        not valid
    ), "Oversized input should be rejected"  # Line 66:  If it's not rejected, guardrails are broken.
    assert (
        "too long" in reason.lower()
    ), f"Reason should mention length, got: {reason}"  # Line 67:  Verify the rejection reason is specific (helps debugging).
    # Line 68:  Test 2b: Empty input should be blocked.
    valid, reason = gr.validate_input(
        ""
    )  # Line 69:  Empty string has no content to process.
    assert not valid, "Empty input should be rejected"  # Line 70:  (blank line)
    # Line 71:  Test 2c: Whitespace-only input should be blocked.
    valid, reason = gr.validate_input(
        "   \t\n  "
    )  # Line 72:  Looks like it has content but doesn't.
    assert (
        not valid
    ), "Whitespace-only input should be rejected"  # Line 73:  (blank line)
    # Line 74:  Test 2d: Injection pattern should be blocked.
    injection = "add 1 and __import__('os').system('rm -rf /')"  # Line 75:  Classic Python code injection attempt.
    valid, reason = gr.validate_input(
        injection
    )  # Line 76:  The guardrails should catch "__import__" in the forbidden patterns.
    assert (
        not valid
    ), "Injection pattern should be rejected"  # Line 77:  If this passes validation, we have a security hole.
    assert (
        "forbidden" in reason.lower()
    ), f"Reason should mention forbidden pattern, got: {reason}"  # Line 78:  (blank line)
    # Line 79:  Test 2e: Non-string input should be blocked.
    valid, reason = gr.validate_input(
        12345
    )  # Line 80:  An integer is not a valid task string.
    assert not valid, "Non-string input should be rejected"  # Line 81:  (blank line)
    # Line 82:  Test 2f: Normal input should PASS validation (positive control).
    valid, reason = gr.validate_input(
        "add 5 and 3"
    )  # Line 83:  A perfectly normal task must not be blocked.
    assert (
        valid
    ), f"Normal input should pass validation, got: {reason}"  # Line 84:  If this fails, guardrails are too aggressive (false positives).


# ──────────────────────────────────────────────
#  TEST 3: Tool Execution Failure
#  Proves: a failing tool doesn't crash the loop; error is handled
# ─────────────────-----------------------------
