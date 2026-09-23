# X Blogger Follow Post

Codex skill for monitoring an X blogger through RSS, verifying the exact X post, filtering low-relevance items, and preparing objective Vietnamese IFXData Vietnam Newsfeed drafts.

The current workflow defaults to `chat_preview`: it discovers through RSS, records decisions locally, and shows the original post, training rewrite, edit notes, labels, and processed media in the conversation. It does not publish until the operator explicitly switches to the Vietnam publishing workflow.

The skill is configured for the `@fxtrader` RSS feed in `references/sources.json`. See `SKILL.md` for the complete workflow and safety rules.
