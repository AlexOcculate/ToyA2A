#!/bin/bash

# chmod +x myscreate_folderscript.sh


touch main.py
touch test_adversarial.py
touch README.md
mkdir -p Harness/
touch Harness/__init__.py
touch Harness/envelope.py          # MessageEnvelope dataclass
touch Harness/message_bus.py       # In-memory pub/sub queue per agent
touch Harness/dispatcher.py        # Routes delegation messages (non-blocking)
touch Harness/simulated_lm.py      # Domain-aware keyword LM with delegate rules
touch Harness/guardrails.py        # Input validation + iteration cap
touch Harness/agent.py             # Agent loop: poll inbox → think → act → respond
touch Harness/trace_logger.py      # ANSI-colored execution trace


