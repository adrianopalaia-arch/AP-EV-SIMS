"""Credential loading without shell execution, interpolation, logging, or serialization."""
import os
from pathlib import Path
import re
from urllib.parse import quote, quote_plus

CREDENTIAL_NAMES = ('CFBD_API_KEY', 'THE_ODDS_API_KEY')

def load_credentials(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[3] / '.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?(CFBD_API_KEY|THE_ODDS_API_KEY)\s*=\s*(.*?)\s*', line)
            if not match:
                continue
            name, value = match.groups()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            else:
                value = value.split(' #', 1)[0].strip()
            if '\x00' in value or '\r' in value or '\n' in value:
                raise ValueError('INVALID_CREDENTIAL_FORMAT')
            # An explicitly set process value, including empty, takes precedence.
            if name not in os.environ:
                os.environ[name] = value
    return {name: bool(os.environ.get(name, '').strip()) for name in CREDENTIAL_NAMES}

def redact(text):
    text = str(text)
    for name in CREDENTIAL_NAMES:
        secret = os.environ.get(name, '')
        if secret:
            for form in {secret, quote(secret, safe=''), quote_plus(secret)}:
                text = text.replace(form, '[REDACTED]')
    text = re.sub(r'(?i)((?:api[_-]?key|access_token|token|authorization)(?:%3d|=|["\x27]?\s*:\s*["\x27]?))[^&\s"\x27<>]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)Bearer\s+[^\s"\x27<>]+', 'Bearer [REDACTED]', text)
    return text

def safe_quota(headers):
    allowed = {'x-requests-remaining', 'x-requests-used', 'x-requests-last',
               'x-calllimit-remaining', 'x-calllimit-limit', 'x-ratelimit-remaining',
               'x-ratelimit-limit', 'retry-after'}
    return {str(k).lower(): int(v) for k, v in headers.items()
            if str(k).lower() in allowed and str(v).isdigit()}
