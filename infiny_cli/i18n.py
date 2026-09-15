"""Compatibility shim: the dictionary itself lives in core/i18n.py.

Moved on 2026-09-03. The reason: user-visible text originates not only in the
CLI but also in core/model_source.py — the "no endpoint found" screen and the
reasons a model counts as unconfigured. While i18n lived in infiny_cli there was
no way to translate those: importing infiny_cli from core would close the
dependency loop (the CLI already depends on core).

The re-export stays here so that `from .i18n import t` across the CLI keeps
working.
"""
from core.i18n import (  # noqa: F401
    DEFAULT_LANG,
    INFINY_DIR,
    LANGS,
    STRINGS,
    get_lang,
    set_lang,
    t,
)
