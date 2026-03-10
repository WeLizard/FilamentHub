"""
FHAgents Telegram Bot — мост между Telegram и CLI-агентами.

Первый вызов через /claude, /qwen, /gemini, /codex задаёт активного агента.
Дальше просто пишешь текст — идёт в того же агента с --continue.
/new — сбросить сессию и переключиться.
"""

import asyncio
import logging
import os
import shutil
import tempfile

import httpx
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "WeLizard/FilamentHub")
REPO_PATH = os.environ.get("REPO_PATH", "/repo")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8090"))
TG_RESULTS_ONLY = os.environ.get("TG_RESULTS_ONLY", "1").lower() not in {"0", "false", "no"}
TG_SHOW_STATUS = os.environ.get("TG_SHOW_STATUS", "0").lower() in {"1", "true", "yes"}

# CLI paths — full paths to avoid PATH issues on Windows
CLAUDE_CMD = os.environ.get("CLAUDE_CMD", os.path.expanduser("~/.local/bin/claude"))
QWEN_CMD = os.environ.get("QWEN_CMD", os.path.join(os.environ.get("APPDATA", ""), "npm", "qwen.cmd"))
GEMINI_CMD = os.environ.get("GEMINI_CMD", os.path.join(os.environ.get("APPDATA", ""), "npm", "gemini.cmd"))
CODEX_CMD = os.environ.get("CODEX_CMD", os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd"))

AGENT_CONFIG = {
    "claude": {"cmd": CLAUDE_CMD, "timeout": 600},
    "qwen": {"cmd": QWEN_CMD, "timeout": 300},
    "gemini": {"cmd": GEMINI_CMD, "timeout": 300},
    "codex": {"cmd": CODEX_CMD, "timeout": 1200},
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Active CLI processes per agent (parallel support)
active_processes: dict[str, asyncio.subprocess.Process] = {}
# Current active agent (for plain text routing)
active_agent: str | None = None
# Whether agent has had at least one call (for --continue)
agent_has_session: dict[str, bool] = {k: False for k in AGENT_CONFIG}
# Last output per agent (for @agent references and /pass)
agent_last_output: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def github_api(method: str, path: str, json_data: dict | None = None) -> dict | None:
    if not GITHUB_TOKEN:
        return None
    url = f"https://api.github.com/repos/{GITHUB_REPO}{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        else:
            resp = await client.post(url, headers=headers, json=json_data)
        if resp.status_code < 300:
            return resp.json()
        logger.error("GitHub API %s %s -> %s: %s", method, path, resp.status_code, resp.text)
        return None


async def create_issue(title: str, body: str, labels: list[str] | None = None) -> dict | None:
    data: dict = {"title": title, "body": body}
    if labels:
        data["labels"] = labels
    return await github_api("POST", "/issues", data)


def read_local_file(relative_path: str, max_lines: int = 80) -> str:
    full_path = os.path.join(REPO_PATH, relative_path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            text = "".join(lines[:max_lines])
            text += f"\n... ({len(lines) - max_lines} lines truncated)"
            return text
        return "".join(lines)
    except FileNotFoundError:
        return f"File not found: {relative_path}"
    except Exception as e:
        return f"Error reading {relative_path}: {e}"


def truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n... (truncated)"


def read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as e:
        logger.warning("Failed to read %s: %s", path, e)
        return ""


import re

# Noise patterns to filter from CLI output
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

NOISE_PATTERNS = [
    re.compile(r"^mcp:"),                          # MCP startup
    re.compile(r"^-{4,}"),                         # Separator lines
    re.compile(r"^(workdir|model|provider|approval|sandbox|reasoning|session id):"),  # Codex header
    re.compile(r"^OpenAI Codex"),                  # Codex version
    re.compile(r"^exec$"),                         # Codex exec marker
    re.compile(r'^"[A-Z]:\\'),                     # Windows command paths
    re.compile(r"^(user|codex|assistant)$"),        # Role markers
    re.compile(r"^\s*succeeded in \d+ms"),         # exec timing
    re.compile(r"^\s*in [A-Z]:\\"),                # "in F:\FilamentHub"
]

def is_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return any(p.search(stripped) for p in NOISE_PATTERNS)


def filter_output(lines: list[str]) -> list[str]:
    """Remove noise lines from CLI output."""
    cleaned_lines = [ANSI_ESCAPE_RE.sub("", line) for line in lines]
    return [line for line in cleaned_lines if not is_noise(line)]


def resolve_agent_refs(prompt: str) -> str:
    """Replace @agent references with that agent's last output."""
    import re
    def replacer(match: re.Match) -> str:
        name = match.group(1).lower()
        output = agent_last_output.get(name, "")
        if not output:
            return f"(@{name}: no output)"
        # Limit injected output to avoid insane prompt sizes
        return truncate(output, 2000)
    return re.sub(r"@(claude|qwen|gemini|codex)\b", replacer, prompt, flags=re.IGNORECASE)


TG_PROMPT_SUFFIX = (
    "\n\n[Output goes to Telegram. Be concise: only the final result, "
    "no tool details, no file dumps. Max 3-5 sentences or a short list.]"
)


def build_cmd(agent: str, prompt: str, output_last_message_path: str | None = None) -> list[str]:
    """Build CLI command with --continue if session exists."""
    cfg = AGENT_CONFIG[agent]
    cmd_path = cfg["cmd"]
    has_session = agent_has_session.get(agent, False)

    # Append Telegram brevity instruction
    prompt = prompt + TG_PROMPT_SUFFIX

    if agent == "claude":
        cmd = [cmd_path, "-p", prompt, "--output-format", "text"]
        if has_session:
            cmd.append("--continue")
        return cmd

    if agent == "codex":
        base = [cmd_path, "exec"]
        if has_session:
            base.extend(["resume", "--last"])
        if output_last_message_path:
            base.extend(["--output-last-message", output_last_message_path])
        base.append(prompt)
        return base

    # qwen, gemini — same interface
    cmd = [cmd_path, "-p", prompt, "--approval-mode", "yolo"]
    if has_session:
        cmd.append("--continue")
    return cmd


async def run_agent(message: types.Message, agent: str, prompt: str, show_status: bool = False):
    """Run an agent CLI and send output to Telegram."""
    global active_agent

    if agent in active_processes:
        await message.reply(f"{agent} is busy. Use /kill {agent} to stop.")
        return

    active_agent = agent

    if show_status and TG_SHOW_STATUS:
        label = "continue" if agent_has_session.get(agent) else "new session"
        await message.reply(f"{agent}: ({label})")

    # Replace @agent references with last output
    prompt = resolve_agent_refs(prompt)

    output_last_message_path: str | None = None
    if agent == "codex" and TG_RESULTS_ONLY:
        fd, output_last_message_path = tempfile.mkstemp(prefix=f"fhbot-{agent}-", suffix=".txt")
        os.close(fd)

    cmd = build_cmd(agent, prompt, output_last_message_path=output_last_message_path)
    logger.info("Running: %s", " ".join(cmd))

    try:
        clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=REPO_PATH,
            env=clean_env,
        )
        active_processes[agent] = proc

        raw_lines: list[str] = []

        async def read_output():
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                raw_lines.append(decoded)

        timeout_sec = AGENT_CONFIG[agent]["timeout"]
        try:
            await asyncio.wait_for(read_output(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            await message.reply(f"{agent}: Timeout ({timeout_sec}s). Killed.")
            return
        finally:
            active_processes.pop(agent, None)

        await proc.wait()
        agent_has_session[agent] = True

        final_message = read_text_file(output_last_message_path).strip() if output_last_message_path else ""
        if final_message:
            all_output = final_message
        else:
            clean_lines = filter_output(raw_lines)
            all_output = "\n".join(clean_lines)

        # Save full output for @agent references
        if all_output.strip():
            agent_last_output[agent] = all_output

        if all_output.strip():
            await bot.send_message(
                chat_id=CHAT_ID,
                text=truncate(f"{agent}:\n{all_output}"),
            )
        else:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=f"{agent}: Done (no output).",
            )

    except FileNotFoundError:
        await message.reply(f"{agent}: CLI not found ({cmd[0]})")
        active_processes.pop(agent, None)
    except Exception as e:
        logger.exception("CLI error for %s", agent)
        await message.reply(f"{agent}: Error: {e}")
        active_processes.pop(agent, None)
    finally:
        if output_last_message_path:
            try:
                os.remove(output_last_message_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    lines = [
        "FHAgents Bot",
        "",
        "Pick agent, then just type:",
        "  /claude <prompt>",
        "  /qwen <prompt>",
        "  /gemini <prompt>",
        "  /codex <prompt>",
        "",
        "After that, plain text goes to",
        "the same agent (with --continue).",
        "",
        "  /new — new session (reset)",
        "  /sessions — active sessions",
        "  /kill — stop process",
        "",
        "Cross-agent:",
        "  @claude @qwen etc in text",
        "  /pass <agent> [prompt]",
        "",
        "  /issue /status /docs /todo",
    ]
    await message.answer("\n".join(lines))


@dp.message(Command("claude"))
async def cmd_claude(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.reply("Usage: /claude <prompt>")
        return
    await run_agent(message, "claude", text, show_status=True)


@dp.message(Command("qwen"))
async def cmd_qwen(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.reply("Usage: /qwen <prompt>")
        return
    await run_agent(message, "qwen", text, show_status=True)


@dp.message(Command("gemini"))
async def cmd_gemini(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.reply("Usage: /gemini <prompt>")
        return
    await run_agent(message, "gemini", text, show_status=True)


@dp.message(Command("codex"))
async def cmd_codex(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.reply("Usage: /codex <prompt>")
        return
    await run_agent(message, "codex", text, show_status=True)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@dp.message(Command("new"))
async def cmd_new(message: types.Message):
    global active_agent
    arg = (message.text or "").partition(" ")[2].strip().lower()

    if arg == "all":
        for key in agent_has_session:
            agent_has_session[key] = False
        active_agent = None
        await message.reply("All sessions reset.")
        return

    if arg in agent_has_session:
        agent_has_session[arg] = False
        if active_agent == arg:
            active_agent = None
        await message.reply(f"Session reset: {arg}")
        return

    if not arg and active_agent:
        agent_has_session[active_agent] = False
        name = active_agent
        active_agent = None
        await message.reply(f"Session reset: {name}")
        return

    await message.reply("Usage: /new [claude|qwen|gemini|codex|all]")


@dp.message(Command("sessions"))
async def cmd_sessions(message: types.Message):
    lines = [f"Active agent: {active_agent or '(none)'}", ""]
    for agent, has in agent_has_session.items():
        status = "active (--continue)" if has else "(no session)"
        lines.append(f"  {agent}: {status}")
    await message.reply("\n".join(lines))


@dp.message(Command("who"))
async def cmd_who(message: types.Message):
    """Show which agents are currently running and on what task."""
    if not active_processes:
        await message.reply("No agents running right now.")
        return

    lines = []
    for agent, proc in active_processes.items():
        pid = proc.pid
        session = "continue" if agent_has_session.get(agent) else "new"
        busy_mark = "\u2699\ufe0f"
        lines.append(f"{busy_mark} {agent} (PID {pid}, {session})")

    # Also show idle agents with sessions
    for agent, has in agent_has_session.items():
        if has and agent not in active_processes:
            lines.append(f"\u23f8 {agent} (idle, has session)")

    header = f"Router \u2192 {active_agent or '(none)'}"
    await message.reply(f"{header}\n\n" + "\n".join(lines))


# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------

@dp.message(Command("pass"))
async def cmd_pass(message: types.Message):
    """Pass last agent's output to another agent."""
    parts = (message.text or "").partition(" ")[2].strip().split(None, 1)
    if not parts:
        await message.reply("Usage: /pass <agent> [prompt]\nExample: /pass qwen Review this")
        return

    target = parts[0].lower()
    extra_prompt = parts[1] if len(parts) > 1 else "Review and analyze the following"

    if target not in AGENT_CONFIG:
        await message.reply(f"Unknown agent: {target}\nAvailable: claude, qwen, gemini, codex")
        return

    # Get output from current active agent
    source = active_agent
    if not source or source not in agent_last_output:
        await message.reply("No output to pass. Run an agent first.")
        return

    last = truncate(agent_last_output[source], 2000)
    full_prompt = f"{extra_prompt}:\n\n{last}"

    await run_agent(message, target, full_prompt, show_status=True)


@dp.message(Command("issue"))
async def cmd_issue(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.reply("Usage: /issue <description>")
        return
    if not GITHUB_TOKEN:
        await message.reply("GITHUB_TOKEN not configured.")
        return
    result = await create_issue(
        title=text[:120],
        body=f"From @{message.from_user.username or 'unknown'}:\n{text}",
    )
    if result:
        await message.reply(f"Issue #{result['number']}: {result['html_url']}")
    else:
        await message.reply("Failed to create issue.")


@dp.message(Command("task"))
async def cmd_task(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.reply("Usage: /task <description>")
        return
    if not GITHUB_TOKEN:
        await message.reply("GITHUB_TOKEN not configured.")
        return
    result = await create_issue(
        title=text[:120],
        body=f"From Telegram by @{message.from_user.username or 'unknown'}:\n{text}",
    )
    if result:
        await message.reply(f"Issue #{result['number']}: {result['html_url']}")
    else:
        await message.reply("Failed to create issue.")


@dp.message(Command("kill"))
async def cmd_kill(message: types.Message):
    arg = (message.text or "").partition(" ")[2].strip().lower()

    if arg and arg in active_processes:
        try:
            active_processes[arg].kill()
        except ProcessLookupError:
            pass
        active_processes.pop(arg, None)
        await message.reply(f"{arg} killed.")
        return

    if not active_processes:
        await message.reply("No active processes.")
        return

    # Kill all
    killed = []
    for name, proc in list(active_processes.items()):
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        killed.append(name)
    active_processes.clear()
    await message.reply(f"Killed: {', '.join(killed)}")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    content = read_local_file("HANDOFF.md", max_lines=20)
    await message.reply(truncate(f"HANDOFF:\n\n{content}"))


@dp.message(Command("docs"))
async def cmd_docs(message: types.Message):
    content = read_local_file("HANDOFF.md", max_lines=120)
    await message.reply(truncate(f"HANDOFF.md:\n\n{content}"))


@dp.message(Command("todo"))
async def cmd_todo(message: types.Message):
    content = read_local_file("docs/current/TODO_CONSOLIDATED.md", max_lines=120)
    await message.reply(truncate(f"TODO:\n\n{content}"))


# ---------------------------------------------------------------------------
# Plain text → active agent (auto-route)
# ---------------------------------------------------------------------------

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_plain_text(message: types.Message):
    """Route plain text messages to the active agent."""
    if not active_agent:
        await message.reply(
            "No active agent. Start with:\n"
            "/claude /qwen /gemini /codex"
        )
        return

    text = (message.text or "").strip()
    if not text:
        return

    await run_agent(message, active_agent, text)


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------

async def handle_hook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    agent = data.get("agent", "unknown")
    text = data.get("text", "")
    event = data.get("event", "")

    if not text and not event:
        return web.Response(status=400, text="Missing text or event")

    emoji = {
        "claude": "\U0001f9d1\u200d\U0001f4bb",
        "codex": "\U0001f916",
        "qwen": "\U0001f9e0",
        "gemini": "\U0001f48e",
    }.get(agent, "\U0001f4e8")

    if event == "commit":
        msg = f"{emoji} {agent}: commit\n{text}"
    elif event == "deploy":
        msg = f"{emoji} {agent}: deploy\n{text}"
    elif event == "error":
        msg = f"\u26a0\ufe0f {agent}: error\n{text}"
    else:
        msg = f"{emoji} {agent}: {text}"

    await bot.send_message(chat_id=CHAT_ID, text=truncate(msg))
    return web.Response(text="ok")


async def handle_github_webhook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    event_type = request.headers.get("X-GitHub-Event", "")

    if event_type == "issue_comment":
        action = data.get("action", "")
        if action == "created":
            issue = data.get("issue", {})
            comment = data.get("comment", {})
            user = comment.get("user", {}).get("login", "unknown")
            body = comment.get("body", "")[:500]
            title = issue.get("title", "")
            number = issue.get("number", "?")
            msg = f"\U0001f4ac GitHub #{number} ({title})\n{user}: {body}"
            await bot.send_message(chat_id=CHAT_ID, text=truncate(msg))

    elif event_type == "issues":
        action = data.get("action", "")
        issue = data.get("issue", {})
        title = issue.get("title", "")
        number = issue.get("number", "?")
        user = issue.get("user", {}).get("login", "unknown")
        if action in ("opened", "closed", "reopened"):
            msg = f"\U0001f4cb Issue #{number} {action}: {title}\nby {user}"
            await bot.send_message(chat_id=CHAT_ID, text=truncate(msg))

    elif event_type == "push":
        pusher = data.get("pusher", {}).get("name", "unknown")
        commits = data.get("commits", [])
        ref = data.get("ref", "").replace("refs/heads/", "")
        if commits:
            lines = [f"\U0001f680 Push to {ref} by {pusher}:"]
            for c in commits[:5]:
                short = c.get("id", "")[:7]
                msg_text = c.get("message", "").split("\n")[0][:80]
                lines.append(f"  {short} {msg_text}")
            if len(commits) > 5:
                lines.append(f"  ... and {len(commits) - 5} more")
            await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines))

    return web.Response(text="ok")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    logger.info("Starting FHAgents Bot (chat_id=%s)", CHAT_ID)

    # Register commands menu in Telegram
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="claude", description="Send prompt to Claude"),
        BotCommand(command="qwen", description="Send prompt to Qwen"),
        BotCommand(command="gemini", description="Send prompt to Gemini"),
        BotCommand(command="codex", description="Send prompt to Codex"),
        BotCommand(command="who", description="Who is running now"),
        BotCommand(command="sessions", description="Session status"),
        BotCommand(command="new", description="Reset session"),
        BotCommand(command="kill", description="Kill agent process"),
        BotCommand(command="pass", description="Pass output to another agent"),
        BotCommand(command="issue", description="Create GitHub issue"),
        BotCommand(command="status", description="Show HANDOFF"),
        BotCommand(command="todo", description="Show TODO list"),
    ])

    available = []
    for name, cfg in AGENT_CONFIG.items():
        cmd = cfg["cmd"]
        if os.path.isfile(cmd) or shutil.which(cmd):
            available.append(name)
        else:
            logger.warning("CLI not found: %s (%s)", name, cmd)

    app = web.Application()
    app.router.add_post("/hook", handle_hook)
    app.router.add_post("/github", handle_github_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    logger.info("Webhook server listening on port %s", WEBHOOK_PORT)

    cli_list = ", ".join(available) if available else "none"
    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"Bot started. CLIs: {cli_list}\n"
            "Type /claude, /qwen, /gemini, or /codex to start.\n"
            "Then just type — auto-routes to active agent."
        ),
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
