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

    def __init__(
        self, max_iterations: int = 10, max_input_length: int = 500
    ):  # Line 15:  Configure the limits that define "safe" behavior.
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

    def validate_input(
        self, text: str
    ) -> tuple:  # Line 30:  Check an input string against all guardrail rules.
        """Returns (is_valid: bool, reason: str). If invalid, reason explains why."""
        # Line 33:  First check: is the input even a string? (Defensive — could be None or int from bad code.)
        if not isinstance(
            text, str
        ):  # Line 34:  Non-string inputs are always rejected — we don't know how to validate them.
            # Line 35:  Return failure with a clear reason for debugging.
            return (
                False,
                f"Input is not a string (got {type(text).__name__})",
            )  # Line 36:  Type name helps the developer identify where the bad data came from.
        # Line 37:  Second check: length limit.
        if (
            len(text) > self.max_input_length
        ):  # Line 38:  Inputs longer than the cap are almost certainly accidental or malicious.
            # Line 39:  Return failure with the actual vs. allowed length for context.
            return (
                False,
                f"Input too long: {len(text)} chars (max {self.max_input_length})",
            )  # Line 40:  Showing both numbers makes it easy to tune the limit if needed.
        # Line 41:  Third check: empty or whitespace-only input.
        if (
            not text.strip()
        ):  # Line 42:  An empty string has no semantic content — processing it would waste a loop iteration.
            # Line 43:  Return failure for empty input.
            return (
                False,
                "Input is empty or whitespace-only",
            )  # Line 44:  (blank line)
        # Line 45:  Fourth check: scan for forbidden patterns (injection attempts).
        for (
            pattern
        ) in (
            self._forbidden_patterns
        ):  # Line 46:  Check each dangerous pattern against the input.
            # Line 47:  Use re.search with IGNORECASE so "OS.SYSTEM" is caught too.
            if re.search(
                pattern, text, re.IGNORECASE
            ):  # Line 48:  If any forbidden pattern matches, this input is BLOCKED immediately.
                # Line 49:  Return failure identifying which pattern triggered the block.
                return (
                    False,
                    f"Forbidden pattern detected: {pattern}",
                )  # Line 50:  Showing the pattern helps developers understand what was flagged.
        # Line 51:  All checks passed — the input is safe to process.
        return (
            True,
            "OK",
        )  # Line 52:  "OK" is a conventional success marker that's easy to grep in logs.

    def check_iteration(
        self, current: int
    ) -> (
        bool
    ):  # Line 54:  Check whether we've exceeded the maximum allowed loop iterations.
        """Returns True if we should STOP (limit reached), False if we can continue."""
        # Line 57:  If current iteration count meets or exceeds the cap, we must stop.
        return (
            current >= self.max_iterations
        )  # Line 58:  Using >= (not >) means the agent gets exactly max_iterations chances, not max+1.
