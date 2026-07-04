from __future__ import annotations

import re

API_KEY_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"glpat-[a-zA-Z0-9\-]{20,}"),
]

PASSWORD_PATTERNS = [
    re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?(\S{6,})['\"]?", re.IGNORECASE),
    re.compile(r"(?:secret|token|api_key|apikey)\s*[:=]\s*['\"]?(\S{6,})['\"]?", re.IGNORECASE),
]

PII_PATTERNS = [
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
]

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|all)\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(your|all|previous)\s+(instructions?|rules?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:(?:a|an)\s+)?(?:DAN|evil|unrestricted)", re.IGNORECASE),
    re.compile(r"^system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
]

HARMFUL_PATTERNS = [
    re.compile(r"(?:how\s+to|ways\s+to|methods?\s+for)\s+(?:hack|exploit|attack)", re.IGNORECASE),
    re.compile(r"(?:create|make|build)\s+(?:a\s+)?(?:virus|malware|ransomware|trojan)", re.IGNORECASE),
    re.compile(r"(?:bypass|circumvent|evade)\s+(?:security|authentication|firewall)", re.IGNORECASE),
]