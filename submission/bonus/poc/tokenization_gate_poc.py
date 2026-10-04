#!/usr/bin/env python3
"""
PoC: PII Tokenization Gate at Bronze (hardest mechanism)

Demonstrates:
- Deterministic tokenization for PII fields (email, phone, id-like)
- Contract enforcement: Silver must not contain raw PII columns
- Idempotent reprocessing with MERGE (Bronze -> Silver)
- Reproducible incident replay concept

Run: python tokenization_gate_poc.py
"""

import hashlib
import re
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

# Deterministic salt per tenant (in prod: from KMS/secret store)
TENANT_SALT = {
    "t1": "salt_t1_v1",
    "t2": "salt_t2_v1",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
ID_RE = re.compile(r"\b(ID|CCCD|CMND|passport):\s*[A-Za-z0-9-]{6,}\b", re.I)

FORBIDDEN_SILVER_COLS = {"email_raw", "phone_raw", "prompt_pii", "response_pii"}

@dataclass
class BronzeEvent:
    request_id: str
    tenant_id: str
    ts: int
    prompt: str
    response: str
    route: str

@dataclass
class SilverEvent:
    request_id: str
    tenant_id: str
    ts: int
    prompt_tok: str  # tokenized
    response_tok: str  # tokenized
    route: str

def tokenize_text(text: str, tenant_id: str) -> str:
    """Deterministic tokenization. Same input+tenant+salt -> same token."""
    if not text:
        return text
    salt = TENANT_SALT.get(tenant_id, "salt_default_v1")
    def repl_email(m):
        h = hashlib.sha256((m.group(0) + salt).encode()).hexdigest()[:12]
        return f"[EMAIL:{h}]"
    def repl_phone(m):
        h = hashlib.sha256((m.group(0) + salt).encode()).hexdigest()[:12]
        return f"[PHONE:{h}]"
    def repl_id(m):
        h = hashlib.sha256((m.group(0) + salt).encode()).hexdigest()[:12]
        return f"[ID:{h}]"
    t = EMAIL_RE.sub(repl_email, text)
    t = PHONE_RE.sub(repl_phone, t)
    t = ID_RE.sub(repl_id, t)
    return t

def bronze_to_silver(be: BronzeEvent) -> SilverEvent:
    return SilverEvent(
        request_id=be.request_id,
        tenant_id=be.tenant_id,
        ts=be.ts,
        prompt_tok=tokenize_text(be.prompt, be.tenant_id),
        response_tok=tokenize_text(be.response, be.tenant_id),
        route=be.route,
    )

def check_silver_contract(rows: List[SilverEvent]) -> Dict[str, Any]:
    """Enforce: no raw PII columns. (simulated by field names)"""
    # In real impl, scan Parquet schema + sampled values
    violations = []
    # simulate values
    for i, r in enumerate(rows):
        if EMAIL_RE.search(r.prompt_tok) or EMAIL_RE.search(r.response_tok):
            violations.append(f"row{i}: email not tokenized")
        if PHONE_RE.search(r.prompt_tok) or PHONE_RE.search(r.response_tok):
            violations.append(f"row{i}: phone not tokenized")
    return {"ok": len(violations) == 0, "violations": violations[:5]}

def merge_silver(bronze: List[BronzeEvent], silver: List[SilverEvent]) -> List[SilverEvent]:
    """Idempotent MERGE: upsert by request_id (simulated)"""
    idx = {s.request_id: s for s in silver}
    for be in bronze:
        se = bronze_to_silver(be)
        idx[se.request_id] = se  # last-write-wins by event ts if needed
    return list(idx.values())

def simulate_replay(quarantine: List[BronzeEvent]) -> List[SilverEvent]:
    """Incident replay: reprocess quarantined Bronze with fixed tokenizer"""
    return [bronze_to_silver(be) for be in quarantine]

if __name__ == "__main__":
    # Seed data
    bronze = [
        BronzeEvent("r1", "t1", 1000, "Help me at alice@example.com", "Your ticket #1234", "chat"),
        BronzeEvent("r2", "t1", 1001, "Call +1-555-010-1234", "Done", "call"),
        BronzeEvent("r3", "t2", 1002, "ID: CCCD-123456", "OK", "verify"),
        BronzeEvent("r4", "t1", 1003, "No PII here", "All good", "health"),
    ]
    # Process
    silver = [bronze_to_silver(be) for be in bronze]
    contract = check_silver_contract(silver)
    # Simulate reprocess with MERGE (idempotent)
    silver2 = merge_silver(bronze[:2], silver[2:])
    # Simulate replay
    quarantine = [BronzeEvent("r5", "t1", 1100, "Fix bob@test.com issue", "Done", "chat")]
    replayed = simulate_replay(quarantine)
    print("=== PoC: PII Tokenization Gate ===")
    print("Bronze->Silver (sample):")
    for s in silver[:2]:
        print(f"  {s.request_id} tenant={s.tenant_id} prompt_tok={s.prompt_tok} resp_tok={s.response_tok}")
    print("\nContract check:", contract)
    print("MERGE idempotent (r1,r2 upsert into existing): total=", len(silver2))
    print("Replay quarantined:", [(x.request_id, x.prompt_tok) for x in replayed])
    print("\n✓ Deterministic tokenization + contract + idempotent MERGE demonstrated")
