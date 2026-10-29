# GPT–Claude first live coding review: approved budget $0.50

Status: **NOT ENABLED**. No paid API call has been made by this change.

The approved ceiling is USD 0.50 for the entire initial GPT → Claude → GPT test, not per call.

Safety prerequisites before any paid call:

1. Set a **provider-enforced total spending cap of $0.50 or less** on the dedicated OpenRouter key `bndaiteam`, with no other processes using that key. The repository secret alone does not impose a limit.
2. Confirm OpenRouter credit availability, exact model IDs, pricing for both models and possible routing/fallback behavior. Do not assume the account is free.
3. Configure `max_tokens` and an input-token bound for each of the three requests; abort rather than truncate critical context.
4. Perform `approve_preflight` using conservative per-model input/output token bounds and current pricing. This estimate is **not** a guarantee and does not enforce runtime token or monetary limits.
5. Disable paid fallback models and automatic retries, and stop if model identity or token usage cannot be verified.
6. Run only after explicit manual approval of the actual workflow, with secret redaction and no market orders. Preserve all three responses and usage records.
7. Do not start the three-call sequence until the key cap and runtime controls are verified. This branch deliberately contains **no live workflow**.

The GitHub Actions tests use mocks and do not spend money.
