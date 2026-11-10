I'd like to improve the spell checker in two directions.

First add the text of the current official Правопис to the context, so that the spell check users it as a reference.

Second, i'd like to split the process into two phases:
1) error detection, i.e. identifying if a sentence has an error.
2) correction -- suggesting the correct text of the sentence.

For the error detection i'd like to use TypeSafe's Jev with the Pravopys as a permanent context and feeding it the text sentence by sentence.

Only when the erroneous sentence is detected, we feed it to a different model on openrouter (the latest Luna by default) to obtain a corrected version.

Both models are accessed via openrouter.

Come up with a plan to update the current codebase accordingly.
