"""
LEXER (Tokenizer)
-----------------
Yeh module JS source code ko ek-ek "token" mein todta hai.
Token = chhota meaningful unit, jaise: number, string, identifier, keyword, operator, punctuation.

Example:
  "let num = 7;"
  ->  [LET, IDENT(num), ASSIGN, NUMBER(7), SEMI]
"""

KEYWORDS = {
    "let", "const", "var", "function", "return", "if", "else", "for", "while",
    "do", "true", "false", "null", "undefined", "new", "typeof", "switch",
    "case", "default", "break", "continue", "in", "of", "this", "class",
    "delete", "instanceof"
}

# Multi-character operators MUST be listed longest-first so the lexer
# matches '===' before '==' before '='.
OPERATORS = [
    "===", "!==", "**=", ">>>", "...",
    "==", "!=", "<=", ">=", "&&", "||", "??",
    "+=", "-=", "*=", "/=", "%=", "**",
    "++", "--", "=>",
    "+", "-", "*", "/", "%", "=", "<", ">", "!", "?", ":",
    "(", ")", "{", "}", "[", "]", ",", ".", ";", "&", "|", "^", "~"
]


class Token:
    def __init__(self, type_, value, line=0):
        self.type = type_   # e.g. 'NUMBER', 'STRING', 'IDENT', 'KEYWORD', 'OP', 'EOF'
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


class Lexer:
    def __init__(self, source):
        self.src = source
        self.pos = 0
        self.line = 1
        self.length = len(source)

    def error(self, msg):
        raise SyntaxError(f"Lexer error at line {self.line}: {msg}")

    def peek_char(self, offset=0):
        p = self.pos + offset
        if p < self.length:
            return self.src[p]
        return ""

    def advance(self):
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
        return ch

    def tokenize(self):
        tokens = []
        while self.pos < self.length:
            ch = self.peek_char()

            # 1. Skip whitespace
            if ch in " \t\r\n":
                self.advance()
                continue

            # 2. Skip comments
            if ch == "/" and self.peek_char(1) == "/":
                while self.pos < self.length and self.peek_char() != "\n":
                    self.advance()
                continue
            if ch == "/" and self.peek_char(1) == "*":
                self.advance(); self.advance()
                while self.pos < self.length and not (self.peek_char() == "*" and self.peek_char(1) == "/"):
                    self.advance()
                self.advance(); self.advance()
                continue

            # 3. Numbers (integers and floats)
            if ch.isdigit() or (ch == "." and self.peek_char(1).isdigit()):
                tokens.append(self._read_number())
                continue

            # 4. Strings (single, double, and template literals with backticks)
            if ch in ('"', "'"):
                tokens.append(self._read_string(ch))
                continue
            if ch == "`":
                tokens.append(self._read_template_string())
                continue

            # 5. Identifiers and keywords
            if ch.isalpha() or ch == "_" or ch == "$":
                tokens.append(self._read_identifier())
                continue

            # 6. Operators and punctuation (longest match first)
            matched = False
            for op in OPERATORS:
                if self.src[self.pos:self.pos + len(op)] == op:
                    tokens.append(Token("OP", op, self.line))
                    for _ in op:
                        self.advance()
                    matched = True
                    break
            if matched:
                continue

            self.error(f"Unexpected character: {ch!r}")

        tokens.append(Token("EOF", None, self.line))
        return tokens

    def _read_number(self):
        start = self.pos
        while self.pos < self.length and (self.peek_char().isdigit() or self.peek_char() == "."):
            self.advance()
        text = self.src[start:self.pos]
        if "." in text:
            value = float(text)
        else:
            value = int(text)
        return Token("NUMBER", value, self.line)

    def _read_string(self, quote):
        start_line = self.line   # string shuru hone ki line yaad rakho
        self.advance()  # skip opening quote
        result = []
        while self.pos < self.length and self.peek_char() != quote:
            ch = self.peek_char()
            if ch == "\n" or ch == "\r":
                raise SyntaxError(f"Lexer error at line {start_line}: Unterminated string")
            
            ch = self.advance()
            if ch == "\\":
                nxt = self.advance()
                if nxt in ("\n", "\r"):
                    # Escaped newline (line continuation in JS)
                    if nxt == "\r" and self.peek_char() == "\n":
                        self.advance()
                    continue
                escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\",
                           "'": "'", '"': '"', "`": "`"}
                result.append(escapes.get(nxt, nxt))
            else:
                result.append(ch)
        if self.pos >= self.length:
            raise SyntaxError(f"Lexer error at line {start_line}: Unterminated string")
        self.advance()  # skip closing quote
        return Token("STRING", "".join(result), start_line)

    def _read_template_string(self):
        """
        Reads a template literal (`...`). We split it into a list of
        parts: plain strings and ${expr} interpolation source snippets.
        The parser will later parse each ${...} part as an expression.
        Result token value = list of ("str", text) or ("expr", source_code)
        """
        start_line = self.line   # template shuru hone ki line
        self.advance()  # skip backtick
        parts = []
        buf = []
        while self.pos < self.length and self.peek_char() != "`":
            ch = self.peek_char()
            if ch == "\\":
                self.advance()
                nxt = self.advance()
                escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\",
                           "'": "'", '"': '"', "`": "`"}
                buf.append(escapes.get(nxt, nxt))
                continue
            if ch == "$" and self.peek_char(1) == "{":
                if buf:
                    parts.append(("str", "".join(buf)))
                    buf = []
                self.advance(); self.advance()  # skip ${
                depth = 1
                expr_src = []
                while self.pos < self.length and depth > 0:
                    c = self.peek_char()
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            self.advance()
                            break
                    expr_src.append(self.advance())
                parts.append(("expr", "".join(expr_src)))
                continue
            buf.append(self.advance())
        if buf:
            parts.append(("str", "".join(buf)))
        if self.pos >= self.length:
            raise SyntaxError(f"Lexer error at line {start_line}: Unterminated template string")
        self.advance()  # skip closing backtick
        return Token("TEMPLATE", parts, start_line)

    def _read_identifier(self):
        start = self.pos
        while self.pos < self.length and (self.peek_char().isalnum() or self.peek_char() in "_$"):
            self.advance()
        text = self.src[start:self.pos]
        if text in KEYWORDS:
            return Token("KEYWORD", text, self.line)
        return Token("IDENT", text, self.line)
