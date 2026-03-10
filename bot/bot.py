"""
FHAgents Telegram Bot — thread-scoped dispatcher for CLI agents.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiohttp import web

from agent_adapters import BaseAgentAdapter, build_agent_adapters
from state_store import BotStateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "WeLizard/FilamentHub")
REPO_PATH = os.environ.get("REPO_PATH", "/repo")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8090"))
HOOK_SECRET = os.environ.get("HOOK_SECRET", "").strip()
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip()
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

ADAPTERS: dict[str, BaseAgentAdapter] = build_agent_adapters(AGENT_CONFIG)
STATE_STORE = BotStateStore(Path(__file__).with_name("state.json"), list(ADAPTERS))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
AGENT_MENTION_RE = re.compile(r"@(?P<agent>claude|qwen|gemini|codex)\b", re.IGNORECASE)


@dataclass
class ActiveRun:
    run_id: str
    thread_key: str
    thread_label: str
    agent: str
    process: asyncio.subprocess.Process
    source_message_id: int | None
    started_at: datetime


active_runs: dict[str, ActiveRun] = {}

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
        with open(full_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if len(lines) > max_lines:
            text = "".join(lines[:max_lines])
            text += f"\n... ({len(lines) - max_lines} lines truncated)"
            return text
        return "".join(lines)
    except FileNotFoundError:
        return f"File not found: {relative_path}"
    except Exception as exc:
        return f"Error reading {relative_path}: {exc}"


def truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n... (truncated)"


def read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""
    except Exception as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return ""

NOISE_PATTERNS = [
    re.compile(r"^mcp:"),
    re.compile(r"^-{4,}"),
    re.compile(r"^(workdir|model|provider|approval|sandbox|reasoning|session id):"),  # Codex header
    re.compile(r"^OpenAI Codex"),
    re.compile(r"^exec$"),
    re.compile(r'^"[A-Z]:\\'),
    re.compile(r"^(user|codex|assistant)$"),
    re.compile(r"^\s*succeeded in \d+ms"),
    re.compile(r"^\s*in [A-Z]:\\"),
]

def is_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return any(p.search(stripped) for p in NOISE_PATTERNS)


def filter_output(lines: list[str]) -> list[str]:
    cleaned_lines = [ANSI_ESCAPE_RE.sub("", line) for line in lines]
    return [line for line in cleaned_lines if not is_noise(line)]

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_thread_context(message: types.Message) -> tuple[str, int, int | None, str]:
    chat_id = int(message.chat.id)
    raw_topic_id = getattr(message, "message_thread_id", None)
    topic_id = int(raw_topic_id) if isinstance(raw_topic_id, int) else None
    suffix = str(topic_id) if topic_id is not None else "root"
    thread_key = f"telegram:{chat_id}:{suffix}"
    thread_label = f"{chat_id}/topic:{topic_id}" if topic_id is not None else f"{chat_id}/root"
    return thread_key, chat_id, topic_id, thread_label


def get_thread_state(message: types.Message) -> tuple[str, int, int | None, str, dict]:
    thread_key, chat_id, topic_id, thread_label = resolve_thread_context(message)
    state = STATE_STORE.get_thread_state(thread_key, chat_id, topic_id)
    return thread_key, chat_id, topic_id, thread_label, state


def get_thread_runs(thread_key: str) -> list[ActiveRun]:
    return [run for run in active_runs.values() if run.thread_key == thread_key]


def get_active_run(thread_key: str, agent: str) -> ActiveRun | None:
    for run in active_runs.values():
        if run.thread_key == thread_key and run.agent == agent:
            return run
    return None


def human_elapsed(started_at: datetime) -> str:
    elapsed = max(0, int((datetime.now(timezone.utc) - started_at).total_seconds()))
    if elapsed < 60:
        return f"{elapsed}s"
    minutes, seconds = divmod(elapsed, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def resolve_explicit_agent_route(text: str) -> tuple[str | None, str | None]:
    matches = [match.group("agent").lower() for match in AGENT_MENTION_RE.finditer(text)]
    unique_agents = list(dict.fromkeys(matches))
    if len(unique_agents) > 1:
        return None, "Multiple @agent mentions found. Use /ask agent1,agent2 <prompt>."
    if not unique_agents:
        return None, None
    cleaned = AGENT_MENTION_RE.sub("", text).strip()
    if not cleaned:
        return None, "Agent mention found, but prompt is empty."
    return unique_agents[0], cleaned


def get_agent_session_ref(state: dict, agent: str) -> str | None:
    agent_state = state.get("agents", {}).get(agent, {})
    session_ref = agent_state.get("session_ref")
    return session_ref if isinstance(session_ref, str) and session_ref.strip() else None


def get_agent_last_output(state: dict, agent: str) -> str:
    agent_state = state.get("agents", {}).get(agent, {})
    last_output = agent_state.get("last_output")
    return last_output if isinstance(last_output, str) else ""


def is_agent_available(agent: str) -> bool:
    adapter = ADAPTERS[agent]
    return os.path.isfile(adapter.command_path) or bool(shutil.which(adapter.command_path))


async def run_agent(message: types.Message, agent: str, prompt: str):
    thread_key, chat_id, topic_id, thread_label, state = get_thread_state(message)

    if agent not in ADAPTERS:
        await message.reply(f"Unknown agent: {agent}")
        return

    if not prompt.strip():
        await message.reply("Prompt is empty.")
        return

    if not is_agent_available(agent):
        await message.reply(f"{agent}: CLI not found ({ADAPTERS[agent].command_path})")
        return

    existing_run = get_active_run(thread_key, agent)
    if existing_run:
        await message.reply(f"{agent} is already busy in this thread (run {existing_run.run_id}).")
        return

    adapter = ADAPTERS[agent]
    existing_session_ref = get_agent_session_ref(state, agent) if adapter.supports_persistent_sessions else None

    output_last_message_path: str | None = None
    if agent == "codex" and TG_RESULTS_ONLY:
        fd, output_last_message_path = tempfile.mkstemp(prefix=f"fhbot-{agent}-", suffix=".txt")
        os.close(fd)

    prepared = adapter.prepare_run(prompt, existing_session_ref, output_last_message_path)
    run_id = uuid.uuid4().hex[:8]

    if TG_SHOW_STATUS:
        mode = "resume" if existing_session_ref else ("persistent" if prepared.session_ref else "new")
        await message.reply(f"{agent} [{run_id}]: {mode}")

    logger.info("Running %s in %s: %s", agent, thread_label, " ".join(prepared.command))

    try:
        clean_env = {key: value for key, value in os.environ.items() if key != "CLAUDECODE"}
        process = await asyncio.create_subprocess_exec(
            *prepared.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=REPO_PATH,
            env=clean_env,
        )
        active_runs[run_id] = ActiveRun(
            run_id=run_id,
            thread_key=thread_key,
            thread_label=thread_label,
            agent=agent,
            process=process,
            source_message_id=message.message_id,
            started_at=datetime.now(timezone.utc),
        )

        raw_lines: list[str] = []

        async def read_output() -> None:
            assert process.stdout is not None
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                raw_lines.append(line.decode("utf-8", errors="replace").rstrip())

        try:
            await asyncio.wait_for(read_output(), timeout=adapter.timeout)
        except asyncio.TimeoutError:
            process.kill()
            await message.reply(f"{agent} [{run_id}]: Timeout ({adapter.timeout}s). Killed.")
            return
        finally:
            active_runs.pop(run_id, None)

        await process.wait()

        final_message = read_text_file(output_last_message_path).strip() if output_last_message_path else ""
        if final_message:
            all_output = final_message
        else:
            all_output = "\n".join(filter_output(raw_lines))

        session_ref = adapter.resolve_session_ref(raw_lines, prepared.session_ref)
        STATE_STORE.update_agent_state(
            thread_key,
            chat_id,
            topic_id,
            agent,
            session_ref=session_ref if adapter.supports_persistent_sessions else None,
            last_output=truncate(all_output.strip(), 8000),
            last_run_at=now_iso(),
        )

        if all_output.strip():
            await message.reply(truncate(f"{agent} [{run_id}]:\n{all_output}"))
        else:
            await message.reply(f"{agent} [{run_id}]: Done (no output).")

    except FileNotFoundError:
        await message.reply(f"{agent}: CLI not found ({prepared.command[0]})")
    except Exception as exc:
        logger.exception("CLI error for %s", agent)
        await message.reply(f"{agent}: Error: {exc}")
    finally:
        active_runs.pop(run_id, None)
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
        "Thread-aware routing:",
        "  /use <agent>",
        "  /claude <prompt>",
        "  /qwen <prompt>",
        "  /gemini <prompt>",
        "  /codex <prompt>",
        "",
        "Parallel:",
        "  /ask codex,claude <prompt>",
        "",
        "Visible handoff:",
        "  /pass <agent> [prompt]",
        "  @codex fix this",
        "",
        "Status:",
        "  /status /sessions /who /new /kill",
        "",
        "Docs:",
        "  /docs /todo /botdocs /bottodo",
    ]
    await message.answer("\n".join(lines))


async def run_direct_command(message: types.Message, agent: str):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.reply(f"Usage: /{agent} <prompt>")
        return

    thread_key, chat_id, topic_id, _, _ = get_thread_state(message)
    STATE_STORE.set_active_agent(thread_key, chat_id, topic_id, agent)
    await run_agent(message, agent, text)


@dp.message(Command("claude"))
async def cmd_claude(message: types.Message):
    await run_direct_command(message, "claude")


@dp.message(Command("qwen"))
async def cmd_qwen(message: types.Message):
    await run_direct_command(message, "qwen")


@dp.message(Command("gemini"))
async def cmd_gemini(message: types.Message):
    await run_direct_command(message, "gemini")


@dp.message(Command("codex"))
async def cmd_codex(message: types.Message):
    await run_direct_command(message, "codex")


@dp.message(Command("use"))
async def cmd_use(message: types.Message):
    agent = (message.text or "").partition(" ")[2].strip().lower()
    if agent not in ADAPTERS:
        await message.reply("Usage: /use <claude|qwen|gemini|codex>")
        return

    thread_key, chat_id, topic_id, _, _ = get_thread_state(message)
    STATE_STORE.set_active_agent(thread_key, chat_id, topic_id, agent)
    await message.reply(f"Active agent for this thread: {agent}")


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@dp.message(Command("new"))
async def cmd_new(message: types.Message):
    arg = (message.text or "").partition(" ")[2].strip().lower()
    thread_key, chat_id, topic_id, _, state = get_thread_state(message)

    if arg == "all":
        busy_agents = [run.agent for run in get_thread_runs(thread_key)]
        if busy_agents:
            await message.reply(f"Cannot reset while busy: {', '.join(sorted(set(busy_agents)))}")
            return
        STATE_STORE.reset_thread(thread_key, chat_id, topic_id)
        await message.reply("Current thread sessions reset.")
        return

    if arg in ADAPTERS:
        if get_active_run(thread_key, arg):
            await message.reply(f"Cannot reset {arg} while it is running.")
            return
        STATE_STORE.reset_agent(thread_key, chat_id, topic_id, arg)
        await message.reply(f"Session reset for this thread: {arg}")
        return

    active_agent = state.get("active_agent")
    if not arg and isinstance(active_agent, str) and active_agent in ADAPTERS:
        if get_active_run(thread_key, active_agent):
            await message.reply(f"Cannot reset {active_agent} while it is running.")
            return
        STATE_STORE.reset_agent(thread_key, chat_id, topic_id, active_agent)
        await message.reply(f"Session reset for this thread: {active_agent}")
        return

    await message.reply("Usage: /new [claude|qwen|gemini|codex|all]")


def build_status_text(message: types.Message) -> str:
    thread_key, _, _, thread_label, state = get_thread_state(message)
    lines = [
        f"Thread: {thread_label}",
        f"Key: {thread_key}",
        f"Active agent: {state.get('active_agent') or '(none)'}",
        "",
        "Agents:",
    ]
    busy_map = {run.agent: run for run in get_thread_runs(thread_key)}
    for agent, adapter in ADAPTERS.items():
        agent_state = state.get("agents", {}).get(agent, {})
        session_ref = agent_state.get("session_ref")
        session_display = (
            truncate(str(session_ref), 24)
            if isinstance(session_ref, str) and session_ref.strip()
            else ("stateless" if not adapter.supports_persistent_sessions else "(none)")
        )
        run = busy_map.get(agent)
        status = f"busy {run.run_id} ({human_elapsed(run.started_at)})" if run else "idle"
        last_run_at = agent_state.get("last_run_at") or "-"
        has_output = "yes" if agent_state.get("last_output") else "no"
        lines.append(
            f"  {agent}: {status}; session={session_display}; last_output={has_output}; last_run_at={last_run_at}"
        )
    return "\n".join(lines)


@dp.message(Command("sessions"))
async def cmd_sessions(message: types.Message):
    await message.reply(build_status_text(message))


@dp.message(Command("who"))
async def cmd_who(message: types.Message):
    if not active_runs:
        await message.reply("No active runs right now.")
        return

    lines = ["Active runs:"]
    for run in sorted(active_runs.values(), key=lambda item: item.started_at):
        lines.append(f"  {run.run_id}: {run.agent} in {run.thread_label} ({human_elapsed(run.started_at)})")
    await message.reply("\n".join(lines))


# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------

@dp.message(Command("pass"))
async def cmd_pass(message: types.Message):
    parts = (message.text or "").partition(" ")[2].strip().split(None, 1)
    if not parts:
        await message.reply("Usage: /pass <agent> [prompt]")
        return

    target = parts[0].lower()
    extra_prompt = parts[1] if len(parts) > 1 else "Review and analyze the following"

    if target not in ADAPTERS:
        await message.reply(f"Unknown agent: {target}")
        return

    _, _, _, _, state = get_thread_state(message)
    source = state.get("active_agent")
    if source not in ADAPTERS:
        await message.reply("No active agent in this thread. Use /use first.")
        return

    last_output = get_agent_last_output(state, str(source))
    if not last_output:
        await message.reply(f"No output to pass from {source}.")
        return

    await message.reply(f"{source} -> {target}")
    full_prompt = f"{extra_prompt}:\n\n{truncate(last_output, 3000)}"
    await run_agent(message, target, full_prompt)


@dp.message(Command("ask"))
async def cmd_ask(message: types.Message):
    payload = (message.text or "").partition(" ")[2].strip()
    if not payload:
        await message.reply("Usage: /ask codex,claude <prompt>")
        return

    parts = payload.split(None, 1)
    if len(parts) != 2:
        await message.reply("Usage: /ask codex,claude <prompt>")
        return

    raw_agents, prompt = parts
    agents: list[str] = []
    for raw_agent in raw_agents.split(","):
        agent = raw_agent.strip().lower()
        if not agent:
            continue
        if agent not in ADAPTERS:
            await message.reply(f"Unknown agent: {agent}")
            return
        if agent not in agents:
            agents.append(agent)

    if not agents or not prompt.strip():
        await message.reply("Usage: /ask codex,claude <prompt>")
        return

    await message.reply(f"Parallel run: {', '.join(agents)}")
    await asyncio.gather(*(run_agent(message, agent, prompt) for agent in agents))


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
    thread_key, _, _, _, _ = get_thread_state(message)
    thread_runs = get_thread_runs(thread_key)

    if not thread_runs:
        await message.reply("No active runs in this thread.")
        return

    to_kill: list[ActiveRun] = []
    if not arg or arg == "all":
        to_kill = thread_runs
    else:
        by_run_id = next((run for run in thread_runs if run.run_id.startswith(arg)), None)
        by_agent = next((run for run in thread_runs if run.agent == arg), None)
        selected = by_run_id or by_agent
        if not selected:
            await message.reply("Usage: /kill [agent|run_id|all]")
            return
        to_kill = [selected]

    killed: list[str] = []
    for run in to_kill:
        try:
            run.process.kill()
        except ProcessLookupError:
            pass
        active_runs.pop(run.run_id, None)
        killed.append(f"{run.agent} [{run.run_id}]")
    await message.reply(f"Killed: {', '.join(killed)}")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    await message.reply(build_status_text(message))


@dp.message(Command("docs"))
async def cmd_docs(message: types.Message):
    content = read_local_file("HANDOFF.md", max_lines=120)
    await message.reply(truncate(f"HANDOFF.md:\n\n{content}"))


@dp.message(Command("todo"))
async def cmd_todo(message: types.Message):
    content = read_local_file("docs/current/TODO_CONSOLIDATED.md", max_lines=120)
    await message.reply(truncate(f"TODO:\n\n{content}"))


@dp.message(Command("botdocs"))
async def cmd_botdocs(message: types.Message):
    content = read_local_file("bot/HANDOFF.md", max_lines=120)
    await message.reply(truncate(f"bot/HANDOFF.md:\n\n{content}"))


@dp.message(Command("bottodo"))
async def cmd_bottodo(message: types.Message):
    content = read_local_file("bot/TODO.md", max_lines=120)
    await message.reply(truncate(f"bot/TODO.md:\n\n{content}"))


# ---------------------------------------------------------------------------
# Plain text → active agent (auto-route)
# ---------------------------------------------------------------------------

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_plain_text(message: types.Message):
    text = (message.text or "").strip()
    if not text:
        return

    explicit_agent, route_error = resolve_explicit_agent_route(text)
    if route_error:
        await message.reply(route_error)
        return

    if explicit_agent:
        cleaned_prompt = AGENT_MENTION_RE.sub("", text).strip()
        await run_agent(message, explicit_agent, cleaned_prompt)
        return

    _, _, _, _, state = get_thread_state(message)
    active_agent = state.get("active_agent")
    if not isinstance(active_agent, str) or active_agent not in ADAPTERS:
        await message.reply("No active agent in this thread. Use /use <agent> or /claude /codex ...")
        return

    await run_agent(message, active_agent, text)


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------

async def handle_hook(request: web.Request) -> web.Response:
    if HOOK_SECRET:
        provided = request.headers.get("X-FH-Hook-Secret", "")
        if not hmac.compare_digest(provided, HOOK_SECRET):
            return web.Response(status=401, text="unauthorized")

    try:
        body = await request.read()
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    agent = str(data.get("agent", "unknown"))
    text = str(data.get("text", ""))
    event = str(data.get("event", ""))

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
    body = await request.read()
    if GITHUB_WEBHOOK_SECRET:
        provided = request.headers.get("X-Hub-Signature-256", "")
        if not provided.startswith("sha256="):
            return web.Response(status=401, text="unauthorized")
        digest = hmac.new(
            GITHUB_WEBHOOK_SECRET.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        expected = f"sha256={digest}"
        if not hmac.compare_digest(provided, expected):
            return web.Response(status=401, text="unauthorized")

    try:
        data = json.loads(body.decode("utf-8"))
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


async def handle_health(_: web.Request) -> web.Response:
    available_agents = sorted([name for name in ADAPTERS if is_agent_available(name)])
    payload = {
        "status": "ok",
        "active_runs": len(active_runs),
        "available_agents": available_agents,
    }
    return web.json_response(payload)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    logger.info("Starting FHAgents Bot (chat_id=%s)", CHAT_ID)

    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="use", description="Set active agent for this thread"),
        BotCommand(command="claude", description="Send prompt to Claude"),
        BotCommand(command="qwen", description="Send prompt to Qwen"),
        BotCommand(command="gemini", description="Send prompt to Gemini"),
        BotCommand(command="codex", description="Send prompt to Codex"),
        BotCommand(command="ask", description="Run multiple agents in parallel"),
        BotCommand(command="pass", description="Pass output to another agent"),
        BotCommand(command="status", description="Show current thread status"),
        BotCommand(command="sessions", description="Alias for thread status"),
        BotCommand(command="who", description="Show active runs"),
        BotCommand(command="new", description="Reset current thread sessions"),
        BotCommand(command="kill", description="Kill runs in current thread"),
        BotCommand(command="issue", description="Create GitHub issue"),
        BotCommand(command="todo", description="Show project TODO"),
        BotCommand(command="bottodo", description="Show bot TODO"),
        BotCommand(command="botdocs", description="Show bot handoff"),
    ])

    available: list[str] = []
    for name in ADAPTERS:
        if is_agent_available(name):
            available.append(name)
        else:
            logger.warning("CLI not found: %s (%s)", name, ADAPTERS[name].command_path)

    app = web.Application()
    app.router.add_get("/healthz", handle_health)
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
            "Use /use <agent> per thread, or /ask agent1,agent2 <prompt> for parallel runs."
        ),
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
