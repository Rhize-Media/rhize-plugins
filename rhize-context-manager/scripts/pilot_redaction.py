"""Deterministic, bounded private-input redaction shared by capture and annotation."""
import bisect
import math
import re
import unicodedata
from collections import Counter

MAX_MESSAGE_CHARS = 200_000
ZERO_WIDTH = frozenset('\u200b\u200c\u200d\ufeff\u2060')
PROMPT_LIMIT = 6500

# Detection runs on a normalized view of the text (see detection_view); every quantifier is bounded except the
# `[ \t]*` in CREDENTIAL_TAIL and NAME_END, which are only ever used anchored (`.match(text, pos)`), so a long run of
# look-alike characters cannot make any pattern run away; a test times every module-level regex on adversarial input.
# Entry: (pattern, marker, prefix group to keep or 0).
def _u(*points):
    return {p: t for p, t in points}


HOMOGLYPHS = str.maketrans(_u(
    (0x0430, 'a'), (0x0435, 'e'), (0x043E, 'o'), (0x0440, 'p'), (0x0441, 'c'), (0x0445, 'x'), (0x0443, 'y'),
    (0x0456, 'i'), (0x0458, 'j'), (0x0455, 's'), (0x0501, 'd'), (0x04BB, 'h'), (0x051B, 'q'), (0x0475, 'v'),
    (0x0410, 'A'), (0x0412, 'B'), (0x0415, 'E'), (0x041A, 'K'), (0x041C, 'M'), (0x041D, 'H'), (0x041E, 'O'),
    (0x0420, 'P'), (0x0421, 'C'), (0x0422, 'T'), (0x0425, 'X'), (0x0405, 'S'), (0x0406, 'I'), (0x0408, 'J'),
    (0x03BF, 'o'), (0x03B1, 'a'), (0x03BD, 'v'), (0x03C1, 'p'), (0x03C4, 't'), (0x03B9, 'i'), (0x03BA, 'k'),
    (0x03C5, 'u'), (0x0391, 'A'), (0x0392, 'B'), (0x0395, 'E'), (0x0396, 'Z'), (0x0397, 'H'), (0x0399, 'I'),
    (0x039A, 'K'), (0x039C, 'M'), (0x039D, 'N'), (0x039F, 'O'), (0x03A1, 'P'), (0x03A4, 'T'), (0x03A5, 'Y'),
    (0x03A7, 'X'), (0x0131, 'i')))
ESCAPE = re.compile(r'\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2}))')
MAX_ESCAPES = 20000
_STR = r"(?:'[^'\n]{0,200}'|\"[^\"\n]{0,200}\"|[^\s'\"]{1,200})"
# A package-manager flag with its optional value: `-g`, `--global=true`, `--location=user`, `--location user`, `-L user`.
_FLAG = r'--?[\w-]+(?:=\S{1,100}|\s{1,4}(?!-)[^\s/@]{1,30}(?=\s))?'
# Known token prefixes. `\b` does not fire after `_`, so `credentials_AKIA...json` is found by SNAKE_TOKEN below, which
# keeps only matches with a digit or a capital (an ordinary snake_case name such as `run_npm_install_with_legacy_flags`
# has neither).
_TOKEN_PREFIXES = (r'(?:sk-ant-[\w-]{1,512}|sk-[\w-]{20,512}|sntrys_[\w-]{1,512}|gh[pousr]_\w{1,512}|'
                   r'github_pat_\w{20,512}|xox[a-z]-[\w%+./=-]{6,512}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[\w-]{30,60}|'
                   r'npm_\w{30,100}|vc[a-z]_\w{20,512}|vercel_\w{16,512}|sb_(?:secret|publishable)_[\w-]{8,512}|'
                   r'sbp_\w{16,512}|re_\w{20,512}|sk[A-Za-z0-9]{40,300}|shpat_\w{20,512}|glpat-[\w-]{20,512}|'
                   r'dop_v1_\w{20,512}|whsec_\w{16,512}|hf_[A-Za-z0-9]{20,300}|ntn_[A-Za-z0-9]{20,300}|'
                   r'(?:pk|sk|rk)_(?:live|test)_\w{1,512})')
SNAKE_TOKEN = re.compile(r'(?i)(?<=_)' + _TOKEN_PREFIXES + r'(?![A-Za-z0-9])')
REDACTIONS = (
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)', re.S), '[REDACTED_PRIVATE_KEY]', 0),
    (re.compile(r'(?i)\bhttps?://hooks\.slack\.com/services/[\w/-]{1,200}|'
                r'\bhttps?://(?:discord(?:app)?\.com)/api/webhooks/\d{1,30}/[\w-]{1,200}'), '[REDACTED_WEBHOOK]', 0),
    (re.compile(r'(?i)(\bhttps?://[^\s/]{1,100}/(?:[^\s/]{1,60}/){0,4}?(?:webhooks?|hooks?)/)[^\s"\'<>]{8,300}'),
     '[REDACTED_WEBHOOK]', 1),
    (re.compile(r'(?i)\b' + _TOKEN_PREFIXES + r'(?![A-Za-z0-9])'), '[REDACTED_TOKEN]', 0),
    (re.compile(r'(?<![A-Za-z0-9])eyJ[\w-]{8,2048}\.[\w-]{8,2048}\.[\w-]{8,2048}\b'), '[REDACTED_TOKEN]', 0),
    (re.compile(r'(?<![0-9A-Za-z])[0-9A-Fa-f]{64,}(?![0-9A-Za-z])'), '[REDACTED_TOKEN]', 0),
    (re.compile(r'(?i)\b(bearer\s{1,8})[\w.~+/=-]{16,512}'), '[REDACTED_TOKEN]', 1),
    (re.compile(r'\b((?i:basic)\s{1,8})(?=[A-Za-z0-9+/]{0,200}[0-9A-Z+/=])[A-Za-z0-9+/]{8,200}={0,2}'), '[REDACTED_TOKEN]', 1),
    (re.compile(r'(?i)(\b[a-z][a-z0-9+.-]{0,30}://)[^\s/@:]{1,256}:[^\s/]{1,256}@'), '[REDACTED_CREDENTIALS]@', 1),
    (re.compile(r'(?i)(\bsshpass\s{1,8}-p\s{0,8})' + _STR), '[REDACTED_PASSWORD]', 1),
    (re.compile(r"(?<!\S)(--?u(?:ser)?(?:\s{1,4}|=))(?:'[^'\n]{0,200}:[^'\n]{0,200}'|\"[^\"\n]{0,200}:[^\"\n]{0,200}\"|"
                r"(?=[^\s'\"]{0,200}:)[^\s'\"]{1,200})"), '[REDACTED_CREDENTIALS]', 1),
    (re.compile(r"(?i)(\b(?:mysql|mysqldump|mysqladmin|mariadb|mongo|mongosh|redis-cli)\b[^\n]{0,200}?\s-p)" + _STR),
     '[REDACTED_PASSWORD]', 1),
    (re.compile(r"(?i)(--?(?:password|passwd|pass|pwd|token|api-?key|apikey|secret|auth-?token|access-?token|client-?secret|otp)"
                r"(?:=|\s{1,8}))" + _STR), '[REDACTED_SECRET]', 1),
    (re.compile(r'(?i)(\b(?:npm|yarn|pnpm|bun)\b(?:\s{1,4}--?[\w-]+(?:[= ]\S{1,100})?){0,4}?\s{1,4}'
                r'(?:(?:config|c)(?:\s{1,4}' + _FLAG + r'){0,3}\s{1,4}set|set)\s{1,4}(?:' + _FLAG + r'\s{1,4}){0,3}'
                r'\S{0,200}(?:token|password|secret|auth|key)\S{0,100}\s{1,4})[^\s]{1,512}'), '[REDACTED_SECRET]', 1),
    (re.compile(r'(?i)([?&](?:key|sig|signature|token|access_token|api_key|apikey|secret|password|pwd|auth|code|'
                r'x-amz-signature|x-goog-signature)=)[^\s&#"\'<>]{1,512}'), '[REDACTED_SECRET]', 1),
    (re.compile(r'\b[\w.+-]{1,64}@[\w.-]{1,255}\.[A-Za-z]{2,24}\b'), '[REDACTED_EMAIL]', 0),
    (re.compile(r'(?<![\w.+-])(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)[ .-]?|\d{3}[ .-])\d{3}[ .-]\d{4}(?![\w-])'), '[REDACTED_PHONE]', 0),
    (re.compile(r'(?<![\w+])\+\d{8,15}(?!\d)'), '[REDACTED_PHONE]', 0),
    (re.compile(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)'), '[REDACTED_LONG_NUMBER]', 0),
    (re.compile(r'\b00[1-9A-Za-z][A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b'), '[REDACTED_CRM_ID]', 0),
)
# Key-name-anywhere rule: a credential word in a key name (`"password": "x"`, `SUPABASE_SERVICE_ROLE_KEY=x`,
# `api key: x`, `Authorization: Basic x`) redacts its whole line, and the lines that carry its value when that
# sits below (JSON, YAML, YAML block scalars). It is a bounded scan, not one big pattern.
# Long words match anywhere in a name (PGPASSWORD, dbPassword, GITHUBTOKEN, _authToken). Short, ordinary-looking words
# need a left edge: not glued to a preceding letter, or a camelCase boundary (userAuth, dbPin). `pass` also matches
# inside a name (dbpass) except after the few English words that end in it. Trailing guards keep author:, authors:,
# max_tokens= and passing clean.
_LEFT = r'(?:(?<![A-Za-z])|(?-i:(?<=[a-z])(?=[A-Z])))'
CREDENTIAL_WORD = re.compile(
    r'(?i)(?:password|passwd|passphrase|passcode|secret|api[ _-]?key|apikey|access[ _-]?key|private[ _-]?key|'
    r'(?:signing|encryption|anon|service[ _-]?role)[ _-]?key|credentials?|token(?!s)|(?<![A-Za-z_])tokens(?=(?:\\{1,3}["\']|["\'])?[ \t]*[:=])|'
    r'pwd(?=(?:\\{1,3}["\']|["\'])?[ \t]*[:=])|bearer|webhook|(?<!by)(?<!com)(?<!tres)(?<!sur)(?<!over)(?<!under)pass(?![A-Za-z])|'
    + _LEFT + r'(?:pw|pin|creds?|auth(?:orization)?|cookies?|session)(?![A-Za-z])|'
    r'(?<=[A-Za-z0-9])[ _-]key\b)')
# `_Q` is a quote, plain or escaped (`\"` inside a JSON string that is itself in a string, `\\\"` double-escaped).
_Q = r'''(?:\\{1,3}["']|["'])?'''
# Runtime suffix matches start immediately after a credential word. Reject search restarts within
# whitespace and overlong first segments before backtracking; anchored runtime match spans stay the same.
_SUFFIX_START = r'(?<![ \t])(?![\w.-]{257})'
CREDENTIAL_TAIL = re.compile(_SUFFIX_START + r'[\w.-]{0,256}(?:[ \t]{1,3}(?:\([^)\n]{0,40}\)|[\w.-]{1,256})){0,3}' + _Q + r'[ \t]*[:=]')
# The word sits where the value would be (a tag, a header, a quoted name, a name/value pair): the line and the next
# value line carry the secret. Only characters that end a name count, so prose such as "password manager" is spared.
NAME_END = re.compile(_SUFFIX_START + r'''[\w.-]{0,256}[ \t]*(?:\\{0,3}["',|>]|$)''', re.M)
# Command and file shapes: `ENV SECRET v`, netrc `password v` / `machine h login u password v`.
COMMAND_SECRET = re.compile(
    r'(?im)^[ \t]*(?:ENV|ARG|SET|EXPORT|SETENV|DEFINE)[ \t]+[\w.-]{0,128}(?:password|passwd|passphrase|secret|token|api[_-]?key|'
    r'credentials?)[\w.-]{0,128}[ \t]+\S')
NETRC_SECRET = re.compile(r'(?im)^[ \t]*password[ \t]+\S+[ \t]*$|\b(?:machine|login)[ \t]+\S{1,512}.{0,300}?\bpassword[ \t]+\S')
NATURAL_SECRET = re.compile(
    r'(?i)(?:password|passwd|passphrase|passcode|secret|token|api[ _-]?key|apikey|' + _LEFT + r'(?:pwd|pw|pin|creds?))'
    r'(?:\s{0,3}\([^)\n]{0,40}\))?(?:\s{1,4}(?:is|was|to|should be|will be)\s{1,4}|\s{0,4}(?:=>|->|\u2192)\s{0,4})\S')
# `pass` is an ordinary word ("the first pass is done", "lint pass was clean"), so it counts only with a credential
# context, a glued name ending (`dbPass`, `db_pass`), one ending token after a bare sentence start ("pass is hunter2"), or
# a token that is not a dictionary word (a digit, an inner capital or a symbol: "the first pass is hunter2").
_PASS_CONTEXT = (r'(?:(?:my|your|our|their|his|her|new|old|temp|temporary|current|sudo|mac|laptop|router|gmail|email|master)|'
                 r'(?:the\s{1,4})?(?:admin|root|db|database|user|login|wifi|wi-fi|account|ssh|vpn))\s{1,4}')
NATURAL_PASS = re.compile(r'(?i)(?:' + _LEFT + _PASS_CONTEXT + r'pass|(?-i:(?<=[a-z])Pass)|(?<=_)pass)'
                          r'\s{1,4}(?:is|was)\s{1,4}\S')
NATURAL_PASS_ODD = re.compile(r'(?i)' + _LEFT + r'pass\s{1,4}(?:is|was)\s{1,4}'
                              r'(?=\S{0,200}?(?:\d|(?-i:[a-z][A-Z])|[@#$%^&*+=/\\|<>~{}\[\]_]))\S')
NATURAL_PASS_BARE = re.compile(r'(?im)(?:^[ \t]{0,8}|[.!?:;,]\s{1,4}|\b(?:the|a|this|that)\s{1,4})pass\s{1,4}(?:is|was)\s{1,4}'
                               r'\S{1,200}[ \t]*(?:[.!?,;](?:\s|$)|$)')
SEPARATOR_LINE = re.compile(r'^[\s|:+=-]*$')
STRONG_WORD = re.compile(r'(?i)password|passwd|passphrase|passcode|secret|token|key|credential')
BLOCK_HEADER = re.compile(r'^(?:[!&]\S+\s+)*[|>][+\-0-9]*\s*(?:#.*)?$')
VALUE_BELOW = ('', '[', '{', '(')
MAX_BLOCK_LINES, MAX_BLOCK_CHARS = 200, 20000
MAX_CONTAINER_LINES, MAX_CONTAINER_CHARS = 50, 4000
# Generic fallbacks: a long unbroken key-like run with lower case, upper case and a digit; and, with base64
# punctuation, a longer run that also looks random.
KEY_RUN = re.compile(r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,}')
KEY_RUN_B64 = re.compile(r'(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/=-]{40,}')

def _is_lower(char):
    return 'a' <= char <= 'z'


def _is_upper(char):
    return 'A' <= char <= 'Z'


def _is_digit(char):
    return '0' <= char <= '9'


def _segment_like(segment):
    """Is one path segment made of identifier-like words: lower case words, Capitalized words, digits, `_` and `-`
    separators and ALLCAPS words? A linear scanner (each character is consumed once), not a regex: the nested
    alternation this replaces split a lower case run in exponentially many ways.

    An ALLCAPS word (`[A-Z][A-Z0-9]*`) counts at the start of a segment, after a separator, before a separator, or as
    the trailing word (`marketA`, `workerV2`, `PanelUI`). A capital glued inside a lower case run that is neither
    (`aGVs`, `xQ3m`) does not, which is what keeps random base64 from reading as a path. A long segment must also be
    made of real words (three letters on average; digits split words): base64 that happens to parse as humps
    (`AdMaKqKcyOiWpB`) has words of one or two letters."""
    i, size, letters, words = 0, len(segment), 0, 0
    while i < size:
        char = segment[i]
        if _is_lower(char):
            start = i
            while i < size and _is_lower(segment[i]):
                i += 1
            letters, words = letters + i - start, words + 1
        elif _is_digit(char):
            while i < size and _is_digit(segment[i]):
                i += 1
        elif char in '_-':
            i += 1
        elif _is_upper(char):
            j = i
            while j < size and _is_upper(segment[j]):
                j += 1
            if j < size and _is_lower(segment[j]):
                if j - i != 1:                                # only a single capital is a hump (`Panel`); `GVs` is not
                    return False
                i = j
                while j < size and _is_lower(segment[j]):
                    j += 1
                letters, words, i = letters + j - i + 1, words + 1, j
                continue
            while j < size and (_is_upper(segment[j]) or _is_digit(segment[j])):
                j += 1
            if j < size and _is_lower(segment[j]):
                return False
            if not (i == 0 or segment[i - 1] in '_-' or j == size or segment[j] in '_-'):
                return False
            letters += sum(1 for c in segment[i:j] if _is_upper(c))
            words, i = words + 1, j
        else:
            return False
    return letters < 9 or letters >= 3 * words


def _path_like(run):
    """A run of `/`-separated identifier-like segments (words, camelCase, snake and kebab case, ALLCAPS): a file
    path or URL path, not random base64, whose letters are not built from whole words."""
    return '+' not in run and '=' not in run and all(_segment_like(part) for part in run.split('/'))


def _looks_like_key(run):
    return any(c.islower() for c in run) and any(c.isupper() for c in run) and any(c.isdigit() for c in run)


def _entropy(run):
    counts = Counter(run)
    return -sum(n / len(run) * math.log2(n / len(run)) for n in counts.values())


class Lines:
    """Line boundaries computed once per text, so a match never rescans its line (linear on one giant line)."""

    def __init__(self, text):
        self.text = text
        self.breaks = [i for i, c in enumerate(text) if c == '\n']

    def bounds(self, position):
        index = bisect.bisect_left(self.breaks, position)
        start = self.breaks[index - 1] + 1 if index else 0
        end = self.breaks[index] if index < len(self.breaks) else len(self.text)
        return start, end


def _bracket_depth(text, depth):
    """Bracket depth after `text`, ignoring brackets inside quoted strings (a string never spans lines here, so a
    stray apostrophe cannot poison the following lines)."""
    quote, escaped = None, False
    for char in text:
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
        elif char in '"\'':
            quote = char
        elif char in '[{':
            depth += 1
        elif char in ']}':
            depth -= 1
    return depth


def _container_end(lines, position, depth):
    """End of the bracket or brace value that starts at `position` with `depth` already open. A container still
    open at the line or character bound (counted from where it started) redacts the rest of the message."""
    text, first, taken = lines.text, position, 0
    end = position
    while position <= len(text):
        if taken >= MAX_CONTAINER_LINES or position - first >= MAX_CONTAINER_CHARS:
            return len(text)
        _, stop = lines.bounds(position)
        depth = _bracket_depth(text[position:stop], depth)
        end, position, taken = stop, stop + 1, taken + 1
        if depth <= 0 or stop >= len(text):
            break
    return end


def _value_is_below(rest):
    """Does the value of a key whose line ends with `rest` continue on the following lines?"""
    return (rest in VALUE_BELOW or bool(BLOCK_HEADER.match(rest))
            or (rest[:1] in ('[', '{') and _bracket_depth(rest, 0) > 0))


def _value_below_end(lines, key_start, key_end, rest):
    """End of the lines that hold a value written below its key: a block scalar body (fail closed: the rest of the
    message when it is still open at the cap), a bracketed or braced value (also one the key line itself opens), a
    YAML list, or the next value line (table separator rows and a couple of blank lines are skipped over)."""
    text = lines.text
    end, position = key_end, key_end + 1
    if BLOCK_HEADER.match(rest):
        indent = len(text[key_start:key_end]) - len(text[key_start:key_end].lstrip(' \t'))
        count = 0
        while position <= len(text):
            if count >= MAX_BLOCK_LINES or position - key_end >= MAX_BLOCK_CHARS:
                return len(text)
            _, stop = lines.bounds(position)
            line = text[position:stop]
            if line.strip() and len(line) - len(line.lstrip(' \t')) <= indent:
                break
            end, position, count = stop, stop + 1, count + 1
            if stop >= len(text):
                break
        return end
    if rest[:1] in ('[', '{'):
        return _container_end(lines, position, max(_bracket_depth(rest, 0), 1))
    for _ in range(6):
        if position > len(text):
            break
        start, stop = lines.bounds(position)
        line = text[start:stop]
        end, position = stop, stop + 1
        if not line.strip() or SEPARATOR_LINE.match(line):
            continue
        opener = line.lstrip()[:1]
        if opener in ('[', '{'):
            return _container_end(lines, start, 0)
        if opener == '-':
            indent = len(line) - len(line.lstrip(' \t'))
            while position <= len(text):                       # a YAML block list: every following item
                _, stop = lines.bounds(position)
                item = text[position:stop]
                if item.strip() and (not item.lstrip().startswith('-') or len(item) - len(item.lstrip(' \t')) < indent):
                    break
                end, position = stop, stop + 1
                if stop >= len(text):
                    break
        break
    return end


def _k8s_value_end(lines, end):
    """`- name: DB_PASSWORD`, then up to three key lines (`valueFrom:`), then `value: v`: take the value line too."""
    text, position = lines.text, end + 1
    for _ in range(4):
        if position > len(text):
            break
        _, stop = lines.bounds(position)
        line = text[position:stop].strip()
        position = stop + 1
        if not line:
            continue
        if line.startswith(('- ', '-\t')):
            break
        if line.startswith(('value:', 'value ', '"value"', "'value'")):
            return stop
    return end


def _credential_spans(text):
    lines = Lines(text)
    spans, covered = [], -1
    for match in CREDENTIAL_WORD.finditer(text):
        if match.start() < covered:
            continue
        start, end = lines.bounds(match.start())
        tail = CREDENTIAL_TAIL.match(text, match.end())
        if tail:
            rest = text[tail.end():end].strip(' \t\r"\'\\')
            spans.append((start, _value_below_end(lines, start, end, rest) if _value_is_below(rest) else end))
        elif STRONG_WORD.search(match.group()):
            # The word is the value or a tag (`"name": "DB_PASSWORD"`, `<password>`, a table header): take the line
            # and the value line below it.
            if not NAME_END.match(text, match.end()):
                continue
            spans.append((start, max(_value_below_end(lines, start, end, ''), _k8s_value_end(lines, end))))
        else:
            continue
        covered = spans[-1][1]
    for pattern in (NATURAL_SECRET, NATURAL_PASS, NATURAL_PASS_ODD, NATURAL_PASS_BARE, COMMAND_SECRET, NETRC_SECRET):
        last = -1
        for match in pattern.finditer(text):
            if match.start() >= last:
                span = lines.bounds(match.start())
                spans.append(span)
                last = span[1]
    return [(a, b, '[REDACTED_CREDENTIAL_LINE]') for a, b in spans]


def _normalized(char):
    if char in ZERO_WIDTH:
        return ''
    if char in '  \x85':
        return '\n'
    if char != '\n' and char.isspace():
        return ' '
    if char.isascii():
        return char
    folded = unicodedata.normalize('NFKC', char)
    return ''.join(c for c in folded if unicodedata.category(c) not in ('Cf', 'Mn', 'Me')).translate(HOMOGLYPHS)


def detection_view(text):
    """(view, starts, ends, cutoff): a normalized copy used only for matching (NFKC, zero-width and format characters
    dropped, Unicode whitespace as a space, look-alike Cyrillic/Greek letters as Latin, \\uXXXX and \\xNN escapes
    decoded). view[j] came from text[starts[j]:ends[j]], so a match redacts the ORIGINAL span. Plain ASCII without
    escapes is its own view (starts and ends are None). Past MAX_ESCAPES the rest of the text cannot be normalized,
    so decoding stops there and `cutoff` is the original offset from which everything must be treated as redacted."""
    if text.isascii() and '\\u' not in text and '\\x' not in text:
        return text, None, None, None
    view, starts, ends = [], [], []
    position, escapes, cutoff = 0, 0, None
    while position < len(text):
        char, stop = text[position], position + 1
        if char == '\\':
            found = ESCAPE.match(text, position)
            if found:
                if escapes >= MAX_ESCAPES:
                    cutoff = position
                    break
                escapes += 1
                char, stop = chr(int(found.group(1) or found.group(2), 16)), found.end()
        for piece in _normalized(char):
            view.append(piece)
            starts.append(position)
            ends.append(stop)
        position = stop
    return ''.join(view), starts, ends, cutoff


def _view_spans(view):
    found = []
    for pattern, marker, keep in REDACTIONS:
        for match in pattern.finditer(view):
            found.append((match.end(keep) if keep else match.start(), match.end(), marker))
    for match in SNAKE_TOKEN.finditer(view):
        if any(c.isdigit() or c.isupper() for c in match.group()):
            found.append((match.start(), match.end(), '[REDACTED_TOKEN]'))
    found += _credential_spans(view)
    for match in KEY_RUN.finditer(view):
        if _looks_like_key(match.group()):
            found.append((match.start(), match.end(), '[REDACTED_TOKEN]'))
    for match in KEY_RUN_B64.finditer(view):
        run = match.group()
        # With base64 punctuation the entropy alone decides (a base64 secret may have no digit), so ordinary words
        # and paths, which are far less random, stay.
        if any(c in run for c in '+/=') and len(set(run)) >= 20 and _entropy(run) >= 4.2 and not _path_like(run):
            found.append((match.start(), match.end(), '[REDACTED_TOKEN]'))
    return found


def redact(text):
    """Replace secrets and personal identifiers with markers. Matching sees the normalized view; the
    replacement always lands on the original span, so an obfuscated secret cannot survive next to its marker."""
    view, starts, ends, cutoff = detection_view(text)
    spans = [(a, b, marker) for a, b, marker in _view_spans(view) if b > a]
    if starts is not None:
        spans = [(starts[a], ends[b - 1], marker) for a, b, marker in spans]
    if cutoff is not None:
        spans.append((cutoff, len(text), '[REDACTED_UNDECODABLE_REMAINDER]'))
    if not spans:
        return text
    spans.sort(key=lambda span: (span[0], -span[1]))
    merged = []
    for start, end, marker in spans:
        if merged and start < merged[-1][1]:
            last = merged[-1]
            biggest = marker if end - start > last[3] else last[2]
            merged[-1] = [last[0], max(last[1], end), biggest, max(last[3], end - start)]
        else:
            merged.append([start, end, marker, end - start])
    parts, position = [], 0
    for start, end, marker, _ in merged:
        parts += [text[position:start], marker]
        position = end
    return ''.join(parts) + text[position:]


def _cut(text, limit):
    """The first `limit` characters, with a token cut in half at the edge dropped."""
    if len(text) <= limit:
        return text
    kept = text[:limit]
    if text[limit].isspace():
        return kept
    edge = len(kept)                                 # walk back over the half token (linear, unlike `\S+$`)
    while edge > 0 and not kept[edge - 1].isspace():
        edge -= 1
    return kept[:edge]


def sanitize(text, limit):
    """Redact the WHOLE message first, then bound it, so a secret cut by the bound is never half-exposed.

    Only an absurdly large message is cut before redaction, and that cut also lands on a token edge. Only the
    head of a message is ever kept: a tail cut could split a key from its value.
    """
    text = _cut(text, MAX_MESSAGE_CHARS)
    text = redact(text)
    if len(text) <= limit:
        return text, False
    return _cut(text, limit) + '\n[TRUNCATED: more source context exists]', True


