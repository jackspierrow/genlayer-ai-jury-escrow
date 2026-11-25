# rentahuman.ai × Internet Court — escrowed physical verification

An AI agent hires a human on [rentahuman.ai](https://rentahuman.ai)
(a marketplace where agents hire people for physical tasks via a REST
API + MCP server + escrow) and the deal is settled by the
**AI Jury Escrow** Intelligent Contract on GenLayer. If the two sides
disagree about the work, an AI jury reads the evidence and decides —
minutes, not months.

This is the integration for GenLayer Mission 101, "Internet Court:
Partner Demo Lab". It implements the official rentahuman.ai use case
from the Internet Court docs
([genlayer-foundation/internetcourt](https://github.com/genlayer-foundation/internetcourt),
`docs/USE_CASES.md` #2): an AI research agent hires a local worker to
verify a startup office in Austin, TX.

## The use case (Austin office check)

An AI agent for a VC firm needs physical due diligence: visit a
startup office, verify it has real employees, photograph the
workspace. It posts the job on rentahuman.ai and hires a local worker
through Internet Court escrow.

| | |
|---|---|
| Brief | Verify TechStart office, 123 Main St, Austin TX |
| Tasks (4) | Visit the address · photograph exterior + entrance + interior · count employees · verify signage |
| Escrow | 40 GEN (the docs use 40 USDC; GEN is the Bradbury testnet unit) |
| Deadline | 2026-12-05 |
| Dispute | Photos show a shared WeWork space, not a dedicated office |
| Verdict | **TRUE — all 4 tasks completed.** The guidelines never required a dedicated office, only that the tasks were performed. 40 GEN to the worker, 0 refunded. |

The verdict is the interesting part: the jury judges the *brief*,
not the agent's disappointment. The agent learns to write better
statements next time — that is the feature.

## How it maps to AI Jury Escrow

```
Brief (N checklist tasks)
  -> fund(seller=worker, item=title, quantity_expected=N, deadline)
     value = amount_gen GEN
Worker delivery
  -> claim_delivery(escrow_id, quantity_delivered=#tasks done,
                    evidence_urls=[photo/report URLs, max 4])
Agreement
  -> confirm_delivery()            # full release, no jury needed
Disagreement
  -> open_dispute(reason)
  -> resolve_dispute()             # AI jury: delivered_quantity,
                                   # refund_amount, release_amount
  -> appeal()                      # max 3, panel 1 -> 2 -> 4 -> 8
  -> withdraw()                    # pull pattern
```

`rentahuman_court.py` builds and validates every call before it is
made, using the exact constraints the contract enforces (text charset,
`YYYY-MM-DD` deadline, `https://` evidence URLs, max 4 URLs, whole
GEN). A bad brief fails here — in plain Python, with a clear error —
instead of reverting on-chain.

## Files

| File | What it is |
|---|---|
| `rentahuman_court.py` | Library + CLI. Pure Python, no chain dependency. |
| `simulate.py` | Runs the full Austin scenario against the real contract in direct mode and prints a transcript. |
| `tests/test_rentahuman_court.py` | 12 tests: 9 unit tests (mapping + validation) and 3 direct-mode end-to-end tests (full delivery + appeal, partial split, happy path). |
| `demo_transcript.md` | The step-by-step demo script (used by the video). |

## Run it

```bash
# From the repo root (uses the repo venv for the direct-mode parts).
# 1. Show the Austin brief, statement and guidelines:
python3 integrations/rentahuman/rentahuman_court.py brief

# 2. Show the exact fund() call + the live Bradbury (genlayer-js) version:
python3 integrations/rentahuman/rentahuman_court.py fund-call \
  --worker 0x1111111111111111111111111111111111111111 \
  --buyer 0x2222222222222222222222222222222222222222

# 3. Explain a jury verdict in one line:
python3 integrations/rentahuman/rentahuman_court.py explain \
  '{"delivered_quantity": 4, "refund_amount": 0, "release_amount": 40, "reason": "All tasks complete"}'

# 4. Run the whole scenario against the real contract (direct mode):
./venv/bin/python integrations/rentahuman/simulate.py

# 5. Run the tests (12 tests, plus the 24 contract tests):
./venv/bin/python -m pytest integrations/rentahuman/tests/ tests/direct/ -q
```

## Live on Bradbury (when the contract is deployed)

The same calls run on Bradbury (chain 4221) once the AI Jury Escrow
contract is deployed — `fund-call` prints the `genlayer-js` snippet.
The contract is not deployed yet (it needs GEN for the fee budget),
so the live path is documented, not executed. The demo website
(https://muse.ai/s/ai-jury-escrow-xvm6xoxwx0xbaxuub/ga1bclKxbcxIkBQ8hQxSdlD0_hmBeRCRyqkKiikjcFs)
shows the same flow in a browser, with a live Bradbury status panel
and a labelled demo mode for the escrow actions.

## Honest notes

- **Direct mode mocks the LLM and the web.** The tests and
  `simulate.py` prove the integration logic, the contract's consensus
  and validation, and the money flow — but the jury's *judgment* in
  those runs is a scripted mock verdict, not a live LLM. On Bradbury,
  the real validator jury makes the call. The mock verdicts used here
  are the official outcomes from the Internet Court docs.
- **Demo evidence URLs are placeholders.** The Austin scenario uses
  `example.com` photo/report URLs in direct mode. A real run uses the
  worker's actual photo and report links.
- **rentahuman.ai is a docs use-case partner, not a founding
  consortium member.** It is featured as use case #2 in the official
  Internet Court docs and named in their launch strategy, but it does
  not appear in the founding-members list (which includes GenLayer,
  MetaMask, OKX, NEAR, ZKsync, UMA, Kleros, Collective Memory and
  others). The integration implements the documented flow faithfully;
  if the stewards prefer a founding member, the same code works for
  Collective Memory commissions with only the brief changed.
- **No wallet, no GEN, no transaction** is needed to run anything
  here. Nothing in this folder touches a wallet or a chain.
