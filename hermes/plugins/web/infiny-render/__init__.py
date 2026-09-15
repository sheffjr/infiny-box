"""Infiny page reader — a user plugin for Hermes providing extract.

Installed into ~/.hermes/plugins/web/infiny-render/ and enabled by two keys in
config.yaml:

    plugins:
      enabled: ["web/infiny-render"]
    web:
      extract_backend: infiny-render

User plugins in Hermes are opt-in: without plugins.enabled it finds the
manifest and skips it, noting "not enabled in config".
"""

from __future__ import annotations


def register(ctx) -> None:
    from .provider import InfinyRenderProvider

    ctx.register_web_search_provider(InfinyRenderProvider())
