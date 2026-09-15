"""
Which model is configured — according to the config, not a constant in code.

Why this deserves a module: `client.py` and `plain.py` each hardcoded
`HERMES_MODEL` (`qwen3-vl:4b`). In Phase 1 there is no model in the box — the
user picks one in the first-run wizard, and a hardcoded name is guaranteed not
to match whatever they actually have. The symptom would have been absurd: the
wizard reports "done", and the very first question fails with "model not found".

Stdlib only. `plain.py` is the emergency mode ("works over SSH, on a bare tty,
in recovery, with no deps"), and dragging httpx and pyyaml into it for the sake
of a model name would break precisely the branch that exists for when
everything else is broken.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

HERMES_CONFIG = Path.home() / ".hermes" / "config.yaml"

# Last resort when there is no config at all. Not a "correct" model, just
# something non-empty, so the error comes from the server and reads clearly.
FALLBACK_MODEL = "qwen3.5:4b"


def configured_model(default: str = FALLBACK_MODEL) -> str:
    """
    The model name from ~/.hermes/config.yaml (flat schema: model.default).

    Order: environment variable → config → fallback name. The environment is a
    convenient way to override the model for one run without touching config.

    Parsed with yaml when available, by regex otherwise. The fallback is not
    paranoia: this code is called from the emergency mode too, where pyyaml may
    not be installed, and failing there is not an option.
    """
    if env := os.environ.get("INFINY_MODEL"):
        return env
    try:
        text = HERMES_CONFIG.read_text()
    except OSError:
        return default

    try:
        import yaml
        cfg = yaml.safe_load(text) or {}
        if model := str((cfg.get("model") or {}).get("default") or "").strip():
            return model
        return default
    except ImportError:
        pass
    except Exception:
        # Broken yaml is no reason to fail; we try line by line below.
        pass

    # Look for `default:` inside the `model:` block rather than the first one in
    # the file: the key `default` appears in other sections of the Hermes config
    # too.
    m = re.search(r"^model:\s*$\n((?:[ \t]+.*\n)*)", text, re.MULTILINE)
    if m:
        d = re.search(r"^[ \t]+default:\s*(\S+)", m.group(1), re.MULTILINE)
        if d:
            return d.group(1).strip().strip("\"'")
    return default
