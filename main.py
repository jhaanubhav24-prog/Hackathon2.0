#!/usr/bin/env python3
"""
main.py - JS Runtime Entry Point

USAGE:
    python3 main.py script.js
    python3 main.py -c "console.log('hello')"
    echo "console.log(1+1)" | python3 main.py
"""

import sys
from jsinterp.interpreter import Interpreter, JSThrow


def main():
    source = None

    # ---- input kaise lega ----
    # Case 1: python3 main.py -c "console.log(1)"
    #         sys.argv[1] = "-c"
    #         sys.argv[2] = "console.log(1)"  <- seedha code
    if len(sys.argv) >= 3 and sys.argv[1] == "-c":
        source = sys.argv[2]

    # Case 2: python3 main.py script.js
    #         sys.argv[1] = "script.js"  <- file naam
    elif len(sys.argv) >= 2:
        path = sys.argv[1]
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except FileNotFoundError:
            print(f"[ERROR] File nahi mili bhai: '{path}'")
            sys.exit(1)

    # Case 3: echo "..." | python3 main.py  <- stdin se
    else:
        source = sys.stdin.read()

    # ---- run karo ----
    # stdout ko utf-8 mode mein set karo (Windows ke liye)
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    interpreter = Interpreter()
    try:
        output = interpreter.run(source)
        if output:
            print(output)

    except JSThrow as e:
        # JS ke andar koi variable nahi mila ya type error
        msg = str(e.value)
        # line number nikalo agar ho
        line = _extract_line(msg)
        if line:
            print(f"[ERROR] Line {line} pe kuch gadbad hai bhai --> {_clean(msg)}")
        else:
            print(f"[ERROR] Error aaya bhai --> {_clean(msg)}")
        sys.exit(1)

    except SyntaxError as e:
        # galat JS syntax
        msg = str(e)
        line = _extract_line(msg)
        if line:
            print(f"[ERROR] Line {line} pe syntax galat hai bhai --> {_clean(msg)}")
        else:
            print(f"[ERROR] Syntax galat hai bhai --> {_clean(msg)}")
        sys.exit(1)

    except Exception as e:
        print(f"[ERROR] Kuch to gadbad hai bhai --> {str(e)}")
        sys.exit(1)


def _extract_line(msg):
    """Error message se line number nikalta hai."""
    import re
    m = re.search(r'line\s+(\d+)', str(msg), re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _clean(msg):
    """Error message ko chhota aur readable banata hai."""
    msg = str(msg)
    import re
    # "Lexer error at line X: Unterminated string" -> "Unterminated string"
    m_lexer = re.match(r"Lexer error at line \d+:\s*(.+)", msg)
    if m_lexer:
        return m_lexer.group(1).strip()
    # "Unexpected token in expression: Token(OP, ';') at line 3"
    # -> "Unexpected token ';'"
    m = re.search(r"Token\(\w+,\s*'?([^'\")\s]+)'?\)", msg)
    if m:
        token = m.group(1)
        if "Unexpected" in msg:
            return f"'{token}' yahan nahi aana chahiye tha"
        if "Expected" in msg:
            what = msg.split("Expected")[1].split("but")[0].strip()
            return f"'{what}' expected tha, '{token}' aa gaya"
    return msg.split(" at line")[0]  # line number wala part hata do


if __name__ == "__main__":
    main()