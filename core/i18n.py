"""Tiny i18n layer — English is the base language, Russian is a switchable
feature (`/lang ru`), not a replacement. Stdlib-only so `plain.py` (the
zero-dependency fallback) can use it too. Preference persists to
~/.infiny/lang so it survives across runs.
"""
from __future__ import annotations

from pathlib import Path

INFINY_DIR = Path.home() / ".infiny"
_LANG_FILE = INFINY_DIR / "lang"
DEFAULT_LANG = "en"
LANGS = ("en", "ru")


def _load_lang() -> str:
    try:
        v = _LANG_FILE.read_text(encoding="utf-8").strip()
        if v in LANGS:
            return v
    except Exception:
        pass
    return DEFAULT_LANG


_lang = _load_lang()


def get_lang() -> str:
    return _lang


def set_lang(code: str) -> None:
    global _lang
    if code not in LANGS:
        raise ValueError(code)
    _lang = code
    try:
        INFINY_DIR.mkdir(parents=True, exist_ok=True)
        _LANG_FILE.write_text(code, encoding="utf-8")
    except Exception:
        pass


def t(key: str, **kwargs) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    s = entry.get(_lang) or entry.get("en") or key
    return s.format(**kwargs) if kwargs else s


STRINGS: dict[str, dict[str, str]] = {
    # ── slash commands ──────────────────────────────────────────────────
    "cmd_help": {"en": "show this help", "ru": "показать эту справку"},
    "cmd_status": {"en": "check services (gateway, model, context)",
                   "ru": "проверить сервисы (gateway, модель, контекст)"},
    "cmd_mode": {"en": "approval mode: manual / auto / yolo  ( /mode <mode> )",
                 "ru": "режим подтверждений: manual / auto / yolo  ( /mode <режим> )"},
    "cmd_new": {"en": "start a new conversation", "ru": "начать новый диалог"},
    "cmd_sessions": {"en": "list / switch conversations  ( /sessions <text or #> )",
                      "ru": "список / переключение диалогов  ( /sessions <текст или #> )"},
    "cmd_resume": {"en": "return to the last conversation", "ru": "вернуться к последнему диалогу"},
    "cmd_history": {"en": "show messages in the current conversation",
                     "ru": "показать сообщения текущего диалога"},
    "cmd_model": {"en": "show / change model  ( /model NAME )",
                  "ru": "показать / сменить модель  ( /model ИМЯ )"},
    "cmd_soul": {"en": "show active persona (SOUL.md)", "ru": "показать активную личность (SOUL.md)"},
    "cmd_lang": {"en": "interface language: en / ru  ( /lang <code> )",
                 "ru": "язык интерфейса: en / ru  ( /lang <код> )"},
    "cmd_retry": {"en": "retry the last message", "ru": "повторить последнее сообщение"},
    "cmd_copy": {"en": "copy the last reply to clipboard",
                 "ru": "скопировать последний ответ в буфер обмена"},
    "cmd_clear": {"en": "clear the screen", "ru": "очистить экран"},
    "cmd_heal": {"en": "self-diagnose and repair the system",
                 "ru": "самодиагностика и починка системы"},
    "cmd_exit": {"en": "exit", "ru": "выход"},
    "cmd_shell_row": {"en": "run a command directly in the shell (bypasses the agent)",
                       "ru": "выполнить команду в шелле напрямую (в обход агента)"},
    "cmd_file_row": {"en": "attach a file's contents to the message (autocompletes)",
                      "ru": "вложить содержимое файла в сообщение (с автодополнением)"},

    "hint": {
        "en": "[dim]/help[/] commands   ·   [dim]![/][dim]cmd[/] — to shell   ·   "
              "[dim]@[/][dim]file[/] — attach   ·   [dim]\\[/] + enter — new line   ·   "
              "[dim]/exit[/] quit",
        "ru": "[dim]/help[/] команды   ·   [dim]![/][dim]cmd[/] — в шелл   ·   "
              "[dim]@[/][dim]файл[/] — вложить   ·   [dim]\\[/] + enter — новая строка   ·   "
              "[dim]/exit[/] выход",
    },

    # ── banner ───────────────────────────────────────────────────────────
    "waking": {"en": "waking up…", "ru": "просыпаюсь…"},
    "tagline": {"en": "the intelligence of this machine, in your terminal",
                "ru": "интеллект этого компьютера, в твоём терминале"},
    "gateway_up": {"en": "gateway online", "ru": "gateway на связи"},
    "gateway_down": {"en": "gateway not responding", "ru": "gateway не отвечает"},
    "gateway_down_hint": {"en": "  Hermes not responding — run:  hermes gateway run",
                           "ru": "  Hermes не отвечает — запусти:  hermes gateway run"},
    "continuing": {"en": "  continuing \u201c{title}\u201d ({turns} turns)\n",
                    "ru": "  продолжаем «{title}» ({turns} реплик)\n"},
    "goodbye": {"en": "\n  see you.\n", "ru": "\n  до встречи.\n"},

    # ── toolbar ──────────────────────────────────────────────────────────
    "turns": {"en": "turns", "ru": "реплик"},
    "tokens": {"en": "tokens", "ru": "токенов"},
    "toolbar_hints": {"en": "^C cancel  ^D quit", "ru": "^C отмена  ^D выход"},

    # ── streaming ────────────────────────────────────────────────────────
    "thinking": {"en": "thinking…", "ru": "думаю…"},
    "mode_label": {"en": "mode", "ru": "режим"},
    "cancel_hint": {"en": "^C cancel", "ru": "^C отмена"},
    "cancelled": {"en": "  \u23f9 cancelled", "ru": "  \u23f9 отменено"},
    "connect_error": {"en": "\n\n\u26a0 Can't reach Hermes (gateway :8642). Run: `hermes gateway run`",
                       "ru": "\n\n\u26a0 Не могу связаться с Hermes (gateway :8642). Запусти: `hermes gateway run`"},
    "usage_line": {"en": "  {elapsed:.1f}s   \u00b7   {p} prompt + {c} reply = {total} tokens",
                    "ru": "  {elapsed:.1f}s   \u00b7   {p} промпт + {c} ответ = {total} токенов"},
    "no_reply": {"en": "(no reply)", "ru": "(нет ответа)"},

    # ── approval dialog ──────────────────────────────────────────────────
    "yolo_note": {"en": "  \u26a1 yolo \u2014 approved without asking: {desc}",
                  "ru": "  \u26a1 yolo \u2014 разрешено без вопроса: {desc}"},
    "auto_note": {"en": "  \u2699 auto \u2014 approved ({scope}): {desc}",
                  "ru": "  \u2699 авто \u2014 одобрено ({scope}): {desc}"},
    "approval_title": {"en": "\u26a0 confirmation needed", "ru": "\u26a0 нужно подтверждение"},
    "approval_prompt": {"en": "  choice ({hint}, enter = deny) \u203a ",
                         "ru": "  выбор ({hint}, enter = deny) \u203a "},
    "approval_bad_choice": {"en": "  didn't catch that, try again", "ru": "  не понял, попробуй ещё раз"},

    # ── /command dispatch ────────────────────────────────────────────────
    "new_dialog": {"en": "  \u2726 new conversation\n", "ru": "  \u2726 новый диалог\n"},
    "returned_to": {"en": "  returned to \u201c{title}\u201d ({turns} turns)\n",
                     "ru": "  вернулись к «{title}» ({turns} реплик)\n"},
    "nothing_to_return": {"en": "  nothing to return to\n", "ru": "  нечего возвращать\n"},
    "unknown_command": {"en": "  unknown command: {cmd}  (/help)\n",
                         "ru": "  неизвестная команда: {cmd}  (/help)\n"},

    # ── /help ────────────────────────────────────────────────────────────
    "help_title": {"en": "commands", "ru": "команды"},
    "help_footer": {
        "en": "  ctrl+r \u2014 search input history \u00b7 everything else \u2014 a message to "
              "Infiny: it sees the screen, runs commands, fixes and installs software.\n",
        "ru": "  ctrl+r — поиск по истории ввода · всё остальное — сообщение "
              "Infiny: он видит экран, выполняет команды, чинит и ставит софт.\n",
    },

    # ── /status ──────────────────────────────────────────────────────────
    "status_title": {"en": "status", "ru": "статус"},
    "online": {"en": "online", "ru": "на связи"},
    "not_responding": {"en": "not responding", "ru": "не отвечает"},
    "model_label": {"en": "model", "ru": "модель"},
    "context_label": {"en": "model context", "ru": "контекст модели"},
    "unknown": {"en": "unknown", "ru": "неизвестно"},
    "session_tokens_label": {"en": "tokens this session", "ru": "токенов в этой сессии"},
    "available_label": {"en": "available", "ru": "доступно"},
    "run_hint": {"en": "  run:  hermes gateway run\n", "ru": "  запусти:  hermes gateway run\n"},

    # ── /sessions ────────────────────────────────────────────────────────
    "none_saved": {"en": "  no saved conversations yet\n", "ru": "  сохранённых диалогов пока нет\n"},
    "no_such_session": {"en": "  no such conversation\n", "ru": "  нет такого диалога\n"},
    "no_matches": {"en": "  no matches for \u201c{query}\u201d \u2014 showing all:\n",
                    "ru": "  совпадений с «{query}» нет — показываю все:\n"},
    "sessions_title": {"en": "conversations", "ru": "диалоги"},
    "col_title": {"en": "title", "ru": "название"},
    "col_turns": {"en": "turns", "ru": "реплик"},
    "col_updated": {"en": "updated", "ru": "обновлён"},
    "sessions_hint": {"en": "  /sessions <# or text>  to switch\n",
                       "ru": "  /sessions <# или текст>  чтобы переключиться\n"},
    "switched_to": {"en": "  switched to \u201c{title}\u201d\n", "ru": "  переключились на «{title}»\n"},

    # ── /mode ────────────────────────────────────────────────────────────
    "mode_manual": {"en": "ask every time (default, safe)",
                     "ru": "спрашивать каждый раз (по умолчанию, безопасно)"},
    "mode_auto": {"en": "ask once per kind of risky command per session, then stop asking",
                   "ru": "спросить один раз на каждый тип опасной команды за сессию, дальше не переспрашивать"},
    "mode_yolo": {"en": "approve everything without asking \u2014 for unattended overnight runs",
                   "ru": "разрешать всё без вопросов — для ночных прогонов без присмотра"},
    "mode_title": {"en": "approval mode", "ru": "режим подтверждений"},
    "mode_switch_hint": {"en": "  /mode <manual|auto|yolo>  to change\n",
                          "ru": "  /mode <manual|auto|yolo>  чтобы сменить\n"},
    "mode_unknown": {"en": "  unknown mode: {m}  (manual/auto/yolo)\n",
                      "ru": "  неизвестный режим: {m}  (manual/auto/yolo)\n"},
    "mode_set": {"en": "  \u2713 mode \u2192 {m}  ({desc})\n", "ru": "  ✓ режим → {m}  ({desc})\n"},

    # ── /lang ────────────────────────────────────────────────────────────
    "lang_title": {"en": "interface language", "ru": "язык интерфейса"},
    "lang_switch_hint": {"en": "  /lang <en|ru>  to change\n", "ru": "  /lang <en|ru>  чтобы сменить\n"},
    "lang_unknown": {"en": "  unknown language: {code}  (en/ru)\n",
                      "ru": "  неизвестный язык: {code}  (en/ru)\n"},
    "lang_set": {"en": "  \u2713 language \u2192 {code}\n", "ru": "  ✓ язык → {code}\n"},

    # ── /history ─────────────────────────────────────────────────────────
    "history_empty": {"en": "  (conversation is empty)\n", "ru": "  (диалог пуст)\n"},

    # ── /model ───────────────────────────────────────────────────────────
    "model_changed": {"en": "  ✓ model → {name}  (config rewritten, gateway restarted)\n",
                      "ru": "  ✓ модель → {name}  (конфиг переписан, gateway перезапущен)\n"},
    "model_current": {"en": "  current: {model}", "ru": "  текущая: {model}"},
    "model_source_line": {"en": "  endpoint: {url}", "ru": "  эндпоинт: {url}"},
    "model_available": {"en": "  available: {list}", "ru": "  доступные: {list}"},
    "model_switch_hint": {"en": "  /model <name>  to switch (restarts the gateway)",
                           "ru": "  /model <имя>  чтобы сменить (перезапустит gateway)"},
    "model_switching": {"en": "switching to {name} — restarting the gateway…",
                         "ru": "переключаю на {name} — перезапускаю gateway…"},
    "model_no_source": {"en": "  no model connected yet — run:  infiny --setup\n",
                         "ru": "  модель ещё не подключена — запусти:  infiny --setup\n"},
    "model_unknown_name": {"en": "  {url} has no model named “{name}”",
                            "ru": "  на {url} нет модели «{name}»"},
    "model_probe_fail": {"en": "  endpoint did not answer: {error}",
                          "ru": "  эндпоинт не ответил: {error}"},
    "model_switch_fail": {"en": "  could not switch: {error}\n",
                           "ru": "  переключить не удалось: {error}\n"},
    "model_gateway_silent": {
        "en": "  config rewritten, but the gateway is silent — log: /tmp/hermes-gateway.log\n",
        "ru": "  конфиг переписан, но gateway молчит — лог: /tmp/hermes-gateway.log\n",
    },

    # ── /reasoning ───────────────────────────────────────────────────────
    "cmd_reasoning": {"en": "thinking level: none…ultra  ( /reasoning <level> )",
                       "ru": "уровень мышления: none…ultra  ( /reasoning <уровень> )"},
    "reasoning_title": {"en": "thinking level", "ru": "уровень мышления"},
    "reasoning_none": {"en": "off — fastest, but breaks multi-step tasks",
                        "ru": "выключено — быстро, но многошаговые задачи ломаются"},
    "reasoning_low": {"en": "recommended — the agent plans and acts",
                       "ru": "рекомендуется — агент планирует и действует"},
    "reasoning_high": {"en": "slower; on small models can loop",
                        "ru": "медленнее; на маленьких моделях бывают циклы"},
    "reasoning_hint": {"en": "  /reasoning <level>  to change (restarts the gateway)",
                        "ru": "  /reasoning <уровень>  чтобы сменить (перезапустит gateway)"},
    "reasoning_switching": {"en": "switching thinking to {level} — restarting the gateway…",
                             "ru": "переключаю мышление на {level} — перезапускаю gateway…"},
    "reasoning_set": {"en": "  ✓ thinking → {level}  (config rewritten, gateway restarted)\n",
                       "ru": "  ✓ мышление → {level}  (конфиг переписан, gateway перезапущен)\n"},
    "reasoning_unknown": {"en": "  unknown level: {level}  ({list})\n",
                           "ru": "  неизвестный уровень: {level}  ({list})\n"},
    "reasoning_fail": {"en": "  could not switch: {error}\n",
                        "ru": "  переключить не удалось: {error}\n"},

    # ── /soul ────────────────────────────────────────────────────────────
    "soul_title": {"en": "SOUL.md \u2014 active persona", "ru": "SOUL.md — активная личность"},
    "soul_missing": {"en": "  no SOUL.md at {path}\n", "ru": "  нет SOUL.md по пути {path}\n"},

    # ── /retry, /copy ────────────────────────────────────────────────────
    "nothing_to_retry": {"en": "  nothing to retry\n", "ru": "  нечего повторять\n"},
    "nothing_to_copy": {"en": "  nothing to copy\n", "ru": "  нечего копировать\n"},
    "copied": {"en": "  \u2713 copied to clipboard\n", "ru": "  ✓ скопировано в буфер обмена\n"},
    "no_clipboard_tool": {"en": "  couldn't find a clipboard tool (clip.exe/wl-copy/xclip)\n",
                           "ru": "  не нашёл инструмент буфера обмена (clip.exe/wl-copy/xclip)\n"},

    # ── plain.py (stdlib fallback) ──────────────────────────────────────
    "plain_subtitle": {"en": "  \u2014 plain mode", "ru": "  — plain-режим"},
    "plain_status_title": {"en": "\n  Infiny \u2014 service status\n", "ru": "\n  Infiny — состояние сервисов\n"},
    "plain_gateway_row": {"en": "  {mark} Hermes gateway (:8642): ", "ru": "  {mark} Hermes gateway (:8642): "},
    "plain_not_responding_hint": {"en": "\n  \u26a0 Hermes is not responding. Run:",
                                    "ru": "\n  ⚠ Hermes не отвечает. Запусти:"},
    "plain_ok": {"en": "\n  \u2713 All good. Infiny is ready.\n", "ru": "\n  ✓ Всё в порядке. Infiny готов.\n"},
    "plain_err_down": {
        "en": "\n\u26a0 Can't reach Infiny (Hermes gateway :8642).\n"
              "  Check:  infiny --status\n  Run:  hermes gateway run",
        "ru": "\n⚠ Не могу связаться с Infiny (Hermes gateway :8642).\n"
              "  Проверь:  infiny --status\n  Запусти:  hermes gateway run",
    },
    "plain_hint": {"en": "  /help for commands. Anything else \u2014 a message.\n",
                    "ru": "  /help — команды. Всё остальное — сообщение.\n"},
    "plain_bye": {"en": "\n  bye.\n", "ru": "\n  пока.\n"},
    "plain_error": {"en": "\n\u26a0 Error: {e}", "ru": "\n⚠ Ошибка: {e}"},
    "plain_lang_set": {"en": "  language \u2192 {code}\n", "ru": "  язык → {code}\n"},
    "plain_help_title": {"en": "\n  commands\n", "ru": "\n  команды\n"},
    "plain_help_status": {"en": "  /status         check services (gateway, model)",
                           "ru": "  /status         проверить сервисы (gateway, модель)"},
    "plain_help_lang": {"en": "  /lang <en|ru>   interface language  ( /lang alone shows current )",
                         "ru": "  /lang <en|ru>   язык интерфейса  ( /lang без аргумента — показать текущий )"},
    "plain_help_clear": {"en": "  /clear          clear the screen", "ru": "  /clear          очистить экран"},
    "plain_help_help": {"en": "  /help           show this help", "ru": "  /help           показать эту справку"},
    "plain_help_exit": {"en": "  /exit           exit  ( /quit, /q also work )",
                         "ru": "  /exit           выход  ( /quit, /q тоже работают )"},

    # ── first-run wizard (setup.py) ──────────────────────────────────────
    # Мастер — первое, что видит человек, и до 2026-09-03 он единственный из
    # крупных модулей говорил только по-русски: i18n он не импортировал вовсе.
    # Англоязычный пользователь получал английский CLI и русский мастер до него.
    "setup_title": {"en": "═══ Infiny Box — connect a model ═══",
                     "ru": "═══ Infiny Box — подключение модели ═══"},
    "setup_env": {"en": "  Environment: {env}", "ru": "  Среда: {env}"},
    "setup_connected": {"en": "  Currently connected: {model}  ({url})",
                         "ru": "  Сейчас подключено: {model}  ({url})"},
    "setup_not_connected": {"en": "  No model connected: {reason}",
                             "ru": "  Модель не подключена: {reason}"},
    "setup_reconfigure": {"en": "Set up again? (y/N)", "ru": "Настроить заново? (y/N)"},

    "setup_searching": {"en": "Looking for running OpenAI-compatible endpoints...",
                         "ru": "Ищу запущенные OpenAI-совместимые эндпоинты..."},
    "setup_n_models": {"en": "({n} models)", "ru": "({n} моделей)"},
    "setup_manual_entry": {"en": "Enter an address manually (cloud / another port)",
                            "ru": "Ввести адрес вручную (облако / другой порт)"},
    "setup_what": {"en": "What are we connecting", "ru": "Что подключаем"},
    "setup_model": {"en": "  Model", "ru": "  Модель"},
    "setup_model_name": {"en": "  Model name", "ru": "  Имя модели"},
    "setup_no_models": {"en": "  The endpoint responds but lists no models — type the name manually.",
                         "ru": "  Эндпоинт отвечает, но моделей не отдаёт — введите имя вручную."},
    "setup_address": {"en": "Endpoint address (e.g. http://192.168.1.10:11434/v1)",
                       "ru": "Адрес эндпоинта (например http://192.168.1.10:11434/v1)"},
    "setup_apikey": {"en": "API key (Enter — if not needed)",
                      "ru": "API-ключ (Enter — если не нужен)"},
    "setup_checking": {"en": "  Checking the address...", "ru": "  Проверяю адрес..."},

    "setup_list_failed": {"en": "  Could not fetch the model list: {err}",
                           "ru": "  Список моделей получить не удалось: {err}"},
    "setup_list_failed_hint1": {
        "en": "  That does not necessarily mean the endpoint is broken — the list",
        "ru": "  Это не обязательно значит, что эндпоинт нерабочий — список"},
    "setup_list_failed_hint2": {
        "en": "  can be large and break on a poor link, while chat itself works.",
        "ru": "  бывает большим и рвётся на плохом канале, а сам чат работает."},
    "setup_type_model_q": {"en": "  Type the model name manually? (y/N)",
                            "ru": "  Ввести имя модели вручную? (y/N)"},

    "setup_slow_check": {
        "en": "Checking tool calling. If the model is loading from disk for the\n"
              "  first time this can take up to two minutes. Ctrl+C — skip.",
        "ru": "Проверяю вызов инструментов. Если модель грузится с диска впервые, это\n"
              "  может занять до двух минут. Ctrl+C — пропустить проверку."},
    "setup_check_skipped": {"en": "  Check skipped.", "ru": "  Проверка пропущена."},
    "setup_tools_ok": {"en": "  Tool calling works.", "ru": "  Вызов инструментов работает."},
    "setup_check_failed": {"en": "  CHECK FAILED ({reason}): {detail}",
                            "ru": "  ПРОВЕРКА НЕ ПРОШЛА ({reason}): {detail}"},
    "setup_key_rejected": {"en": "  The server rejected the key. Usual causes:",
                            "ru": "  Сервер отклонил ключ. Обычные причины:"},
    "setup_key_r1": {"en": "    • the key was copied partially or with a trailing space",
                      "ru": "    • ключ скопирован не целиком или с пробелом на конце"},
    "setup_key_r2": {"en": "    • the key has no access to this particular model",
                      "ru": "    • у ключа нет доступа именно к этой модели"},
    "setup_key_r3": {"en": "    • no credit on the account (some providers answer 401)",
                      "ru": "    • на счету нет средств (некоторые провайдеры отвечают 401)"},
    "setup_no_tools1": {"en": "  The server replied but called no tool. The agent will not",
                         "ru": "  Сервер ответил, но инструмент не вызвал. Агент на такой связке"},
    "setup_no_tools2": {"en": "  work on this setup. Usual causes:",
                         "ru": "  работать не будет. Обычные причины:"},
    "setup_no_tools_r1": {"en": "    • llama.cpp started without --jinja",
                           "ru": "    • llama.cpp запущен без --jinja"},
    "setup_no_tools_r2": {"en": "    • vLLM without --enable-auto-tool-choice --tool-call-parser",
                           "ru": "    • vLLM без --enable-auto-tool-choice --tool-call-parser"},
    "setup_no_tools_r3": {"en": "    • a model whose template does not support tools",
                           "ru": "    • модель без поддержки инструментов в шаблоне"},
    "setup_connect_anyway": {"en": "  Connect anyway? (y/N)", "ru": "  Всё равно подключить? (y/N)"},

    "setup_connecting": {"en": "Connecting {model} ({url})...",
                          "ru": "Подключаю {model} ({url})..."},
    "setup_error": {"en": "  Error: {err}", "ru": "  Ошибка: {err}"},
    "setup_ctx": {"en": "  Context window: {n} tokens", "ru": "  Окно контекста: {n} токенов"},
    "setup_ctx_small": {"en": "  WARNING: that is below the {min} tokens the agent needs.",
                         "ru": "  ВНИМАНИЕ: это меньше {min} токенов, которые нужны агенту."},
    "setup_ctx_small1": {"en": "  Tool schemas and the system prompt take a large fixed",
                          "ru": "  Схемы инструментов и системный промпт занимают большой"},
    "setup_ctx_small2": {"en": "  slice of the window; on what is left the agent is unreliable —",
                          "ru": "  фиксированный кусок окна; на остатке агент работает ненадёжно —"},
    "setup_ctx_small3": {"en": "  it loses the start of the conversation and confuses its own calls.",
                          "ru": "  теряет начало разговора и путается в собственных вызовах."},
    "setup_ctx_fix": {"en": "  Fixed on the server side, with one variable:",
                       "ru": "  Чинится на стороне сервера, одной переменной:"},
    "setup_ctx_rerun": {"en": "  After restarting the server run: infiny --setup",
                         "ru": "  После перезапуска сервера запустите: infiny --setup"},

    "setup_written": {"en": "  Config written, starting the gateway...",
                       "ru": "  Конфиг записан, поднимаю gateway..."},
    "setup_ready": {"en": "  Done. Infiny is online.", "ru": "  Готово. Infiny на связи."},
    "setup_gw_down": {"en": "  Gateway is not responding. Log: /tmp/hermes-gateway.log",
                       "ru": "  Gateway не отвечает. Лог: /tmp/hermes-gateway.log"},
    "setup_gw_hint1": {"en": "  A common cause is port 8642 taken by another process; in the log",
                        "ru": "  Частая причина — порт 8642 занят другим процессом; в логе это"},
    "setup_gw_hint2": {
        "en": "  that is \"Could not bind 127.0.0.1:8642: address already in use\".",
        "ru": "  строка \"Could not bind 127.0.0.1:8642: address already in use\"."},

    "setup_cancelled_rerun": {"en": "Setup cancelled. Run again: infiny --setup",
                               "ru": "Настройка отменена. Запустить снова: infiny --setup"},
    "setup_cancelled": {"en": "Setup cancelled.", "ru": "Настройка отменена."},
    "setup_interrupted": {"en": "Interrupted. Run again: infiny --setup",
                           "ru": "Прервано. Запустить снова: infiny --setup"},

    # ── stages, shown inside error text (client.py) ──────────────────────
    # 2026-08-03 пользователь получил голое "⚠ UnicodeDecodeError: ... byte
    # 0xd1 in position 2", и по этой строке нельзя было понять даже, чей это
    # сбой — наш, gateway или инструмента. На разбор ушёл вечер, и он ничем
    # не кончился. С тех пор в текст ошибки попадает шаг, на котором она
    # случилась.
    "stage_request": {"en": "creating the request", "ru": "создание запроса"},
    "stage_stream": {"en": "reading the event stream", "ru": "чтение потока событий"},
    "stage_approval": {"en": "command approval", "ru": "подтверждение команды"},
    "stage_error": {"en": "{kind} at stage «{stage}»: {err}",
                     "ru": "{kind} на шаге «{stage}»: {err}"},

    # ── /heal (cli.py) ───────────────────────────────────────────────────
    # Это промпт АГЕНТУ, а не надпись на экране. Язык всё равно берём из i18n:
    # SOUL.md велит агенту отвечать на языке собеседника, поэтому русский
    # промпт заставил бы его отвечать по-русски даже англоязычному человеку.
    "heal_prompt": {
        "en": "Run self-healing: diagnose the system and repair what you can.",
        "ru": "Запусти self-healing: продиагностируй систему и почини что можешь."},

    # ── core/model_source.py: состояние источника модели ──────────────────
    "src_no_config": {"en": "config.yaml does not exist", "ru": "config.yaml не существует"},
    "src_bad_config": {"en": "config.yaml is unreadable: {err}",
                        "ru": "config.yaml не читается: {err}"},
    "src_not_set": {"en": "model source not configured",
                     "ru": "источник модели не настроен"},

    # ── core/model_source.py: экран «ничего не найдено» ───────────────────
    # Смысл экрана — не «не найдено», а «вот что конкретно проверить». Самый
    # частый случай: сервер запущен и с хоста прекрасно открывается, но слушает
    # только 127.0.0.1, а такой сокет из песочницы недостижим в принципе.
    "nf_title": {"en": "No OpenAI-compatible endpoint found.",
                  "ru": "Не найден ни один OpenAI-совместимый эндпоинт."},
    "nf_hosts": {"en": "Looked at: {hosts}", "ru": "Искали на адресах: {hosts}"},
    "nf_ports": {"en": "Ports: {ports}", "ru": "Порты: {ports}"},
    "nf_localhost": {
        "en": "If the server is running and opens fine from the host, it almost "
              "certainly listens on 127.0.0.1 only. Allow external connections:",
        "ru": "Если сервер запущен и с хоста открывается — почти наверняка он "
              "слушает только 127.0.0.1. Разрешите ему внешние подключения:"},
    "nf_ollama": {"en": "  • Ollama — set OLLAMA_HOST=0.0.0.0 and restart",
                   "ru": "  • Ollama — переменная OLLAMA_HOST=0.0.0.0 и перезапуск"},
    "nf_lmstudio": {"en": "  • LM Studio — enable \"Serve on Local Network\" in server settings",
                     "ru": "  • LM Studio — в настройках сервера включить \"Serve on Local Network\""},
    "nf_llamacpp": {
        "en": "  • llama.cpp — run with --host 0.0.0.0 (and --jinja, without it "
              "tool calling will not work)",
        "ru": "  • llama.cpp — запускать с --host 0.0.0.0 (и с --jinja, иначе не "
              "будет работать вызов инструментов)"},
    "nf_vllm": {"en": "  • vLLM — --host 0.0.0.0 and --enable-auto-tool-choice",
                 "ru": "  • vLLM — --host 0.0.0.0 и --enable-auto-tool-choice"},
    "nf_manual": {"en": "Or enter an address manually below — cloud endpoints included.",
                   "ru": "Либо укажите адрес вручную ниже — включая облачные эндпоинты."},

    # ── core/runtime_env.py: почему хост может быть не виден ──────────────
    # Текст зависит от среды: совет про OLLAMA_HOST бессмысленен на голом
    # Linux, где мы и так на localhost, и там он только запутает.
    "sandbox_wsl": {
        "en": "Infiny runs in WSL2. A server listening on 127.0.0.1 only on "
              "Windows is unreachable from WSL by design — it has to allow "
              "external connections.",
        "ru": "Infiny работает в WSL2. Сервер, слушающий на Windows только "
              "127.0.0.1, из WSL недостижим в принципе — ему нужно разрешить "
              "внешние подключения."},
    "sandbox_docker": {
        "en": "Infiny runs in a container. A server listening on 127.0.0.1 only "
              "on the host is unreachable from inside. On Linux the container "
              "also needs --add-host=host.docker.internal:host-gateway.",
        "ru": "Infiny работает в контейнере. Сервер, слушающий только 127.0.0.1 "
              "на хосте, изнутри контейнера недостижим. На Linux контейнер также "
              "должен быть запущен с --add-host=host.docker.internal:host-gateway."},
    "sandbox_native": {
        "en": "Infiny runs directly on the system. Check that the server is "
              "running and listening on the port given.",
        "ru": "Infiny работает напрямую в системе. Проверьте, что сервер запущен "
              "и слушает указанный порт."},

    # ── core/model_source.py: тексты отказов ─────────────────────────────
    # Эти строки приходят наружу как res["error"] / res["detail"] и печатаются
    # мастером. 2026-09-03 обнаружилось, что рамка у него уже английская, а
    # содержимое осталось русским: перевод дошёл до current_source() и
    # explain_not_found(), а до путей отказа — нет. Самая обидная — err_timeout:
    # это самый вероятный сбой первого запуска вообще.
    "err_not_openai": {"en": "response is not in OpenAI format: {err}",
                        "ru": "ответ не в формате OpenAI: {err}"},
    "err_timeout": {
        "en": "the endpoint did not answer in {sec:.0f} s. If the model is "
              "loading from disk for the first time, try again.",
        "ru": "эндпоинт не ответил за {sec:.0f} с. Если модель грузится с диска "
              "впервые — попробуйте ещё раз."},
    "err_empty_reply": {"en": "the model returned an empty response",
                         "ru": "модель вернула пустой ответ"},
    "err_config_read": {"en": "config.yaml is unreadable: {err}",
                         "ru": "config.yaml не читается: {err}"},
    "err_config_write": {"en": "cannot write config.yaml: {err}",
                          "ru": "не записать config.yaml: {err}"},
    "err_bad_level": {"en": "unknown level: {level}", "ru": "неизвестный уровень: {level}"},
}
