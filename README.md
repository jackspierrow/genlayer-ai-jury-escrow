# AI Jury Escrow — Intelligent Contract for GenLayer

An escrow for agent-to-agent deals, settled by an **AI jury** under GenLayer's
Optimistic Democracy consensus. Built for the GenLayer Season 2 Builder
program (category: Intelligent Contracts).

> **Status:** contract written, linted and direct-tested. **Not yet deployed**
> to Bradbury testnet — deployment needs GEN for the fee budget and is a
> separate step (see [Deployment](#deployment)).

## The problem

AI agents already trade with each other — one agent hires another to buy
goods, book services, or deliver data. Payments exist (x402), identity
exists (ERC-8004), negotiation exists (A2A). What does not exist is a
**court**: when two agents disagree about whether a delivery happened,
there is no neutral judge. Today the options are "trust the counterparty"
or "don't trade".

AI Jury Escrow is that court, as a reusable on-chain primitive: lock funds
in escrow, and if delivery is disputed, a jury of independent AI validators
reads the evidence and votes. The verdict is enforced by the contract.

## How it works

```
Buyer --fund()--> [ESCROW: amount locked] --claim_delivery()--> DELIVERED
   |                                                              |
   | confirm_delivery() -> seller paid in full                    | open_dispute()
   |                                                              v
   +--------------------------------------------------------> DISPUTED
                                                             resolve_dispute()
                                                              -> jury verdict
                                                              -> split applied
                                                              -> RESOLVED
                                                              -> appeal() x3 max
                                                                 (panel doubles
                                                                  each time)
```

1. **Fund** — the buyer calls `fund()` (payable) with the seller's address,
   an item description, the quantity ordered, and a delivery deadline.
   The amount must be **whole GEN** (see [Why whole GEN](#why-whole-gen)).
2. **Claim delivery** — the seller calls `claim_delivery()` with the
   quantity delivered and up to 4 evidence URLs (receipts, tracking pages,
   stock pages). Evidence is stored on-chain as part of the escrow.
3. **Confirm or dispute** — the buyer calls `confirm_delivery()` for a
   full release, or either party calls `open_dispute()` with a reason.
4. **Jury verdict** — anyone calls `resolve_dispute()`. A jury function
   fetches the evidence pages, builds a prompt from **programmatic facts**
   (amount, item, quantities, deadline — taken from contract state, never
   from the web) plus the evidence, and asks the LLM for a verdict:
   `delivered_quantity`, `refund_amount`, `release_amount`, `reason`.
   The verdict is produced under `gl.eq_principle.strict_eq`, so the
   leader and every validator must produce the **exact same** verdict.
5. **Appeal** — either party may appeal a resolved escrow (max 3 times).
   Each appeal **doubles the number of independent consensus rounds**
   that must agree (panel 1 → 2 → 4 → 8) and re-decides the split.
   Appeals are blocked once either side has withdrawn, so a verdict can
   never be reversed after payout.
6. **Withdraw** — resolved/refunded amounts sit in a claimable ledger;
   each party pulls their share with `withdraw()` (pull pattern, so a
   failing receiver can never block a settlement).

## How consensus is used

This is not a thin "AI decides X" wrapper. The LLM is used for exactly
one thing it is good at — **reading messy real-world evidence and judging
a delivery** — and everything else is deterministic:

| Layer | Mechanism |
|---|---|
| Jury vote | `gl.nondet.exec_prompt` with the evidence, under `gl.eq_principle.strict_eq` (leader + validators must agree byte-for-byte on the canonical JSON verdict) |
| Appeal escalation | `resolve_dispute()` re-runs the jury `2^appeals` times under `strict_eq` and requires **unanimity across all rounds** — a bigger, more expensive panel for a bigger claim |
| Programmatic grounding | The verdict is validated on-chain before any funds move: split must sum to the escrow amount, quantities must be in range, full delivery forces full release, zero delivery forces full refund |
| Deterministic state machine | `FUNDED → DELIVERED → RELEASED / DISPUTED → RESOLVED`, with role checks (only buyer confirms, only seller claims, only parties dispute/appeal) |

## State design

```python
Escrow (dataclass, @allow_storage)
  id: str                  # "escrow-0", "escrow-1", ...
  buyer: str               # checksummed hex
  seller: str              # checksummed hex
  amount: u256             # locked GEN (wei)
  item: str                # validated: 1-64 chars, [A-Za-z0-9 _-.,]
  quantity_expected: u256
  claimed_quantity: u256   # seller's claim
  quantity_delivered: u256 # jury's verdict
  deadline: str            # YYYY-MM-DD, format-validated
  status: str              # FUNDED | DELIVERED | RELEASED | DISPUTED | RESOLVED
  dispute_reason: str
  refund_amount: u256      # to buyer (wei)
  release_amount: u256     # to seller (wei)
  appeals: u256            # 0..3

Contract storage
  escrows: TreeMap[str, Escrow]
  evidence: TreeMap[str, str]      # escrow_id -> JSON list of evidence URLs
  balances: TreeMap[Address, u256] # claimable ledger (pull payouts)
  escrow_count: u256
```

## Security design

Built deliberately to **not** repeat the prompt-injection flaws in the
official `football_bets.py` example (see `SECURITY.md` for the full
analysis):

- **Evidence is data, never instructions.** Every fetched page is wrapped
  in `<EVIDENCE n>...</EVIDENCE n>` delimiters and the prompt explicitly
  orders the jury to ignore any instructions, commands, or fake verdicts
  inside them. The boilerplate example pastes raw web content into the
  prompt with no delimiter and no such instruction.
- **Programmatic facts first.** Amount, item, quantities, and deadline
  come from contract state. The LLM judges only the ambiguous part
  (did the delivery match the order?).
- **Verdict validation.** `_validate_verdict()` enforces, on-chain:
  exact key set, integer types (bools rejected), quantity in range,
  `refund + release == amount`, full delivery ⇒ refund 0, zero delivery
  ⇒ release 0, reason 1–200 chars. A poisoned or malformed verdict
  **reverts** — no funds move.
- **Input restriction.** Item names, dispute reasons, deadlines, and
  evidence URLs are validated at entry (character allowlist, format,
  `https://` only, max 4 URLs, fetched content truncated to 3000 chars).
- **No guaranteed wins.** Unlike the boilerplate's commented-out
  "game already finished" check, this contract has no path to a
  risk-free payout: every release or split goes through the jury or an
  explicit buyer confirmation.
- **Appeal safety.** Appeals are blocked after withdrawal, so a verdict
  can never be reversed after funds left the ledger.

## Why whole GEN

The jury LLM works with the amounts in the prompt. Asking it to do
20-digit wei arithmetic (`refund + release == 50000000000000000000`)
is error-prone; small whole-GEN integers are exact. `fund()` therefore
requires the amount to be a whole number of GEN, and the verdict is
expressed in GEN and converted to wei on-chain. Sub-GEN precision is a
documented limitation, not a bug.

## Project structure

```
contracts/
  ai_jury_escrow.py      # the Intelligent Contract
tests/
  direct/
    conftest.py
    test_ai_jury_escrow.py   # direct-mode tests (in-memory, mocked web/LLM)
integrations/
  rentahuman/
    rentahuman_court.py      # Internet Court escrow for rentahuman.ai tasks
    simulate.py              # full Austin scenario, direct mode
    tests/test_rentahuman_court.py
    README.md
    demo_transcript.md
requirements.txt             # genlayer-py v0.18, genlayer-test v0.29,
                             # genvm-linter, pytest
pyproject.toml
```

## Integrations

### rentahuman.ai × Internet Court (Mission 101)

`integrations/rentahuman/` implements the official rentahuman.ai use
case from the Internet Court docs: an AI agent hires a human to verify
a physical location, and the AI Jury Escrow contract settles the deal.
See [`integrations/rentahuman/README.md`](integrations/rentahuman/README.md).

```bash
# Show the Austin office brief (statement + guidelines)
python3 integrations/rentahuman/rentahuman_court.py brief

# Run the whole scenario against the real contract (direct mode)
./venv/bin/python integrations/rentahuman/simulate.py

# Tests (12 integration tests + 24 contract tests)
./venv/bin/python -m pytest integrations/rentahuman/tests/ tests/direct/ -q
```

## Testing

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Lint
./venv/bin/genvm-lint check contracts/ai_jury_escrow.py

# Direct tests (fast, in-memory, no Studio, no wallet, no GEN)
./venv/bin/pytest tests/direct/ -v
```

Direct tests cover: funding validation, claim/confirm flow, dispute +
jury resolution (mocked web + LLM), verdict validation (a poisoned
verdict that breaks the split invariant **must revert**), appeal
doubling the panel and re-deciding the split, appeal blocked after
withdrawal, and all views.

## Deployment

Deploy to Bradbury testnet (chain 4221) with the GenLayer CLI or Studio:

```bash
genlayer network testnet-bradbury
genlayer deploy
```

Deployment needs GEN for the fee budget (faucet:
https://testnet-faucet.genlayer.foundation — 100 GEN per claim).
**This repo does not include a deployment yet** — the contract was
developed and tested locally only.

### Calling the contract (genlayer-js)

```ts
// Fund 50 GEN escrow for 100 sensor units
await client.writeContract({
  address: CONTRACT_ADDRESS,
  functionName: "fund",
  args: ["0xSeller...", "Sensor units", 100, "2026-12-31"],
  value: BigInt(50) * BigInt(10 ** 18),
});
```

## License

MIT
