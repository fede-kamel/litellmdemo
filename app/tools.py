"""The agent's tools: Northwind Cloud's (fictional) policies, accounts and arithmetic."""

from __future__ import annotations

import ast
import operator

from langchain_core.tools import tool

POLICIES = {
    "password": "Console passwords are reset from the sign-in page: choose 'Forgot password', confirm the email "
                "link within 15 minutes, then set a new password of at least 14 characters.",
    "refund": "Duplicate charges are refunded in full to the original payment method within 5 business days of "
              "confirmation. Support confirms the duplicate, opens a billing case, and emails the case number.",
    "sla": "Availability target 99.9% per calendar month (43.8 minutes of allowed downtime in a 30.4-day month). "
           "Credit: 10% of the monthly fee if availability is below 99.9%, 25% below 99.0%, 50% below 95.0%. "
           "Credits are requested within 30 days and are the sole remedy for unavailability.",
    "priority": "Ticket priority: P1 production down, response 15 minutes; P2 degraded, 1 hour; P3 question, "
                "1 business day. Enterprise accounts may escalate P2 to P1 once per month.",
    "billing": "Usage is billed per second for compute and per GB-month for storage. A monthly spend limit can be "
               "set per compartment; at 100% new resources are blocked and an email alert is sent.",
}
ACCOUNTS = {
    "NW-4471": {"name": "Tailspin Toys", "plan": "Standard", "monthly_fee": 1200.0},
    "NW-0093": {"name": "Contoso Health", "plan": "Enterprise", "monthly_fee": 48000.0},
}

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("only numbers and + - * / ** are allowed")


@tool
def lookup_policy(topic: str) -> str:
    """Look up a Northwind Cloud policy. topic: password, refund, sla, priority or billing."""
    key = next((k for k in POLICIES if k in topic.lower()), None)
    return POLICIES[key] if key else f"No policy for {topic!r}. Topics: {', '.join(POLICIES)}."


@tool
def get_account(account_id: str) -> str:
    """Look up a customer account by id, e.g. NW-4471: name, plan, monthly fee in USD."""
    a = ACCOUNTS.get(account_id.strip().upper())
    return str(a) if a else f"No account {account_id!r}."


@tool
def calculate(expression: str) -> str:
    """Evaluate arithmetic with + - * / ** and parentheses, e.g. '48000 * 0.25'. Several expressions separated by
    ';' are evaluated in one call, one result per line: '1.2e6 * 1.12; 1.2e6 * 1.12 * 1.09'."""
    out = []
    for part in [p.strip() for p in expression.split(";") if p.strip()]:
        try:
            out.append(str(round(_eval(ast.parse(part, mode="eval").body), 6)))
        except (ValueError, SyntaxError, ZeroDivisionError) as exc:
            out.append(f"Cannot evaluate {part!r}: {exc}")
    return "\n".join(out) if len(out) > 1 else (out[0] if out else "Cannot evaluate: empty expression")


TOOLS = [lookup_policy, get_account, calculate]
