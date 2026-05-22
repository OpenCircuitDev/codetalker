"""Phase 26 — human-language renderers for markup spans."""
from __future__ import annotations

import os
import re
from datetime import datetime


def describe_code_fence(language: str, line_count: int) -> str:
    if line_count <= 1:
        size = "a one-line"
    elif line_count < 10:
        size = "a short"
    elif line_count < 50:
        size = "a medium"
    else:
        size = "a long"
    lang = f"{language} " if language else ""
    return f"{size} {lang}code block of about {line_count} lines"


def describe_long_numeral(_text: str) -> str:
    return "a long number"


def describe_file_path(path: str, mode: str = "filename") -> str:
    base = os.path.basename(path.split(":", 1)[0])
    if mode == "filename":
        return base
    return f"the file {base}"


def describe_tool_output(tool: str, exit_code: int | None, line_count: int) -> str:
    state = "succeeded" if exit_code == 0 else f"exited with code {exit_code}" if exit_code else "ran"
    return f"{tool} {state} with {line_count} lines of output"


def describe_subagent(phase: str, subagent_type: str | None) -> str:
    label = subagent_type or "subagent"
    if phase == "pre":
        return f"dispatching {label}"
    return f"{label} returned"


def _num_to_words(n: int) -> str:
    """Convert integer 0–999,999 to words. Larger numbers fall back to digit-by-digit."""
    if n < 0 or n > 999999:
        return "".join(str(d) for d in str(n))  # Fall back to digits for out-of-range

    ones = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    teens = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    if n < 10:
        return ones[n]
    if n < 20:
        return teens[n - 10]
    if n < 100:
        return tens[n // 10] + ("" if n % 10 == 0 else " " + ones[n % 10])
    if n < 1000:
        result = ones[n // 100] + " hundred"
        if n % 100 == 0:
            return result
        return result + " " + _num_to_words(n % 100)
    if n < 1000000:
        result = _num_to_words(n // 1000) + " thousand"
        if n % 1000 == 0:
            return result
        return result + " " + _num_to_words(n % 1000)

    return "".join(str(d) for d in str(n))


def describe_ip_address(host: str, port: int | None = None) -> str:
    """Return generic phrase for IP address."""
    if port:
        return f"the address {host} on port {port}"
    return "the address"


def read_ip_address(host: str, port: int | None = None) -> str:
    """Convert IP address to TTS-friendly format."""
    octets = host.split(".")
    parts = [_num_to_words(int(octet)) for octet in octets]
    result = " dot ".join(parts)
    if port:
        result += f" on port {_num_to_words(port)}"
    return result


def describe_iso_timestamp() -> str:
    """Return generic phrase for timestamp."""
    return "a recent timestamp"


def read_iso_timestamp(raw: str) -> str:
    """Convert ISO timestamp to TTS-friendly format."""
    try:
        # Try parsing with Z suffix
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(raw)

        # Format: "May 21st, 2026" or "May 21st, 2026 at 3:08 PM"
        day = dt.day
        suffix = "st" if day in (1, 21, 31) else "nd" if day in (2, 22) else "rd" if day in (3, 23) else "th"
        month_name = dt.strftime("%B")
        year = dt.year
        date_str = f"{month_name} {day}{suffix}, {year}"

        # If there's a time component, add it
        if dt.hour != 0 or dt.minute != 0:
            hour_12 = dt.hour % 12 if dt.hour % 12 != 0 else 12
            ampm = "AM" if dt.hour < 12 else "PM"
            time_str = f"{hour_12}:{dt.minute:02d} {ampm}"
            return f"{date_str} at {time_str}"
        return date_str
    except (ValueError, AttributeError):
        # Fall back to spacing out digits on parse failure
        return re.sub(r"(\d)", r"\1 ", raw).strip()


def describe_currency_amount() -> str:
    """Return generic phrase for currency."""
    return "a dollar amount"


def read_currency_amount(raw: str) -> str:
    """Convert currency to TTS-friendly format."""
    # Remove leading $
    text = raw.lstrip("$").strip()

    # Extract the numeric part and suffix (mo/month/yr/year/etc)
    match = re.match(r"([\d,]+(?:\.\d+)?)\s*(?:USD|usd)?\s*(/(.+))?", text)
    if not match:
        return raw  # Fallback

    amount_str = match.group(1).replace(",", "")
    suffix = match.group(3) if match.group(3) else ""

    try:
        # Parse as float to handle decimals
        amount = float(amount_str)
        # Convert whole dollars and cents separately
        if amount == int(amount):
            words = _num_to_words(int(amount)) + " dollars"
        else:
            whole = int(amount)
            cents = round((amount - whole) * 100)
            if whole > 0:
                words = _num_to_words(whole) + " dollars and " + _num_to_words(cents) + " cents"
            else:
                words = _num_to_words(cents) + " cents"
    except (ValueError, OverflowError):
        words = amount_str  # Fallback to raw number

    # Add duration suffix if present
    if suffix:
        suffix_map = {
            "mo": "month", "month": "month",
            "yr": "year", "year": "year",
            "week": "week", "wk": "week",
            "day": "day",
            "hr": "hour", "hour": "hour",
        }
        suffix_text = suffix_map.get(suffix.lower(), suffix)
        words += f" per {suffix_text}"

    return words
