---
name: mcp-management
description: Connect, test and remove MCP servers that add new tools
triggers: mcp, сервер, подключи, интеграция, tools, инструменты, connect, integration, n8n, linear, blender, unreal, добавь инструмент, новые возможности
---

# MCP Management (Infiny OS)

MCP servers are how the user gives you **new tools** — Linear issues, Blender,
n8n workflows, their own scripts. Skills teach you to use what already exists;
an MCP server adds capabilities that did not exist before.

You manage them through the `hermes mcp` CLI in the terminal.

## Non-negotiable acceptance criteria

- **Never add a server the user did not ask for.** Adding one means Hermes will
  run that command, or send data to that endpoint, on every session from now on.
- **Never invent a URL, command, or package name.** If you do not know the exact
  endpoint or npm package, say so and ask. A wrong guess here wires arbitrary
  code into the system.
- **Always confirm before `add`, `install` or `remove`**, and state exactly what
  will run: the full command or the full URL. Unless autonomous mode is on.
- Prefer the **catalog** over hand-written commands. Catalog entries are vetted;
  anything else is arbitrary code the user must vouch for.
- Never claim a server works without running `hermes mcp test <name>` and reading
  its exit status.
- Secrets (API keys, tokens) go in `--env KEY=VALUE`. Never paste a secret into
  a URL, never echo it back, never write it into a skill or memory.

## The catalog (start here)

```sh
hermes mcp catalog          # list vetted servers + their status
hermes mcp install <name>   # e.g. hermes mcp install n8n
```

Currently vetted: `blender`, `linear`, `n8n`, `unreal-engine`.

If the user's request matches one of these, use `install` — do not hand-build an
equivalent `add` command.

## Adding a custom server

**Stdio (a local command — most common):**
```sh
hermes mcp add <name> --command <cmd> --args <arg> <arg> ...
```

`--args` consumes everything after it, so it **must be the last flag**. This is
wrong and will silently swallow the rest:
```sh
hermes mcp add x --args a b --env KEY=V     # WRONG: --env is eaten by --args
hermes mcp add x --env KEY=V --args a b     # correct
```

**HTTP / SSE (a remote endpoint):**
```sh
hermes mcp add <name> --url https://host/path
```

**Useful flags:**
- `--env KEY=VALUE [KEY=VALUE ...]` — environment for stdio servers
- `--auth oauth` or `--auth header` — when the endpoint needs credentials
- `--connect-timeout <seconds>` — for slow-starting servers
- `--preset <name>` — a known preset, if one applies

## Inspecting, testing, removing

```sh
hermes mcp list             # what is configured right now
hermes mcp test <name>      # connect and discover tools — ALWAYS run after add
hermes mcp configure <name> # pick which of the server's tools stay enabled
hermes mcp login <name>     # force OAuth re-authentication
hermes mcp remove <name>    # remove it
```

## After adding a server

New tools are picked up on a fresh session — they will not appear mid-turn.
Tell the user plainly: the server is configured, and its tools become available
in a new session. Do not pretend you can already call them.

If a server exposes many tools, run `hermes mcp configure <name>` and help the
user keep only what they need. Every enabled tool costs context on every single
turn, and the prompt budget here is tight.

## Where it lives

Servers are stored in `config.yaml` under `mcp_servers:`:

```yaml
mcp_servers:
  my-server:
    command: "python3"
    args: ["/path/to/server.py"]
    env:
      LOG_LEVEL: "debug"
  my-http-server:
    url: "http://localhost:3000"
```

Prefer the CLI over hand-editing this file — the CLI validates the entry and can
test the connection. Read the file when you need to explain the current setup.

### Never name a server after a built-in toolset

`web`, `browser`, `terminal`, `file`, `memory`, `vision`, `skills`, `todo`,
`delegation`, `cronjob` are names Hermes already uses for its own toolsets. An
MCP server with one of those names **registers its tools and then loses them**:
the platform resolver sees the familiar name and hands back the built-in
toolset, so the server's tools never reach the model. Nothing errors, nothing is
logged at the usual level, and every layer looks healthy when you check it.

This exact bug cost this project two weeks — a server named `web` made the agent
look like it was lying about searching, when in truth it had no search tool at
all. If tools from a server never show up, **check the name for a collision
before you suspect anything else**.

## When something fails

- **Server not found / command not found** — the underlying program is not
  installed. Name what is missing and offer to install it (see
  `package-management`). Do not silently switch to a different server.
- **Connection refused on a URL** — report the exact URL you tried. Do not retry
  variations of the address hoping one sticks.
- **Auth failure** — try `hermes mcp login <name>` once, then stop and tell the
  user which credential is being rejected.
