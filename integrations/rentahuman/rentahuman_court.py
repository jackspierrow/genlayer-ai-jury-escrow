"""rentahuman-court — Internet Court escrow for rentahuman.ai tasks.

An AI agent hires a human worker for a physical-world job it cannot do
itself (visit a place, take photos, verify something on site). The agent
funds an escrow; the worker delivers photo/report evidence; if they
disagree, an AI jury on GenLayer settles it.

This module is the *integration layer* between rentahuman.ai and the
AI Jury Escrow Intelligent Contract
(contracts/ai_jury_escrow.py in this repo). It does NOT talk to a chain:
it builds and validates every call the contract needs, so a bad brief
fails here — in plain Python, with a clear error — instead of reverting
on-chain. The same calls run live on Bradbury once the contract is
deployed (see README.md for the genlayer-js equivalent).

Partner: rentahuman.ai — the marketplace where AI agents hire humans
for physical tasks (REST API + MCP server + escrow). It is the official
partner use case #2 in the Internet Court docs
(genlayer-foundation/internetcourt, docs/USE_CASES.md): an AI research
agent hires a local worker to verify a startup office in Austin, TX.
The built-in brief below reproduces that exact scenario.

Mapping to AI Jury Escrow:
  Brief (N checklist tasks)  ->  fund(seller=worker, item=title,
                                  quantity_expected=N, deadline)
                                  with value = amount_gen GEN.
  Worker delivery            ->  claim_delivery(escrow_id,
                                  quantity_delivered=#tasks done,
                                  evidence_urls=[photo/report URLs]).
  Agreement                  ->  confirm_delivery() (full release).
  Disagreement               ->  open_dispute(reason) ->
                                  resolve_dispute() (AI jury verdict:
                                  delivered_quantity, refund, release)
                                  -> appeal() (max 3, panel 1->2->4->8)
                                  -> withdraw() (pull pattern).

The contract enforces, on-chain, that the split always sums to the
escrow, that full delivery forces full release, and that zero delivery
forces full refund — a poisoned or malformed verdict reverts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

WEI_PER_GEN = 10**18
MAX_EVIDENCE_URLS = 4
MAX_ITEM_CHARS = 64
MAX_REASON_CHARS = 200

# The contract only accepts this charset in text fields (item, reason).
_VALID_TEXT_RE = re.compile(r"^[A-Za-z0-9 _.,\-]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """One checklist item of a physical-verification brief."""

    description: str
    evidence: str  # what counts as proof for this task


@dataclass
class Brief:
    """A physical-verification job an AI agent posts for a human worker."""

    title: str  # goes into the contract as `item` (<=64 chars, plain text)
    location: str
    tasks: list[Task] = field(default_factory=list)
    deadline: str = "2026-12-05"  # YYYY-MM-DD
    amount_gen: int = 40  # whole GEN held in escrow
    worker_address: str = ""  # seller (0x + 40 hex)
    buyer_address: str = ""  # the hiring agent (0x + 40 hex)

    @property
    def task_count(self) -> int:
        return len(self.tasks)


def austin_office_brief(
    worker_address: str = "", buyer_address: str = ""
) -> Brief:
    """The official rentahuman.ai use case (Internet Court docs #2).

    An AI research agent for a VC firm hires a local worker to verify a
    startup office at 123 Main St, Austin TX: visit the address,
    photograph exterior + interior, count employees, verify signage.
    The docs escrow 40 USDC; here the escrow is 40 GEN on Bradbury
    (GEN is the testnet unit — the amount and the four tasks are the
    same, only the currency label changes).
    """
    return Brief(
        title="Verify TechStart office Austin",
        location="123 Main St, Austin TX",
        tasks=[
            Task(
                description="Visit 123 Main St Austin TX during business hours",
                evidence="Photo of building exterior",
            ),
            Task(
                description=(
                    "Photograph building exterior office entrance "
                    "workspace interior"
                ),
                evidence="Minimum 5 photographs exterior entrance interior",
            ),
            Task(
                description="Count visible employees",
                evidence="Written report with employee count",
            ),
            Task(
                description="Verify TechStart Inc signage at the location",
                evidence="Photo of company signage",
            ),
        ],
        deadline="2026-12-05",
        amount_gen=40,
        worker_address=worker_address,
        buyer_address=buyer_address,
    )


# ---------------------------------------------------------------------------
# Statement + guidelines (what the jury judges)
# ---------------------------------------------------------------------------


def statement(brief: Brief) -> str:
    """The contract statement: the claim the jury evaluates.

    Mirrors the official use case statement from the Internet Court docs.
    """
    parts = []
    for i, task in enumerate(brief.tasks, start=1):
        parts.append(f"({i}) {task.description}")
    joined = ", ".join(parts)
    return (
        f"The worker completed all {brief.task_count} verification tasks: "
        f"{joined}."
    )


def guidelines(brief: Brief) -> str:
    """The judgment rules handed to the jury.

    Mirrors the official use case guidelines from the Internet Court docs.
    """
    return (
        f"Evaluate each of the {brief.task_count} tasks independently. "
        "Completed means the deliverable evidence shows the task was "
        "performed, not that the results were favorable. "
        "Minimum 5 photographs required. Written report must include "
        "date and time, employee count, signage confirmation, "
        "workspace description."
    )


# ---------------------------------------------------------------------------
# Validation (mirrors the contract — fail here, not on-chain)
# ---------------------------------------------------------------------------


def _valid_text(text: str, max_len: int) -> bool:
    return (
        isinstance(text, str)
        and 0 < len(text) <= max_len
        and bool(_VALID_TEXT_RE.match(text))
    )


def _valid_date(date: str) -> bool:
    return isinstance(date, str) and bool(_DATE_RE.match(date))


def _valid_url(url: str) -> bool:
    return (
        isinstance(url, str)
        and 12 <= len(url) <= 200
        and url.startswith("https://")
        and not any(ch in url for ch in (" ", "\n", "\t"))
    )


def _valid_address(addr: str) -> bool:
    return isinstance(addr, str) and bool(_ADDRESS_RE.match(addr))


def validate_brief(brief: Brief) -> list[str]:
    """Return a list of problems with a brief (empty = valid).

    Checks every constraint the AI Jury Escrow contract enforces, so a
    bad brief is caught before any call is built.
    """
    problems: list[str] = []
    if not _valid_text(brief.title, MAX_ITEM_CHARS):
        problems.append(
            f"title must be 1-{MAX_ITEM_CHARS} chars of letters, digits, "
            "space, - _ . , only"
        )
    if not brief.tasks:
        problems.append("brief needs at least one task")
    if brief.amount_gen <= 0:
        problems.append("amount_gen must be greater than zero")
    if not _valid_date(brief.deadline):
        problems.append("deadline must be YYYY-MM-DD")
    if brief.worker_address and not _valid_address(brief.worker_address):
        problems.append("worker_address must be 0x + 40 hex chars")
    if brief.buyer_address and not _valid_address(brief.buyer_address):
        problems.append("buyer_address must be 0x + 40 hex chars")
    return problems


def validate_evidence_urls(urls: list[str]) -> list[str]:
    """Return problems with a delivery's evidence URLs (empty = valid)."""
    problems: list[str] = []
    if len(urls) > MAX_EVIDENCE_URLS:
        problems.append(
            f"at most {MAX_EVIDENCE_URLS} evidence URLs, got {len(urls)}"
        )
    for url in urls:
        if not _valid_url(url):
            problems.append(f"invalid evidence URL: {url}")
    return problems


def validate_dispute_reason(reason: str) -> list[str]:
    if not _valid_text(reason, MAX_REASON_CHARS):
        return [
            f"dispute reason must be 1-{MAX_REASON_CHARS} chars of letters, "
            "digits, space, - _ . , only"
        ]
    return []


# ---------------------------------------------------------------------------
# Mapping to AI Jury Escrow calls
# ---------------------------------------------------------------------------


def fund_args(brief: Brief) -> dict:
    """Exact arguments for AIJuryEscrow.fund() (+ the payable value).

    Returns {"seller", "item", "quantity_expected", "deadline",
    "value_wei"}. Raises ValueError if the brief is invalid.
    """
    problems = validate_brief(brief)
    if problems:
        raise ValueError("invalid brief: " + "; ".join(problems))
    if not brief.worker_address:
        raise ValueError("invalid brief: worker_address is required to fund")
    return {
        "seller": brief.worker_address,
        "item": brief.title,
        "quantity_expected": brief.task_count,
        "deadline": brief.deadline,
        "value_wei": brief.amount_gen * WEI_PER_GEN,
    }


def claim_args(
    escrow_id: str, completed_tasks: int, evidence_urls: list[str]
) -> dict:
    """Exact arguments for AIJuryEscrow.claim_delivery().

    completed_tasks is how many of the brief's tasks the worker says
    are done (0..N); evidence_urls are the photo/report links (max 4).
    """
    problems = validate_evidence_urls(evidence_urls)
    if problems:
        raise ValueError("invalid evidence: " + "; ".join(problems))
    if completed_tasks < 0:
        raise ValueError("completed_tasks cannot be negative")
    return {
        "escrow_id": escrow_id,
        "quantity_delivered": completed_tasks,
        "evidence_urls": json.dumps(evidence_urls),
    }


def dispute_reason_for(brief: Brief, shortcoming: str) -> str:
    """Build a contract-valid dispute reason from a shortcoming.

    The reason goes on-chain, so it must be plain text (see
    _valid_text). Example: "Photos show shared workspace not
    dedicated office".
    """
    problems = validate_dispute_reason(shortcoming)
    if problems:
        raise ValueError("invalid dispute reason: " + "; ".join(problems))
    return shortcoming


def verdict_summary(verdict: dict, brief: Brief) -> str:
    """One human-readable line explaining a jury verdict.

    verdict is the dict the contract returns: delivered_quantity,
    refund_amount, release_amount (all in GEN), reason.
    """
    delivered = verdict["delivered_quantity"]
    refund = verdict["refund_amount"]
    release = verdict["release_amount"]
    reason = verdict.get("reason", "")
    total = brief.task_count
    line = (
        f"Jury: {delivered} of {total} tasks complete — "
        f"{release} GEN released to the worker, {refund} GEN refunded "
        f"to the agent."
    )
    if reason:
        line += f" Reason: {reason}"
    return line


def fund_js_snippet(brief: Brief) -> str:
    """genlayer-js snippet for the same fund() call on live Bradbury.

    For when the contract is deployed (needs a deployed address + GEN).
    The contract address is a placeholder until deployment.
    """
    args = fund_args(brief)
    return f"""// Live call on Bradbury (chain 4221) — fill in the deployed address.
import {{ createClient, createAccount }} from "genlayer-js";
import {{ testnetBradbury }} from "genlayer-js/chains";

const CONTRACT = "0x<deployed AI Jury Escrow address>"; // TODO: deploy first
const client = createClient({{ chain: testnetBradbury, account: createAccount({{ privateKey: "0x..." }}) }});
const escrowId = await client.writeContract({{
  address: CONTRACT,
  functionName: "fund",
  args: ["{args['seller']}", "{args['item']}", {args['quantity_expected']}, "{args['deadline']}"],
  value: {args['value_wei']}n, // {brief.amount_gen} GEN
}});
console.log("escrow:", escrowId);"""


# ---------------------------------------------------------------------------
# Demo transcript (used by the video narration)
# ---------------------------------------------------------------------------


DEMO_EVIDENCE_URLS = [
    "https://example.com/photo-exterior-1",
    "https://example.com/photo-entrance-1",
    "https://example.com/photo-interior-1",
    "https://example.com/report-austin",
]


def demo_transcript(brief: Brief) -> str:
    """Step-by-step narration of the Austin scenario, for the demo video."""
    lines = [
        "AI Jury Escrow x rentahuman.ai — the Austin office check.",
        "",
        f"1. An AI agent hires a human on rentahuman.ai: {brief.title}.",
        f"   {brief.task_count} tasks, {brief.amount_gen} GEN held in escrow, "
        f"deadline {brief.deadline}.",
        "2. The worker visits the office, takes photos, counts employees,",
        "   and claims delivery with the photo and report links as evidence.",
        "3. The agent disagrees: the photos show a shared WeWork space,",
        "   not a dedicated office — so it opens a dispute.",
        "4. The AI jury reads the brief, the guidelines and the evidence.",
        "   Verdict: all 4 tasks were completed. The guidelines never",
        "   required a dedicated office — only that the tasks were done.",
        f"   {brief.amount_gen} GEN released to the worker, 0 refunded.",
        "5. Either side could appeal — each appeal doubles the jury.",
        "   The worker withdraws the 40 GEN. Case closed in minutes,",
        "   not months. Every deal has a court.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_brief(args: argparse.Namespace) -> int:
    brief = austin_office_brief()
    print(json.dumps(
        {
            "title": brief.title,
            "location": brief.location,
            "tasks": [
                {"description": t.description, "evidence": t.evidence}
                for t in brief.tasks
            ],
            "deadline": brief.deadline,
            "amount_gen": brief.amount_gen,
        },
        indent=2,
    ))
    print()
    print("STATEMENT:")
    print(statement(brief))
    print()
    print("GUIDELINES:")
    print(guidelines(brief))
    return 0


def _cmd_fund_call(args: argparse.Namespace) -> int:
    brief = austin_office_brief(
        worker_address=args.worker, buyer_address=args.buyer
    )
    print("# fund() arguments (AI Jury Escrow):")
    print(json.dumps(fund_args(brief), indent=2))
    print()
    print("# Live Bradbury equivalent (genlayer-js):")
    print(fund_js_snippet(brief))
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    brief = austin_office_brief()
    verdict = json.loads(args.verdict_json)
    print(verdict_summary(verdict, brief))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    print(demo_transcript(austin_office_brief()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rentahuman_court",
        description=(
            "Internet Court escrow for rentahuman.ai tasks, "
            "on top of the AI Jury Escrow contract."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_brief = sub.add_parser("brief", help="Show the Austin office brief")
    p_brief.set_defaults(func=_cmd_brief)

    p_fund = sub.add_parser(
        "fund-call", help="Show the exact fund() call + live JS snippet"
    )
    p_fund.add_argument("--worker", required=True, help="worker address (seller)")
    p_fund.add_argument("--buyer", default="", help="hiring agent address")
    p_fund.set_defaults(func=_cmd_fund_call)

    p_explain = sub.add_parser(
        "explain", help="Explain a jury verdict JSON in one line"
    )
    p_explain.add_argument("verdict_json", help='e.g. {"delivered_quantity": 4, "refund_amount": 0, "release_amount": 40, "reason": "..."}')
    p_explain.set_defaults(func=_cmd_explain)

    p_demo = sub.add_parser("demo", help="Print the demo transcript")
    p_demo.set_defaults(func=_cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
