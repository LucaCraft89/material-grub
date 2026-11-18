"""A small GRUB script tokenizer and block finder (stdlib only).

It replaces line-by-line regexes on grub.cfg. It understands what the regexes could not:
  - quoting: 'single' (no escapes), "double" (backslash escapes), backslash escapes outside quotes, and strings that span lines
  - comments (a `#` that starts a word), line continuation (backslash + newline)
  - `{` and `}` as block delimiters only when they are a word of their own (so `}` inside a title is just text)
  - menuentry / submenu blocks, nested to any depth, with their title, options and the offset where a class can be inserted
  - which lines start a command (so a line inside a multi-line title is never mistaken for `blscfg` or `menuentry`)

Offsets are character offsets into the text that was scanned; nothing is rewritten here.
"""

COMMAND_KEYWORDS = ("then", "else", "do", "elif", "if", "while", "until", "!", "time")
OPERATORS = "|&;<>()"  # a word ends at one of these when it is not quoted


class Token:
    __slots__ = ("kind", "text", "value", "start", "end", "line", "bol", "cmd")

    def __init__(self, kind, text, value, start, end, line, bol, cmd):
        self.kind, self.text, self.value = kind, text, value  # kind: word, op ("{" "}" ";" "\n" ...), comment
        self.start, self.end, self.line = start, end, line  # line: 0-based line of the first character
        self.bol = bol  # first token on its line (not counting a line continuation or a string that spans lines)
        self.cmd = cmd  # at command position: the first word of a command

    def __repr__(self):
        return f"Token({self.kind}, {self.text!r}, line={self.line}, cmd={self.cmd})"


class Entry:
    """A menuentry or submenu block."""

    def __init__(self, word, title, title_end, args, token_index):
        self.word = word  # "menuentry" or "submenu"
        self.title = title  # the first argument, unquoted
        self.title_end = title_end  # offset just after the title word: insert " --class x" here
        self.args = args  # all arguments before `{`, unquoted
        self.token_index = token_index
        self.open_brace = None  # offset of `{`
        self.close_brace = None  # offset of the matching `}` (None: never closed)
        self.parent = None  # enclosing Entry or None
        self.line = 0
        self.start = 0  # offset of the `menuentry` / `submenu` word
        self.guarded = (
            False  # inside an if/while/for/case or a function body: the block cannot be moved or removed on its own
        )

    @property
    def end(self):
        """Offset just after the closing brace (None when the block is never closed)."""
        return None if self.close_brace is None else self.close_brace + 1

    @property
    def classes(self):
        out = []
        for i, a in enumerate(self.args):
            if a == "--class" and i + 1 < len(self.args):
                out.append(self.args[i + 1])
        return out

    @property
    def level(self):
        p = self.parent
        while p is not None:
            if p.word == "submenu":
                return "adv"
            p = p.parent
        return "top"

    def __repr__(self):
        return f"Entry({self.word}, {self.title!r}, line={self.line}, level={self.level})"


class Scan:
    def __init__(self, text, tokens, entries):
        self.text, self.tokens, self.entries = text, tokens, entries
        self._by_line = {}
        for t in tokens:
            if t.bol and t.kind in ("word", "comment"):
                self._by_line.setdefault(t.line, t)

    def command_at_line(self, line):
        """The first command word on a (0-based) line when a command really starts there; else None."""
        t = self._by_line.get(line)
        return t if t is not None and t.kind == "word" and t.cmd else None

    def comment_at_line(self, line):
        t = self._by_line.get(line)
        return t if t is not None and t.kind == "comment" else None


def split_lines(text):
    """Lines the way GRUB sees them: only a line feed ends a line. Each item keeps its line ending."""
    parts = text.split("\n")
    out = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        out.append(parts[-1])
    return out


def _word(text, i, n):
    """Read one word starting at i. Returns (end, value). Quotes and escapes are resolved in value."""
    value = []
    j = i
    while j < n:
        c = text[j]
        if c in " \t\r\n" or c in OPERATORS:
            break
        if c == "\\":
            if j + 1 < n:
                nxt = text[j + 1]
                if nxt == "\n":  # line continuation: joins the pieces
                    j += 2
                    continue
                value.append(nxt)
                j += 2
                continue
            j += 1
            continue
        if c == "'":
            k = text.find("'", j + 1)
            if k < 0:
                value.append(text[j + 1 :])
                return n, "".join(value)
            value.append(text[j + 1 : k])
            j = k + 1
            continue
        if c == '"':
            j += 1
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n and text[j + 1] in '"\\$\n':
                    if text[j + 1] != "\n":
                        value.append(text[j + 1])
                    j += 2
                    continue
                value.append(text[j])
                j += 1
            j += 1  # closing quote
            continue
        if c in "{}" and j == i:
            break  # handled by the caller: a lone brace is a token
        value.append(c)
        j += 1
    return j, "".join(value)


def tokenize(text):
    tokens = []
    n = len(text)
    i = 0
    line = 0
    bol = True  # no token yet on this line
    cmd = True  # next word is at command position
    while i < n:
        c = text[i]
        if c == "\n":
            tokens.append(Token("op", "\n", "\n", i, i + 1, line, False, False))
            line += 1
            i += 1
            bol, cmd = True, True
            continue
        if c in " \t\r":
            i += 1
            continue
        if c == "\\" and text[i + 1 : i + 2] == "\n":  # continuation between words
            line += 1
            i += 2
            continue
        if c == "#":  # a comment runs to the end of the line
            j = text.find("\n", i)
            j = n if j < 0 else j
            tokens.append(Token("comment", text[i:j], text[i:j], i, j, line, bol, False))
            bol = False
            i = j
            continue
        if c in "{}":
            # a brace is a token only as a whole word: `{` or `}` followed by a separator
            nxt = text[i + 1 : i + 2]
            if nxt == "" or nxt in " \t\r\n" or nxt in OPERATORS or nxt == "#":
                tokens.append(Token("op", c, c, i, i + 1, line, bol, False))
                bol = False
                cmd = True
                i += 1
                continue
        if c in OPERATORS:
            j = i + 1
            while j < n and text[j] in OPERATORS and text[j] in "&|" and text[j] == c:
                j += 1
            tokens.append(Token("op", text[i:j], text[i:j], i, j, line, bol, False))
            bol = False
            cmd = text[i:j] in (";", "&&", "||", "|", "&", "(")
            i = j
            continue
        j, value = _word(text, i, n)
        if j == i:  # a lone brace inside a word start that was not a token: take it as text
            j = i + 1
            value = text[i]
        raw = text[i:j]
        tokens.append(Token("word", raw, value, i, j, line, bol, cmd))
        line += raw.count("\n")  # newlines inside quotes and continuations move the line counter
        bol = False
        cmd = cmd and value in COMMAND_KEYWORDS
        i = j
    return tokens


def scan(text):
    tokens = tokenize(text)
    entries = []
    frames = []  # open `{` blocks: an Entry, or None for a function body and the like
    ctrl = 0  # open if / while / until / for / case constructs
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t.kind == "word" and t.cmd and t.value in ("menuentry", "submenu"):
            args = []
            j = i + 1
            while j < n and tokens[j].kind == "word":
                args.append(tokens[j])
                j += 1
            if j < n and tokens[j].kind == "op" and tokens[j].text == "{" and args:
                e = Entry(t.value, args[0].value, args[0].end, [a.value for a in args], i)
                e.line = t.line
                e.start = t.start
                e.guarded = ctrl > 0 or any(f is None for f in frames)
                e.open_brace = tokens[j].start
                e.parent = next((f for f in reversed(frames) if f is not None), None)
                entries.append(e)
                frames.append(e)
                i = j + 1
                continue
            i = j  # a menuentry without a block is not valid GRUB script: not an entry
            continue
        if t.kind == "word" and t.cmd and t.value in ("if", "while", "until", "for", "case", "select"):
            ctrl += 1
        elif t.kind == "word" and t.cmd and t.value in ("fi", "done", "esac") and ctrl:
            ctrl -= 1
        if t.kind == "op" and t.text == "{":
            frames.append(None)
        elif t.kind == "op" and t.text == "}" and frames:
            f = frames.pop()
            if f is not None:
                f.close_brace = t.start
        i += 1
    return Scan(text, tokens, entries)
