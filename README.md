A tool for spellchecking and proofreading markdown text.

chyk.py <file>

It splits the text into sentences and sends each one to an LLM via [OpenRouter](https://openrouter.ai) (`~openai/gpt-luna-latest` by default). The prompt is something like this: "Rewrite this sentence with perfect spelling, grammar and syntax and consistent use of punctuation characters, following the current official Ukrainian orthography (Український правопис). Don't edit word choice or order, only correct mistakes."

## Configuration

Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. Set `MODEL` to use a different OpenRouter model.

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
