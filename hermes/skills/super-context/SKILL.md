---
name: super-context
description: Session start: gather context before the first reply
triggers: __session_start__, first message, new conversation, начало сессии
---

# Super Context

On the FIRST message of a new session, quietly gather context so your first reply
is already informed — don't make the user explain what you could have checked.

## Non-negotiable acceptance criteria
- Do this ONCE per session, silently, before the first substantive reply.
- **Two commands, then stop.** This is a warm-up, not an investigation. If you
  find yourself running a third check, you have already gone too far: answer the
  user instead. Endless silent sweeping produces empty turns and burns the
  context window the user is paying for.
- Never dump raw output. Fold it into your reasoning.
- If the user's message needs no context at all (a greeting, a general question),
  skip this entirely and just answer.

## What to gather
1. **System state**, one command: `free -h | grep Mem; df -h / | tail -1`
2. **Past work**, only if their message references it ("the project", "that bug",
   "как в прошлый раз"): search your memory / past sessions for that topic.

That is the whole list.

## What NOT to do
- There is no screen here. This machine has no display, no compositor and no
  vision tool — never try to look at one, and never mention screenshots. A
  request about "this" or "here" refers to the conversation or the filesystem.
- Don't check services on a healthy session. If something is actually broken the
  user will say so, and `self-healing` exists for exactly that.

## How to use it
- Fold the gathered context into your reasoning silently. Don't announce "I
  checked your system". Just answer as if you already knew.
- If something is clearly broken and it is relevant to what the user asked,
  mention it proactively. Otherwise stay quiet about it.

## Output
There is no separate output — this skill informs your first real reply. The user
should feel the conversation started "warm", already aware of their context.
