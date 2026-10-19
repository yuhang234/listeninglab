"""Word-level diff for dictation scoring."""
import re
from typing import List, Dict, Any


def tokenize(text: str, ignore_punctuation: bool = True, case_sensitive: bool = False) -> List[str]:
    if not case_sensitive:
        text = text.lower()
    text = re.sub(r"[’‘＇`]", "'", text)
    if ignore_punctuation:
        text = re.sub(r"[^\w\s'-]", " ", text)
    raw_tokens = text.strip().split()
    if ignore_punctuation:
        tokens = [t.strip("'-_") for t in raw_tokens if t.strip("'-_")]
    else:
        tokens = raw_tokens
    return tokens


def lcs(seq_a: List[str], seq_b: List[str]) -> List[tuple]:
    m, n = len(seq_a), len(seq_b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    matches = []
    i, j = m, n
    while i > 0 and j > 0:
        if seq_a[i - 1] == seq_b[j - 1]:
            matches.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    matches.reverse()
    return matches


def compute_diff(expected: str, actual: str, ignore_punctuation: bool = True, case_sensitive: bool = False) -> Dict[str, Any]:
    exp_tokens = tokenize(expected, ignore_punctuation, case_sensitive)
    act_tokens = tokenize(actual, ignore_punctuation, case_sensitive)
    matches = lcs(exp_tokens, act_tokens)

    tokens = []
    correct_count = 0
    i = j = 0
    mi = 0

    while i < len(exp_tokens) or j < len(act_tokens):
        if mi < len(matches) and matches[mi][0] == i and matches[mi][1] == j:
            tokens.append({"type": "correct", "word": exp_tokens[i]})
            correct_count += 1
            i += 1
            j += 1
            mi += 1
        elif mi < len(matches) and (i < matches[mi][0] or j < matches[mi][1]):
            if i < matches[mi][0] and j < matches[mi][1]:
                tokens.append({"type": "wrong", "expected": exp_tokens[i], "actual": act_tokens[j]})
                i += 1
                j += 1
            elif i < matches[mi][0]:
                tokens.append({"type": "missing", "word": exp_tokens[i]})
                i += 1
            else:
                tokens.append({"type": "extra", "word": act_tokens[j]})
                j += 1
        else:
            if i < len(exp_tokens) and j < len(act_tokens):
                tokens.append({"type": "wrong", "expected": exp_tokens[i], "actual": act_tokens[j]})
                i += 1
                j += 1
            elif i < len(exp_tokens):
                tokens.append({"type": "missing", "word": exp_tokens[i]})
                i += 1
            else:
                tokens.append({"type": "extra", "word": act_tokens[j]})
                j += 1

    total = len(exp_tokens) if exp_tokens else 1
    accuracy = round((correct_count / total) * 100, 1)
    return {
        "accuracy": accuracy,
        "tokens": tokens,
        "expected_count": len(exp_tokens),
        "actual_count": len(act_tokens),
        "correct_count": correct_count,
    }