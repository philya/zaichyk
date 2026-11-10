A tool for spellchecking and proofreading markdown text.

    chyk <file>

It splits the text into sentences and sends each one to an LLM via [OpenRouter](https://openrouter.ai) (`~openai/gpt-luna-latest` by default). The prompt is something like this: "Rewrite this sentence with perfect spelling, grammar and syntax and consistent use of punctuation characters, following the current official Ukrainian orthography (Український правопис). Don't edit word choice or order, only correct mistakes."

## Installation

Install it as a command for the current user with [uv](https://docs.astral.sh/uv/). It goes into its own isolated environment and is linked as `~/.local/bin/chyk`:

    uv tool install .              # from the repo root
    uv tool install --reinstall .  # after pulling changes
    uv tool install --editable .   # or: pick up source edits without reinstalling
    uv tool uninstall zaichyk      # to remove it

Then run `chyk <file>` from any directory. You can still run `python chyk.py <file>` from the repo.

## Configuration

Set `OPENROUTER_API_KEY`, and optionally `MODEL` to use a different OpenRouter model. For an installed `chyk`, put them in the user config file:

    mkdir -p ~/.config/chyk
    cp .env.example ~/.config/chyk/.env   # then edit the key

Settings are looked up in this order, and the first one wins:
1. Environment variables.
2. A `.env` in the current directory or one of its parents.
3. `~/.config/chyk/.env` (or `$XDG_CONFIG_HOME/chyk/.env`).

## Правопис reference

`pravopys/pravopys.md` is a markdown version of the official 2026 Український правопис, generated from the PDF in `pravopys/` by:

    python tools/pravopys_to_md.py

By default it keeps only the normative body (§ 1–168), without the preface and the word index (ПОКАЖЧИК), and it removes stress marks. Use `--keep-stress`, `--with-preface` or `--with-index` to include more. Declension paradigm tables are flattened into plain rows. The file is currently not sent to the model. In tests on Jev, adding it as context made almost no difference, and it doesn't fit Jev's context window.

## UI

The TUI of the app has a viewer on the top part of the screen. It highlights the sentence we're currently working on in yellow. On the right side, there's a vertical progress bar that shows how far along we are in the text.

If a sentence has no error (a suggested rewrite is identical), the tool skips silently and moves on to the next sentence.

For each sentence that has a suggested rewrite, present 4 options to the user:
1. Apply the correction
2. Keep the original
3. Edit the corrected version
4. Edit the original

These choices are presented in a thin horizontal panel in the middle of the screen.

In the bottom is a small editor panel. The editor takes up 30% of the vertical space.

The editing is done when Enter is pressed. The tool saves the user's version of the sentence and moves on to the next.

After each review/correction session, the sentence is logged into a JSON file that for each error logs the original sentence and the corrected version accepted by the user, if it differs. It also logs the file name and time at the beginning of the file.
