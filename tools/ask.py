#!/usr/bin/env python3
"""
ask.py — Terminal UI for daily conversation with Swami ji, grounded in distillation.md.

Setup (one-time):
    python3 -m pip install --user anthropic
    export ANTHROPIC_API_KEY=sk-ant-...        # add to ~/.zshrc to persist

Usage:
    python3 tools/ask.py                       # ask a question, append to guidance.md
    python3 tools/ask.py search "kali"         # search past journal entries
    python3 tools/ask.py search --since 2026-05-01

The script reads distillation.md as the grounding context and uses prompt
caching, so repeated calls in a session are fast and cheap.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("Missing dependency. Run: python3 -m pip install --user anthropic")

ROOT = Path(__file__).resolve().parent.parent
DISTILLATION = ROOT / "distillation.md"
GUIDANCE = ROOT / "guidance.md"

MODEL = os.environ.get("OMSWAMI_MODEL", "claude-opus-4-7")

SYSTEM_INSTRUCTIONS = """You are responding in the voice of Om Swami ji as captured in the distillation below — a faithful, ever-growing portrait of his teachings drawn from his own blogs and podcasts.

Rules you must follow:

1. **Ground every response in the distillation.** Use only his teachings, his stories, his analogies, his Sanskrit invocations, his salutations. Do not invent teachings, mantras, or claims he has not given. If the disciple asks about something not covered, say so honestly — *"my friend, on this I cannot speak from what I have shared with you so far"* — rather than fabricate.

2. **Adopt his tone, voice, and cadence precisely** as catalogued in the distillation:
   - Open with his standard salutation when appropriate: *"First of all, I offer my obeisance to the Divine in you."*
   - Address the listener as *"my friend"* — warmly, especially when delivering a hard truth.
   - Build with everyday analogies first, then introduce Sanskrit framework second (mirror, salty water, restaurant, well-digger, supermarket, professor's teacup, etc. — whichever fits).
   - Use rhetorical questions that ask the listener to think (*"What does that tell you?" / "Do you have any proof?"*).
   - Be direct but kind. He says uncomfortable truths softly but firmly.
   - Avoid grandiose language. Never call the listener "seeker" or "child."
   - Use dry, gentle humor when fitting — never punching down.
   - Close with the disciple's-choice flourish when appropriate: *"If what I have said is useful, you are free to keep it. Else you are free to just discard it. That's all I have for you today."*
   - End with a chant or seal: *"Hari Om Tat Sat. Hari Om Tat Sat. Hari Om Tat Sat."* or *"Breathe. Smile. Let go."* or simply *"Jai Shri Hari."*

3. **Length and shape.** Match the spaciousness of one of his talks — long enough to develop one image or teaching properly, not so long it lectures. Roughly 400–700 words is typical. Build with one or two stories or analogies from the distillation, then arrive at the practical direction.

4. **Path of Ma (Tantra/Mahavidya) questions:** If and only if the distillation contains specific Tantra teachings (Mahavidyas, Sri Vidya, japa+yagna protocol, the "It is always Ma" principle, etc.), draw on them. Otherwise stay with the universal sadhana method — purity, discipline, give-before-take, turn inward, one well dug deeply.

Do not break character. Do not refer to yourself as an AI or a model. You are speaking as Swami ji, grounded only in what is in the distillation below."""


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_ask(args: argparse.Namespace) -> None:
    if not DISTILLATION.exists():
        sys.exit(f"Cannot find {DISTILLATION}. Are you running from the repo root?")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it first.\n  export ANTHROPIC_API_KEY=sk-ant-...")

    distillation = DISTILLATION.read_text()

    print()
    print("🪷  Jai Shri Hari.")
    print()
    print("Sit for a moment. Then ask Swami ji your question.")
    print("(Type your question. Press Enter twice when done.)")
    print()

    question = _read_multiline("Question: ").strip()
    if not question:
        sys.exit("No question entered.")

    context = _read_multiline("Context (optional, press Enter twice to skip): ").strip()

    print()
    print("🕉️   Asking Swami ji ...")
    print()

    client = anthropic.Anthropic()

    # System content: stable voice instructions + distillation (cached together).
    system_blocks = [
        {"type": "text", "text": SYSTEM_INSTRUCTIONS},
        {
            "type": "text",
            "text": f"<distillation>\n{distillation}\n</distillation>",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    user_message = f"Question: {question}"
    if context:
        user_message += f"\n\nContext: {context}"

    # Stream the response so the disciple sees Swami ji's words arrive.
    response_text_parts: list[str] = []
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system_blocks,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            response_text_parts.append(text)
        final = stream.get_final_message()

    response_text = "".join(response_text_parts).strip()
    print("\n")

    # Reflection
    print("─" * 60)
    print("Take a moment to sit with what was said.")
    reflection = _read_multiline(
        "Reflection (optional — what landed for you? Press Enter twice to skip): "
    ).strip()

    # Append to guidance.md
    _append_to_journal(question=question, context=context,
                       response=response_text, reflection=reflection,
                       model=final.model, usage=final.usage)

    # Cost / cache info
    u = final.usage
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
    print()
    print(f"✓ Appended to guidance.md")
    print(f"  tokens — in: {u.input_tokens}, out: {u.output_tokens}, "
          f"cache read: {cache_read}, cache write: {cache_write}")
    print()
    print("Hari Om Tat Sat.")
    print()


def cmd_search(args: argparse.Namespace) -> None:
    if not GUIDANCE.exists():
        sys.exit(f"Cannot find {GUIDANCE}.")
    text = GUIDANCE.read_text()
    entries = _parse_journal_entries(text)
    if not entries:
        sys.exit("No journal entries found.")

    matches = entries
    if args.query:
        q = args.query.lower()
        matches = [e for e in matches if q in e["body"].lower()]
    if args.since:
        cutoff = _parse_date(args.since)
        matches = [e for e in matches if e["date"] and e["date"] >= cutoff]

    if not matches:
        print("No matching entries.")
        return

    for e in matches:
        print("─" * 60)
        print(e["header"])
        print()
        print(e["body"].strip())
        print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_multiline(prompt: str) -> str:
    """Read multi-line input. Empty line ends input."""
    print(prompt)
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line and (not lines or not lines[-1]):
            break
        lines.append(line)
    return "\n".join(lines).rstrip()


def _append_to_journal(*, question: str, context: str, response: str,
                       reflection: str, model: str, usage) -> None:
    now = dt.datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    section = [f"\n## {stamp}", "", f"**Question:** {question}", ""]
    if context:
        section += [f"**Context:** {context}", ""]
    section += ["**Response (in the voice of Swami ji, grounded in `distillation.md`):**",
                "", response, ""]
    if reflection:
        section += ["**Reflection:**", "", reflection, ""]
    section.append(f"<sub>{model}</sub>")
    section.append("")

    with GUIDANCE.open("a") as f:
        f.write("\n".join(section))


_HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?:[ T]?(\d{2}:\d{2}))?\s*$")


def _parse_journal_entries(text: str) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    in_journal = False
    for line in text.splitlines():
        if line.strip() == "## Journal":
            in_journal = True
            continue
        m = _HEADER_RE.match(line)
        if m:
            if current:
                entries.append(current)
            date = _parse_date(m.group(1))
            current = {"header": line, "date": date, "body": ""}
            continue
        if current is not None:
            current["body"] += line + "\n"
    if current:
        entries.append(current)
    return entries


def _parse_date(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("ask", help="Ask Swami ji a question (default)")

    p_search = sub.add_parser("search", help="Search past journal entries")
    p_search.add_argument("query", nargs="?", help="Keyword to search for (case-insensitive)")
    p_search.add_argument("--since", help="Only entries on/after YYYY-MM-DD")

    args = p.parse_args()
    cmd = args.cmd or "ask"
    if cmd == "ask":
        cmd_ask(args)
    elif cmd == "search":
        cmd_search(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
