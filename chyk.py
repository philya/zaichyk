#!/usr/bin/env python3
"""chyk.py - AI spellcheck/proofread tool for markdown files."""

from __future__ import annotations

import argparse
import difflib
import functools
import re
import sys
from pathlib import Path

from anthropic import Anthropic
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static, TextArea


MODEL = "claude-haiku-4-5-20251001"

PROMPT = (
    "Rewrite this sentence with perfect grammar and syntax and consistent "
    "use of punctuation characters. Don't edit word choice or order, only "
    "correct grammatical mistakes. If the input is not a normal prose "
    "sentence (e.g. a heading, a code fragment, a URL, or a list marker), "
    "return it exactly unchanged. Return only the resulting text with no "
    "commentary, no quotation marks, and no surrounding formatting.\n\n"
    "Input: {sentence}"
)

NON_PROSE_RE = re.compile(r"^(#|```|~~~|\||---+|\*\*\*+|___+)")

# Bracket/quote pairs that should suppress sentence-terminator detection
# while open. Straight single quote is intentionally absent (apostrophe
# collisions in contractions).
_BRACKET_PAIRS: dict[str, str] = {
    "(": ")",
    "[": "]",
    "{": "}",
    "\"": "\"",
    "“": "”",
    "‘": "’",
    "«": "»",
    "‹": "›",
}
_TERMINATORS = ".!?"


def _emphasis_opener(text: str, i: int) -> str | None:
    """If text[i:] starts an emphasis run (`*` or `**`) per a loose CommonMark
    reading, return the opener token; otherwise None.

    Distinguishes from bullet markers (`* `) and arithmetic-style standalone
    asterisks (` * `) by requiring the asterisk(s) to be immediately followed
    by a non-space character.
    """
    n = len(text)
    if text[i] != "*":
        return None
    if text[i : i + 2] == "**":
        j = i + 2
        if j < n and not text[j].isspace() and text[j] != "*":
            return "**"
        return None
    j = i + 1
    if j < n and not text[j].isspace() and text[j] != "*":
        return "*"
    return None


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Return [(start, end, sentence)] for each prose-sentence in text.

    Sentence terminators (`.`, `!`, `?`, line breaks) are ignored while
    inside a balanced quote/bracket/paren/emphasis block, so quoted speech
    or emphasised phrases with internal punctuation stay as one sentence.
    """
    spans: list[tuple[int, int, str]] = []
    n = len(text)
    i = 0
    while i < n:
        while i < n and text[i] in " \t\n":
            i += 1
        if i >= n:
            break
        start = i
        stack: list[str] = []
        while i < n:
            ch = text[i]
            if stack:
                top = stack[-1]
                if top == "**":
                    if text[i : i + 2] == "**" and i > 0 and not text[i - 1].isspace():
                        stack.pop()
                        i += 2
                        continue
                elif top == "*":
                    if ch == "*" and i > 0 and not text[i - 1].isspace():
                        stack.pop()
                        i += 1
                        continue
                elif ch == top:
                    stack.pop()
                    i += 1
                    continue
                if ch in _BRACKET_PAIRS and _BRACKET_PAIRS[ch] != ch:
                    stack.append(_BRACKET_PAIRS[ch])
                    i += 1
                    continue
                opener = _emphasis_opener(text, i)
                if opener is not None:
                    stack.append(opener)
                    i += len(opener)
                    continue
                if ch == "\n" and i + 1 < n and text[i + 1] == "\n":
                    stack.clear()
                    break
                i += 1
                continue
            if ch == "\n":
                break
            opener = _emphasis_opener(text, i)
            if opener is not None:
                stack.append(opener)
                i += len(opener)
                continue
            if ch in _BRACKET_PAIRS:
                stack.append(_BRACKET_PAIRS[ch])
                i += 1
                continue
            if ch in _TERMINATORS:
                i += 1
                while i < n and text[i] in _TERMINATORS:
                    i += 1
                break
            i += 1
        end = i
        raw = text[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        if NON_PROSE_RE.match(stripped):
            continue
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        spans.append((start + lead, end - trail, stripped))
    return spans


_ESCAPABLE = set("\\`*_{}[]()#+-.!|>~")


def strip_markdown(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Strip markdown syntax for LLM input.

    Returns (stripped, spans) where spans[i] is the (start, end) range in
    `text` that produced stripped[i]. The stripped form:
      - drops backslash escapes (`\\.` -> `.`)
      - collapses `---` to em-dash and `--` to en-dash
    """
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i : i + 3] == "---":
            out.append("—")
            spans.append((i, i + 3))
            i += 3
            continue
        if text[i : i + 2] == "--":
            out.append("–")
            spans.append((i, i + 2))
            i += 2
            continue
        if text[i] == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
            out.append(text[i + 1])
            spans.append((i, i + 2))
            i += 2
            continue
        out.append(text[i])
        spans.append((i, i + 1))
        i += 1
    return "".join(out), spans


def reapply_correction(
    original: str,
    stripped: str,
    spans: list[tuple[int, int]],
    corrected: str,
) -> str:
    """Splice an LLM correction (in stripped form) back into `original`.

    Unchanged regions keep the original markdown bytes; changed regions are
    replaced with the LLM's plain text.
    """
    matcher = difflib.SequenceMatcher(a=stripped, b=corrected, autojunk=False)
    parts: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if i2 > i1:
            orig_start = spans[i1][0]
            orig_end = spans[i2 - 1][1]
        elif i1 < len(spans):
            orig_start = orig_end = spans[i1][0]
        elif spans:
            orig_start = orig_end = spans[-1][1]
        else:
            orig_start = orig_end = 0
        if tag == "equal":
            parts.append(original[orig_start:orig_end])
        elif tag in ("replace", "insert"):
            parts.append(corrected[j1:j2])
        # 'delete' -> drop the original chars in this range
    return "".join(parts)


def _diff_highlight(original: str, suggested: str) -> Text:
    """Return `suggested` as Text, with chars that differ from `original` highlighted.

    Inserted/replaced chars are highlighted in yellow. Where chars were
    deleted (present in original, absent in suggested) a red caret `‸` is
    inserted at the position of the deletion.
    """
    matcher = difflib.SequenceMatcher(a=original, b=suggested, autojunk=False)
    out = Text()
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        chunk = suggested[j1:j2]
        if tag == "equal":
            out.append(chunk)
        elif tag in ("replace", "insert"):
            if chunk:
                out.append(chunk, style="black on yellow")
        elif tag == "delete":
            out.append("‸", style="bold red")
    return out


class VBar(Static):
    """A vertical progress bar drawn with block characters."""

    def __init__(self, total: int, **kwargs):
        super().__init__(**kwargs)
        self.total = total
        self.value = 0

    def set_progress(self, value: int) -> None:
        self.value = value
        self.refresh()

    def render(self):
        h = max(self.size.height, 1)
        fill = 0 if self.total == 0 else int(round(h * self.value / self.total))
        lines = []
        for i in range(h):
            lines.append("█" if i < fill else "│")
        text = Text("\n".join(lines))
        text.stylize("green")
        return text


class ChykApp(App):
    CSS = """
    Screen { layout: vertical; }
    #top { height: 1fr; }
    #viewer-scroll { width: 1fr; height: 1fr; border: round white; }
    #viewer { width: 100%; padding: 0 1; }
    #vbar { width: 3; height: 1fr; padding: 0 1; }
    #choices-scroll { height: 8; border: round white; }
    #choices { padding: 0 1; width: 100%; }
    #commands { height: 1; padding: 0 1; color: $accent; }
    #editor { height: 30%; border: round white; display: none; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("escape", "maybe_quit", "Quit"),
    ]

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = Path(filepath)
        self.text = self.filepath.read_text()
        self.spans = split_sentences(self.text)
        self.delta = 0
        self.idx = -1
        self.current_span: tuple[int, int] | None = None
        self.current_sentence: str = ""
        self.current_stripped: str = ""
        self.current_spans: list[tuple[int, int]] = []
        self.current_correction: str = ""
        self.client = Anthropic()
        self.skip_path = self.filepath.with_suffix(self.filepath.suffix + ".chyk")
        self.skip_set: set[str] = self._load_skip_set()
        # Modes: thinking | choosing | editing | done
        self.mode = "thinking"

    def _load_skip_set(self) -> set[str]:
        if not self.skip_path.exists():
            return set()
        return {line for line in self.skip_path.read_text().splitlines() if line}

    def _mark_skipped(self, sentence: str) -> None:
        if sentence in self.skip_set:
            return
        self.skip_set.add(sentence)
        with open(self.skip_path, "a") as f:
            f.write(sentence + "\n")

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            with VerticalScroll(id="viewer-scroll"):
                yield Static("", id="viewer")
            yield VBar(len(self.spans), id="vbar")
        with VerticalScroll(id="choices-scroll"):
            yield Static("Loading...", id="choices")
        yield Static("", id="commands")
        yield TextArea("", id="editor")

    def on_mount(self) -> None:
        self.update_viewer()
        self.advance()

    # --- viewer ----------------------------------------------------------

    def update_viewer(self, highlight: tuple[int, int] | None = None) -> None:
        view = Text()
        if highlight is None:
            view.append(self.text)
        else:
            s, e = highlight
            view.append(self.text[:s])
            view.append(self.text[s:e], style="black on yellow")
            view.append(self.text[e:])
        self.query_one("#viewer", Static).update(view)

    def scroll_to_span(self, start: int) -> None:
        line = self._visual_row(start)
        scroll = self.query_one("#viewer-scroll", VerticalScroll)
        viewport_top = int(scroll.scroll_y)
        viewport_height = scroll.size.height
        if viewport_height and viewport_top <= line < viewport_top + viewport_height:
            return
        scroll.scroll_to(y=line, animate=False)

    def _visual_row(self, char_offset: int) -> int:
        """Return the wrapped-render row that contains `char_offset` in self.text."""
        width = self.query_one("#viewer", Static).content_size.width
        if width <= 0:
            return self.text[:char_offset].count("\n")
        src = self.text[:char_offset]
        lines = src.split("\n")
        row = 0
        for i, line in enumerate(lines):
            if i == len(lines) - 1:
                row += len(line) // width
            else:
                row += max(1, -(-len(line) // width))
        return row

    # --- main flow -------------------------------------------------------

    def advance(self) -> None:
        while True:
            self.idx += 1
            self.query_one(VBar).set_progress(self.idx)
            if self.idx >= len(self.spans):
                self.finish()
                return
            orig_start, orig_end, _ = self.spans[self.idx]
            start = orig_start + self.delta
            end = orig_end + self.delta
            current = self.text[start:end]
            if current in self.skip_set:
                continue
            break
        self._check_sentence(start, end, current)

    def _check_sentence(self, start: int, end: int, current: str) -> None:
        stripped, spans = strip_markdown(current)
        self.current_span = (start, end)
        self.current_sentence = current
        self.current_stripped = stripped
        self.current_spans = spans
        self.update_viewer((start, end))
        self.scroll_to_span(start)
        self.mode = "thinking"
        self.query_one("#choices", Static).update(
            Text.from_markup(f"[dim]Checking {self.idx + 1}/{len(self.spans)}...[/]")
        )
        self._set_commands("[Esc] Quit")
        self.run_worker(
            functools.partial(self.fetch_correction, stripped),
            exclusive=True,
            thread=True,
        )

    def fetch_correction(self, sentence: str) -> None:
        try:
            msg = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": PROMPT.format(sentence=sentence)}
                ],
            )
            correction = msg.content[0].text.strip()
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._on_correction_error, str(exc))
            return
        self.call_from_thread(self._on_correction, sentence, correction)

    def _on_correction(self, sentence: str, correction: str) -> None:
        if correction == sentence:
            self._mark_skipped(self.current_sentence)
            self.advance()
            return
        reapplied = reapply_correction(
            self.current_sentence, sentence, self.current_spans, correction
        )
        if reapplied == self.current_sentence:
            self._mark_skipped(self.current_sentence)
            self.advance()
            return
        self.current_correction = reapplied
        self.show_choices()

    def _on_correction_error(self, err: str) -> None:
        self.query_one("#choices", Static).update(
            Text.from_markup(f"[red]LLM error:[/] {err}")
        )
        self._set_commands("[n] Skip   [Esc] Quit")
        self.mode = "error"

    def show_choices(self) -> None:
        body = Text()
        body.append("Original:  ", style="bold")
        body.append(self.current_sentence + "\n")
        body.append("Suggested: ", style="bold green")
        body.append(_diff_highlight(self.current_sentence, self.current_correction))
        self.query_one("#choices", Static).update(body)
        self._set_commands(
            "[a] Apply   [k] Keep   [s] Skip   [e] Edit   [Esc] Quit"
        )
        self.query_one("#choices-scroll", VerticalScroll).scroll_home(animate=False)
        self.mode = "choosing"

    def start_edit(self, initial: str) -> None:
        editor = self.query_one("#editor", TextArea)
        editor.display = True
        editor.text = initial
        editor.focus()
        self.mode = "editing"
        self._set_commands("[Ctrl+A] Apply & recheck   [Esc] Cancel")

    def _close_editor(self) -> None:
        editor = self.query_one("#editor", TextArea)
        editor.text = ""
        editor.display = False
        self.set_focus(None)

    def _set_commands(self, text: str) -> None:
        self.query_one("#commands", Static).update(Text(text))

    def skip(self) -> None:
        """Move to the next sentence without editing or recording a skip entry."""
        self._close_editor()
        self.advance()

    def commit(self, new_sentence: str, recheck: bool = False) -> None:
        assert self.current_span is not None
        start, end = self.current_span
        old = self.text[start:end]
        if new_sentence != old:
            self.text = self.text[:start] + new_sentence + self.text[end:]
            self.delta += len(new_sentence) - len(old)
            self._save_file()
        elif not recheck:
            self._mark_skipped(self.current_sentence)
        self._close_editor()
        if recheck:
            self._check_sentence(start, start + len(new_sentence), new_sentence)
        else:
            self.advance()

    def _save_file(self) -> None:
        tmp = self.filepath.with_suffix(self.filepath.suffix + ".chyk.tmp")
        tmp.write_text(self.text)
        tmp.replace(self.filepath)

    def finish(self) -> None:
        self.mode = "done"
        self.filepath.write_text(self.text)
        self.query_one("#choices", Static).update(
            Text.from_markup("[green]Done.[/]")
        )
        self._set_commands("[Esc] Quit")
        self.update_viewer()

    # --- key handling ----------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        if self.mode == "choosing":
            if event.key in ("a", "ф"):
                event.stop()
                self.commit(self.current_correction)
            elif event.key in ("k", "л"):
                event.stop()
                self.commit(self.current_sentence)
            elif event.key in ("s", "і"):
                event.stop()
                self.skip()
            elif event.key in ("e", "у"):
                event.stop()
                self.start_edit(self.current_sentence)
        elif self.mode == "editing":
            if event.key in ("ctrl+a", "ctrl+ф"):
                event.stop()
                event.prevent_default()
                editor = self.query_one("#editor", TextArea)
                self.commit(editor.text.strip(), recheck=True)
            elif event.key == "escape":
                event.stop()
                event.prevent_default()
                self._close_editor()
                self.show_choices()
        elif self.mode == "error":
            if event.key == "n":
                event.stop()
                self.advance()

    def action_maybe_quit(self) -> None:
        if self.mode == "editing":
            return
        self.exit()


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-powered markdown spellchecker.")
    parser.add_argument("file", help="Path to the markdown file to proofread.")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    ChykApp(str(path)).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
