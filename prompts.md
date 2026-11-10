# Prompts

## 2026-11-10 20:43 EET — Claude Code, Claude Opus 5.5

> The key is in .env. Run the probe

> Now test luna on the same sentences, without pravopys as the context

> yes, switch back to the original one model design with Luna

## 2026-11-10 20:35 EET — Claude Code, Claude Opus 5.5

> Read Jev documentation. Is there a way to set up a context and then get it to answer multiple question sharing that context?

## 2026-11-10 20:23 EET — Claude Code, Claude Opus 5.5

> I'd like to improve the spell checker in two directions.
>
> First add the text of the current official Правопис to the context, so that the spell check users it as a reference.
>
> Second, i'd like to split the process into two phases:
> 1) error detection, i.e. identifying if a sentence has an error.
> 2) correction -- suggesting the correct text of the sentence.
>
> For the error detection i'd like to use TypeSafe's Jev with the Pravopys as a permanent context and feeding it the text sentence by sentence.
>
> Only when the erroneous sentence is detected, we feed it to a different model on openrouter (the latest Luna by default) to obtain a corrected version.
>
> Both models are accessed via openrouter.
>
> Come up with a plan to update the current codebase accordingly.

Follow-ups during planning:

> We can use the latest jev. That's the whole point. We ask jev a question, does this sentence contain a grammatical error? If the answer is no, we skip the sentence. If yes - we feed it to the `correction` model, i.e. Luna.

> Detection. Read the docs on Jev. It answers with the probability number. You don't need to tell it to answer yes or no, it always responds with a probability of Yes.

> The pdf version of the Pravopys is already in the `pravopys` folder. You ounly need to convert it to markdown.
