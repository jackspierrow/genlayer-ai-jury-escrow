# GenLayer Builder Submission — Intelligent Contracts

**Category:** Builder → Intelligent Contracts
**Status:** READY TO SUBMIT — bos submits from his own phone (account hextor).
Do NOT deploy the contract (needs GEN); this submission is the contract +
repo only.

## Title (paste into "Title" field, optional)

AI Jury Escrow — Agent-to-Agent Escrow Settled by an AI Jury

## Description (paste into "Notes / Description", 934 / 1000 characters)

AI Jury Escrow is a reusable Intelligent Contract that gives agent-to-agent trade a court. A buyer locks GEN in escrow for a delivery; the seller claims delivery with web evidence; if they disagree, a jury of independent AI validators reads the evidence and votes, and the verdict is enforced on-chain under the Equivalence Principle (strict_eq). Either side may appeal, doubling the independent consensus rounds that must agree (1->2->4->8, max 3 appeals). The contract fixes the prompt-injection flaws in the official football_bets example: evidence is wrapped in <EVIDENCE> delimiters and treated as untrusted data, facts come from contract state, and every verdict is validated programmatically before funds move (split must sum to the escrow, full delivery forces full release). Payouts use a pull ledger. Includes full README, security analysis, and 24 passing direct-mode tests (mocked web + LLM, incl. poisoned-verdict cases).

## Evidence (paste into "URL Link" / Add Evidence)

https://github.com/jackspierrow/genlayer-ai-jury-escrow

## Contribution Date

25/11/2026

## How to submit (bos, from phone)

1. Open https://portal.genlayer.foundation (logged in as hextor).
2. Submit contribution → Contribution Type: **Builder** →
   category **Intelligent Contracts** (0 of 2 weekly slots used).
3. Contribution Date: 25/11/2026.
4. Title: `AI Jury Escrow — Agent-to-Agent Escrow Settled by an AI Jury`
5. Notes / Description: paste the description above (934 chars, under
   the 1000 limit).
6. Evidence: Add Evidence → paste the repo URL above.
7. Submit. Reward: 0–500 pts (steward review; Builder acceptance ~18.5%).

## What was verified locally (no wallet, no GEN, no deploy)

- `genvm-lint check contracts/ai_jury_escrow.py` — PASSED, 3 checks,
  0 warnings (bare `Exception` replaced with `gl.vm.UserError`).
- `pytest tests/direct/ -v` — **24 passed** in ~93s (in-memory direct
  mode, mocked web + LLM). Covers: funding validation, claim/confirm,
  dispute + jury split, 3 poisoned-verdict cases (must revert), appeal
  doubling the panel + re-deciding, appeal blocked after withdrawal,
  withdraw payouts, views.
- Repo is PUBLIC so the steward can read the source.
- `emit_transfer` / `get_contract_at` confirmed to exist in the pinned
  py-genlayer std (GenVM bundle) and `withdraw()` executes in direct mode.

## Files in this folder

- `contracts/ai_jury_escrow.py` — the Intelligent Contract
- `tests/direct/test_ai_jury_escrow.py` — 24 direct-mode tests
- `README.md` — purpose, consensus design, state design, usage
- `SECURITY.md` — prompt-injection analysis + mitigations
- `submission.md` — this file
- `requirements.txt`, `pyproject.toml`, `gltest.config.yaml`
- `frontend/README.md` — placeholder for the separate Projects-category
  frontend (same repo, NOT part of this submission)
