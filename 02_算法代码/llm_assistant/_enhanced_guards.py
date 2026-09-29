# -*- coding: utf-8 -*-
# [v18.7.16.4] Enhanced guards for postprocess.py
import re

def _strip_markdown_fences(text):
    text = re.sub(r'```[a-z]*[\s\S]*?```', '', text)
    text = re.sub(r'~~~[a-z]*[\s\S]*?~~~', '', text)
    return text

def _detect_ctx_injection(text):
    keywords = ['ignore previous', 'disregard', 'forget the system', 'reveal your',
        'show your prompt', 'what are your', 'act as', 'pretend to be',
        'developer mode', 'jailbreak', 'dan mode', 'roleplay', 'system override']
    text_lower = text.lower()
    hits = [kw for kw in keywords if kw.lower() in text_lower]
    return len(hits) >= 2, hits

def _redact_pii(text):
    hits = []
    text, n = re.subn(r'(?:\+?86)?[1][3-9]\d{9}', '[REDACTED]', text)
    if n: hits.extend(['phone'] * n)
    text, n = re.subn(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED]', text)
    if n: hits.extend(['email'] * n)
    return text, hits

def _check_domain_vocab(text):
    non_vocab = ['transformer', 'bus', 'line', 'breaker', 'load', 'generator', 'voltage', 'current']
    text_lower = text.lower()
    hits = [w for w in non_vocab if w in text_lower]
    return len(hits) == 0, hits

def _wrap_md_fences(text):
    text = re.sub(r'```', '', text)
    text = re.sub(r'~~~', '', text)
    return text
