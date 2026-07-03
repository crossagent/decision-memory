import re
from typing import Any

# Regular expressions for common API keys and credential formats
API_KEY_PATTERNS = [
    # Google AI Studio / Gemini API Key
    re.compile(r"AIzaSy[A-Za-z0-9_\-]{33}"),
    # OpenAI API Key
    re.compile(r"sk-[A-Za-z0-9]{32,80}"),
    # General Bearer token / high entropy secret patterns
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.\~+\/]+=*", re.IGNORECASE),
    # Password variables
    re.compile(r"(password|passwd|secret|api_key|token|private_key)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE)
]

def scan_text_for_secrets(text: str) -> list[str]:
    """Scans a block of text for API keys, bearer tokens, or password variables.
    
    Returns:
        A list of matching strings found.
    """
    matches = []
    for pattern in API_KEY_PATTERNS:
        for match in pattern.findall(text):
            # If the match is a tuple (e.g. from capturing groups), grab the full match
            if isinstance(match, tuple):
                matches.append(match[0])
            else:
                matches.append(match)
    return matches


def mask_account_id(account: str) -> str:
    """Masks a brokerage/bank account ID (e.g. DU123456 -> D***456) to prevent exposure.
    
    Args:
        account: The raw account ID string.
        
    Returns:
        The masked account ID.
    """
    cleaned = account.strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "****"
    return f"{cleaned[:1]}***{cleaned[-3:]}"


def redact_secrets_and_accounts(data: Any, managed_accounts: list[str]) -> Any:
    """Recursively traverses a Python data structure to redact known secrets and mask account IDs.
    
    Args:
        data: The input string, list, dict, or primitive type.
        managed_accounts: List of raw account numbers to redact.
        
    Returns:
        The sanitized data structure.
    """
    if isinstance(data, dict):
        return {key: redact_secrets_and_accounts(val, managed_accounts) for key, val in data.items()}
    if isinstance(data, list):
        return [redact_secrets_and_accounts(item, managed_accounts) for item in data]
    if isinstance(data, str):
        # 1. Redact secrets
        sanitized = data
        secrets = scan_text_for_secrets(sanitized)
        for secret in secrets:
            sanitized = sanitized.replace(secret, "[REDACTED SECRET]")
        
        # 2. Redact accounts
        for account in managed_accounts:
            if account:
                sanitized = sanitized.replace(account, mask_account_id(account))
        return sanitized
    return data


def validate_safe_write(file_path: str, content: str) -> None:
    """Performs safety policy checks before any file is written to the workspace.
    
    Raises:
        ValueError: If a safety violation (e.g. secret leakage) is detected.
    """
    # 1. Check for API keys or passwords in the content
    secrets = scan_text_for_secrets(content)
    if secrets:
        raise ValueError(
            f"Security Policy Violation: Found credentials/secrets in write request to {file_path}! "
            f"Matches: {', '.join([s[:10] + '...' for s in secrets])}"
        )

    # 2. Prevent writing executable scripts or code to memory folders
    if any(file_path.endswith(ext) for ext in [".py", ".sh", ".ps1", ".bat", ".exe"]):
        raise ValueError(
            f"Security Policy Violation: Attempted to write executable code to memory vault path: {file_path}"
        )
