# Line 1:  Import time for timestamping trace entries.
import time  # Line 2:  Import typing for the log entry list type hint.
from typing import List, Tuple  # Line 3:  (blank line)

# Line 5:  ─── ANSI Color Codes (no external packages needed) ───────────────────────
# Line 6:  These are escape sequences that terminal emulators interpret as color instructions.
RESET = "\033[0m"  # Line 8:  Resets all formatting back to default — always append after colored text.
BOLD = "\033[1m"  # Line 9:  Makes text bold for emphasis (used on headers).
# Line 10:  Foreground colors for component labels.
RED = (
    "\033[91m"  # Line 11:  Bright red — used for guardrails and errors (danger/safety).
)
GREEN = "\033[92m"  # Line 12:  Bright green — used for loop lifecycle events (healthy operation).
YELLOW = "\033[93m"  # Line 13:  Bright yellow — used for tool execution (action being taken).
BLUE = (
    "\033[94m"  # Line 14:  Bright blue — used for agent A (math_agent) identification.
)
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

    def __init__(
        self, agent_id: str
    ):  # Line 43:  Create a trace logger for a specific agent.
        # Line 44:  Store the agent ID so we can color-code by agent in multi-agent scenarios.
        self.agent_id = agent_id  # Line 45:  Used to select the right agent color (blue for math, magenta for memory).
        # Line 46:  List of all log entries as (timestamp, component, message, level) tuples.
        self.entries: List[Tuple[float, str, str, str]] = (
            []
        )  # Line 47:  Stored in memory for the report() method; also printed live.
        # Line 48:  Determine the color for this agent's name based on its ID.
        self._agent_color = (
            BLUE if "math" in agent_id else MAGENTA
        )  # Line 49:  Simple heuristic — contains "math" → blue, otherwise magenta.

    def log(
        self, component: str, message: str, level: str = "info"
    ) -> None:  # Line 51:  Record and print a single trace entry.
        """Log a colored message tagged with a component name and severity level."""
        # Line 54:  Get the current time for timestamping (monotonic would be better for durations, but wall-clock is more readable).
        ts = (
            time.time()
        )  # Line 55:  Unix timestamp — in report() we'll show relative offsets from start.
        # Line 56:  Look up the color for this component (default to white if unknown).
        color = self.COMPONENT_COLORS.get(
            component, WHITE
        )  # Line 57:  .get() with default prevents KeyError on new/unexpected component names.
        # Line 58:  Determine the color for the level indicator.
        level_color = (
            BG_RED if level == "error" else (BG_YELLOW if level == "warn" else "")
        )  # Line 59:  Errors get red bg, warnings get yellow bg, info gets no special bg.
        # Line 60:  Build the colored output string.
        line = f"{color}[{component}] {self._agent_color}{self.agent_id}{RESET} | {message}"  # Line 61:  Format: [component] agent_id | message, each part in its own color.
        # Line 62:  If there's a level indicator (error/warn), prepend it with background color.
        if level_color:  # Line 63:  Only add the level badge for non-info messages.
            # Line 64:  Insert the colored level tag at the beginning of the message portion.
            line = f"{color}[{component}] {self._agent_color}{self.agent_id}{RESET} | {level_color}{level.upper()}{RESET} {message}"  # Line 65:  Rebuild with the level badge included.
        # Line 66:  Print the colored line to stdout (live output during execution).
        print(
            line
        )  # Line 67:  This gives real-time visibility — you see events as they happen.
        # Line 68:  Store the entry in memory for the final report().
        self.entries.append(
            (ts, component, message, level)
        )  # Line 69:  The stored version is plain (no ANSI codes) for programmatic analysis.

    def report(
        self,
    ) -> (
        None
    ):  # Line 71:  Print a summary report of all logged events after execution completes.
        """Display a formatted summary of the full execution trace."""
        # Line 74:  Print a header to visually separate the report from live output.
        print(f"\n{BOLD}{'='*60}")  # Line 75:  Bold separator line for visual clarity.
        # Line 76:  Print the report title with the agent ID.
        print(
            f"{BOLD}  TRACE REPORT — {self.agent_id}{RESET}"
        )  # Line 77:  Identify which agent this report belongs to.
        # Line 78:  Print another separator.
        print(f"{BOLD}{'='*60}{RESET}\n")  # Line 79:  (blank line)
        # Line 80:  If there are no entries, say so and return.
        if (
            not self.entries
        ):  # Line 81:  Edge case: agent was created but never processed anything.
            # Line 82:  Print a message indicating no activity occurred.
            print("  (no events logged)")  # Line 83:  (blank line)
            # Line 84:  Return early — nothing to report.
            return  # Line 85:  (blank line)
        # Line 86:  Get the timestamp of the first entry as our reference point for relative times.
        start_time = self.entries[0][
            0
        ]  # Line 87:  All subsequent times will be shown as "+X.XXs" from this moment.
        # Line 88:  Iterate through all entries and print them with relative timestamps.
        for (
            ts,
            component,
            message,
            level,
        ) in (
            self.entries
        ):  # Line 89:  Unpack each tuple for clean access to its fields.
            # Line 90:  Calculate how many seconds after the first event this occurred.
            offset = (
                ts - start_time
            )  # Line 91:  Relative time is more useful than absolute Unix timestamps for understanding flow.
            # Line 92:  Get the color for this component.
            color = self.COMPONENT_COLORS.get(
                component, WHITE
            )  # Line 93:  Same lookup as in log() — consistent coloring throughout.
            # Line 94:  Format and print the entry with its relative timestamp.
            print(
                f"  {color}[+{offset:.3f}s] [{component}] {message}{RESET}"
            )  # Line 95:  Three decimal places gives millisecond precision without being noisy.
        # Line 96:  Print a summary line with total event count and any errors.
        error_count = sum(
            1 for e in self.entries if e[3] == "error"
        )  # Line 97:  Count how many entries were at error level.
        # Line 98:  Print the summary with color coding (green if no errors, red if there were).
        summary_color = (
            BG_GREEN if error_count == 0 else BG_RED
        )  # Line 99:  At-a-glance health indicator.
        # Line 100:  Format and print the final summary line.
        print(
            f"\n  {summary_color}{len(self.entries)} events, {error_count} errors{RESET}"
        )  # Line 101:  Quick stats for the developer to assess run health.
