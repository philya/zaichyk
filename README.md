
A tool for spellchecking and proofreading markdown text.

chyk.py <file>

It splits the text into sentences and then checks them with an LLM via an API call. The prompt is something like this: "Rewrite this sentence with perfect grammar and syntax and consistent use of punctuation characters. Don't edit word choice or order, only correct grammatical mistakes."

The TUI of the app has a viewer on the top part of the screen. It highlights the sentence we're currently working on in yellow. On the right side, there's a vertical progress bar that shows how far along we are in the text.

If a sentence has no error (a suggested rewrite is identical) --- skip silently and move on to the next sentence.

For each sentence that has a suggested rewrite, present 4 options to the user:
1. Apply the correction
2. Keep the original
3. Edit the corrected version
4. Edit the original

These choices are presented in a thin horizontal panel in the middle of the screen.

In the bottom is a small editor panel. The editor takes up 30% of the vertical space.

The editing is done when Enter is pressed. The tool saves the user's version of the sentence and moves on to the next.

After each review/correction session, the sentence is logged into a JSON file that for each error logs the original sentence and the corrected version accepted by the user, if it differs. It also logs the file name and time at the beginning of the file.
