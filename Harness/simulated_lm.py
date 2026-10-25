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

    def __init__(
        self, domain: str
    ):  # Line 16:  Each LM instance knows its own domain so it can decide when to delegate.
        # Line 17:  Store the domain this agent specializes in ("math" or "memory").
        self.domain = domain  # Line 18:  Used in _should_delegate() to check if a task is out-of-domain.

    def generate(
        self, task: str, context: dict
    ) -> (
        str
    ):  # Line 20:  Main entry point — given a task and context, return an action instruction string.
        """Produce an action string that the agent loop will parse and execute.

        Output format (one of):
          TOOL: <name> | ARGS: {json}    → execute a tool
          DELEGATE: <agent_id>           → forward to another agent
          RESPONSE: <text>               → final answer to return to user
        """
        # Line 29:  Normalize the task text for matching.
        text = (
            task.lower().strip()
        )  # Line 30:  Remove whitespace and lowercase so "Add 5 and 3" matches "add".
        # Line 31:  If this task is outside our domain, immediately delegate.
        if self._should_delegate(
            text
        ):  # Line 32:  This check happens FIRST — we don't waste effort trying to handle what we can't.
            # Line 33:  Determine which agent should handle this (opposite of our domain for this 2-agent toy).
            target = (
                "memory_agent" if self.domain == "math" else "math_agent"
            )  # Line 34:  In a larger system, this would come from the dispatcher's domain map.
            # Line 35:  Return the delegation instruction in the format the agent loop expects to parse.
            return f"DELEGATE: {target}"  # Line 36:  The agent will extract "memory_agent" or "math_agent" from this string.
        # Line 37:  We're in-domain — now figure out which specific tool to call.
        action = self._match_tool(
            text
        )  # Line 38:  This returns a formatted TOOL instruction or None if no tool matches.
        # Line 39:  If a tool matched, return the tool-call instruction.
        if (
            action is not None
        ):  # Line 40:  Non-None means we found a specific tool to execute.
            # Line 41:  Return the formatted instruction for the agent to parse and execute.
            return action  # Line 42:  (blank line)
        # Line 43:  No tool matched — generate a polite refusal response.
        return f"RESPONSE: I ({self.domain}) don't understand that task. Try a {'math' if self.domain == 'memory' else 'memory'} command."  # Line 44:  The response tells the user what domain we handle so they can rephrase.

    def _should_delegate(
        self, text: str
    ) -> bool:  # Line 46:  Check if the task text indicates an out-of-domain request.
        """Return True if the task clearly belongs to a different domain."""
        # Line 49:  Define keywords that signal each domain (same lists as dispatcher for consistency).
        math_keywords = [
            "add",
            "subtract",
            "multiply",
            "sum",
            "difference",
            "product",
        ]  # Line 50:  Mathematical operation indicators.
        memory_keywords = [
            "store",
            "recall",
            "remember",
            "forget",
            "list",
            "save",
            "retrieve",
        ]  # Line 51:  State-management operation indicators.
        # Line 52:  If we're the math agent and the text has memory keywords, delegate.
        if self.domain == "math" and any(
            kw in text for kw in memory_keywords
        ):  # Line 53:  Cross-domain detection — this is the trigger for multi-agent coordination.
            # Line 54:  Signal that delegation is needed.
            return True  # Line 55:  (blank line)
        # Line 56:  If we're the memory agent and the text has math keywords, delegate.
        if self.domain == "memory" and any(
            kw in text for kw in math_keywords
        ):  # Line 57:  Symmetric check — either agent can delegate to the other.
            # Line 58:  Signal that delegation is needed.
            return True  # Line 59:  (blank line)
        # Line 60:  Task is in our domain (or ambiguous) — handle it ourselves.
        return False  # Line 61:  (blank line)

    def _match_tool(
        self, text: str
    ) -> (
        "str | None"
    ):  # Line 63:  Try to match the task text to a specific tool call within our domain.
        """Return a formatted TOOL instruction string, or None if no tool matches."""
        # Line 66:  Extract all numbers from the text (handles integers and simple floats).
        numbers = re.findall(
            r"-?\d+\.?\d*", text
        )  # Line 67:  Regex captures optional negative sign, digits, optional decimal point + digits.
        # Line 68:  If we're the math agent, check for math operations.
        if self.domain == "math":  # Line 69:  Branch into math-specific tool matching.
            # Line 70:  Check for addition (most common — check first).
            if (
                "add" in text or "sum" in text
            ):  # Line 71:  Both "add 5 and 3" and "what is the sum of 5 and 3" should trigger add.
                # Line 72:  We need at least 2 numbers for a binary operation.
                if (
                    len(numbers) >= 2
                ):  # Line 73:  Guard against "add something" with no numbers — would crash the tool.
                    # Line 74:  Convert string numbers to floats for the tool (tools expect numeric args).
                    a, b = float(numbers[0]), float(
                        numbers[1]
                    )  # Line 75:  Take the first two numbers found in the text.
                    # Line 76:  Return the formatted instruction with JSON-encoded arguments.
                    return f'TOOL: add | ARGS: {{"a": {a}, "b": {b}}}'  # Line 77:  The agent loop will json.loads() the ARGS portion to get a dict.
            # Line 78:  Check for subtraction.
            if (
                "subtract" in text or "difference" in text
            ):  # Line 79:  "subtract 10 from 20" or "what is the difference between 20 and 10".
                # Line 80:  Same guard — need two numbers.
                if len(numbers) >= 2:  # Line 81:  (blank line)
                    # Line 82:  Convert to floats.
                    a, b = float(numbers[0]), float(
                        numbers[1]
                    )  # Line 83:  (blank line)
                    # Line 84:  Return subtraction instruction.
                    return f'TOOL: subtract | ARGS: {{"a": {a}, "b": {b}}}'  # Line 85:  (blank line)
            # Line 86:  Check for multiplication.
            if (
                "multiply" in text or "product" in text
            ):  # Line 87:  "multiply 4 by 5" or "what is the product of 4 and 5".
                # Line 88:  Need two numbers.
                if len(numbers) >= 2:  # Line 89:  (blank line)
                    # Line 90:  Convert to floats.
                    a, b = float(numbers[0]), float(
                        numbers[1]
                    )  # Line 91:  (blank line)
                    # Line 92:  Return multiplication instruction.
                    return f'TOOL: multiply | ARGS: {{"a": {a}, "b": {b}}}'  # Line 93:  (blank line)
            # Line 94:  No math tool matched — fall through to None.
            return None  # Line 95:  (blank line)
        # Line 96:  If we're the memory agent, check for memory operations.
        if (
            self.domain == "memory"
        ):  # Line 97:  Branch into memory-specific tool matching.
            # Line 98:  Check for store/save operation.
            if (
                "store" in text or "save" in text or "remember" in text
            ):  # Line 99:  Multiple synonyms for the same operation.
                # Line 100:  Try to extract a key-value pair from the text.
                kv = self._extract_key_value(
                    text
                )  # Line 101:  This parses patterns like "store X as Y" or "save X under Y".
                # Line 102:  If we found a valid key-value pair, create the tool instruction.
                if (
                    kv is not None
                ):  # Line 103:  Non-None means we successfully parsed both key and value.
                    # Line 104:  Unpack the tuple into named variables for clarity.
                    key, value = kv  # Line 105:  (blank line)
                    # Line 106:  Return the store instruction with JSON args.
                    return f'TOOL: memory_store | ARGS: {{"key": "{key}", "value": "{value}"}}'  # Line 107:  Values are stringified — the memory tool stores them as-is.
                # Line 108:  Couldn't parse key-value but keyword matched — use a default pattern.
                return (
                    'TOOL: memory_store | ARGS: {"key": "default", "value": "'
                    + text.replace('"', '\\"')
                    + '"}'
                )  # Line 109:  Fallback: store the entire task text as the value under key "default".
            # Line 110:  Check for recall/retrieve operation.
            if (
                "recall" in text or "retrieve" in text
            ):  # Line 111:  User wants to read back a previously stored value.
                # Line 112:  Try to extract the key they want to recall.
                key = self._extract_key(
                    text
                )  # Line 113:  Parses "recall X" → key = "X".
                # Line 114:  If we found a key, create the recall instruction.
                if key is not None:  # Line 115:  (blank line)
                    # Line 116:  Return the recall instruction.
                    return f'TOOL: memory_recall | ARGS: {{"key": "{key}"}}'  # Line 117:  (blank line)
                # Line 118:  No specific key found — default to "default" key.
                return 'TOOL: memory_recall | ARGS: {"key": "default"}'  # Line 119:  (blank line)
            # Line 120:  Check for list operation.
            if "list" in text:  # Line 121:  User wants to see all stored keys.
                # Line 122:  List takes no arguments — return an empty args object.
                return "TOOL: memory_list | ARGS: {}"  # Line 123:  (blank line)
            # Line 124:  No memory tool matched.
            return None  # Line 125:  (blank line)
        # Line 126:  Unknown domain — should never reach here if _should_delegate worked correctly.
        return None  # Line 127:  Safety net to prevent crashes on unexpected domain values.

    def _extract_key_value(
        self, text: str
    ) -> (
        "tuple | None"
    ):  # Line 129:  Parse "store X as Y" or "save X under Y" patterns into (key, value).
        """Extract a key-value pair from natural language store commands."""
        # Line 132:  Try pattern: "store <value> as <key>" (most common phrasing).
        m = re.search(
            r"(?:store|save|remember)\s+(.+?)\s+(?:as|under)\s+(.+)", text
        )  # Line 133:  Non-greedy (.+?) ensures we capture the shortest match between keywords.
        # Line 134:  If the pattern matched, extract and return the groups.
        if m:  # Line 135:  (blank line)
            # Line 136:  Return (key=group2, value=group1) — note the order swap!
            return (
                m.group(2).strip(),
                m.group(1).strip(),
            )  # Line 137:  "store hello as greeting" → key="greeting", value="hello".
        # Line 138:  Try alternate pattern: "<key> = <value>" or "key: value".
        m2 = re.search(
            r"(\w+)\s*[=:]\s*(.+)", text
        )  # Line 139:  Catches programming-style assignments like "name = Alice".
        # Line 140:  If this pattern matched, return the groups in (key, value) order.
        if m2:  # Line 141:  (blank line)
            # Line 142:  Return with key first, value second (no swap needed here).
            return (m2.group(1).strip(), m2.group(2).strip())  # Line 143:  (blank line)
        # Line 144:  No pattern matched — we can't reliably extract key and value.
        return None  # Line 145:  Caller will use a fallback strategy.

    def _extract_key(
        self, text: str
    ) -> (
        "str | None"
    ):  # Line 147:  Extract just the key from a recall command like "recall greeting".
        """Extract the key name from a recall/retrieve command."""
        # Line 150:  Pattern: "recall <key>" or "retrieve <key>".
        m = re.search(
            r"(?:recall|retrieve)\s+(.+)", text
        )  # Line 151:  Greedy match to capture everything after the verb as the key.
        # Line 152:  If matched, return the captured key string.
        if m:  # Line 153:  (blank line)
            # Line 154:  Strip whitespace and return the key.
            return m.group(1).strip()  # Line 155:  (blank line)
        # Line 156:  No key found in the text.
        return None  # Line 157:  Caller will use a default key.
