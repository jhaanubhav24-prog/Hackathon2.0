"""
INTERPRETER (Tree-Walking Evaluator)
--------------------------------------
Yeh module AST ko traverse karta hai aur har node ko "evaluate" karta hai.
Yeh JS ki semantics (rules) ko Python mein simulate karta hai:

- JS object/array  -> Python dict / list (with JSObject/JSArray wrappers for methods)
- JS function       -> Python callable wrapping AST + closure environment
- JS undefined      -> special UNDEFINED sentinel (Python None represents JS null)
- console.log       -> Python print, with JS-style value formatting

ENVIRONMENT / SCOPE:
Each function call and block creates a new "Environment" (variable scope)
that has a reference to its parent scope (-> closures work naturally).
"""

import math
import random
import time
import datetime

from .ast_nodes import Node


# ---------------------------------------------------------------------------
# Special sentinel values
# ---------------------------------------------------------------------------

class JSUndefined:
    """Represents JavaScript's `undefined` (distinct from `null`/None)."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "undefined"

    def __bool__(self):
        return False

    def __eq__(self, other):
        return isinstance(other, JSUndefined)

    def __hash__(self):
        return hash("undefined")


UNDEFINED = JSUndefined()


# ---------------------------------------------------------------------------
# Control-flow signal exceptions (used to implement return/break/continue)
# ---------------------------------------------------------------------------

class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class BreakSignal(Exception):
    pass


class ContinueSignal(Exception):
    pass


class JSThrow(Exception):
    """Represents a JS `throw` (used by errors raised inside interpreter)."""
    def __init__(self, value):
        self.value = value


# ---------------------------------------------------------------------------
# Environment (scope chain)
# ---------------------------------------------------------------------------

class Environment:
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def get(self, name):
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.get(name)
        raise JSThrow(f"ReferenceError: {name} is not defined")

    def set(self, name, value):
        """Assign to an existing variable (walks up scope chain)."""
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        # If not found anywhere, create in global (sloppy-mode JS behaviour)
        self.get_global().vars[name] = value

    def declare(self, name, value):
        """Declare a new variable in THIS scope (let/const/var/function param)."""
        self.vars[name] = value

    def get_global(self):
        env = self
        while env.parent is not None:
            env = env.parent
        return env


# ---------------------------------------------------------------------------
# JS Function representation
# ---------------------------------------------------------------------------

class JSFunction:
    """A user-defined JS function (declaration, expression, or arrow)."""

    def __init__(self, name, params, body, closure_env, expr_body=False, this_val=None):
        self.name = name
        self.params = params
        self.body = body
        self.closure_env = closure_env
        self.expr_body = expr_body  # True for arrow functions with expression body
        self.this_val = this_val    # bound `this` (used for arrow functions)

    def __repr__(self):
        return f"<function {self.name or '(anonymous)'}>"


class NativeFunction:
    """Wraps a Python callable so it can be called like a JS function/method."""

    def __init__(self, func, name="native"):
        self.func = func
        self.name = name

    def __call__(self, *args):
        return self.func(*args)

    def __repr__(self):
        return f"<native function {self.name}>"


# ---------------------------------------------------------------------------
# Value formatting helpers (mimic JS console.log / String() output)
# ---------------------------------------------------------------------------

def js_typeof(val):
    if val is UNDEFINED:
        return "undefined"
    if val is None:
        return "object"  # typeof null === 'object' in JS (famous quirk)
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, (JSFunction, NativeFunction)):
        return "function"
    return "object"


def js_to_string(val):
    """Mimics JS String(val) / template literal stringification."""
    if val is UNDEFINED:
        return "undefined"
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float):
        if val == int(val) and not math.isinf(val) and not math.isnan(val):
            return str(int(val))
        if math.isnan(val):
            return "NaN"
        if math.isinf(val):
            return "Infinity" if val > 0 else "-Infinity"
        return repr(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return ",".join(js_to_string(x) for x in val)
    if isinstance(val, dict):
        return "[object Object]"
    if isinstance(val, (JSFunction, NativeFunction)):
        return f"function {getattr(val, 'name', '') or ''}() {{ ... }}"
    return str(val)


def js_console_log_format(val):
    """console.log formats objects/arrays differently from String(): uses JSON-ish form."""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "[ " + ", ".join(js_inspect(x) for x in val) + " ]" if val else "[]"
    if isinstance(val, dict):
        if not val:
            return "{}"
        parts = []
        for k, v in val.items():
            parts.append(f"{k}: {js_inspect(v)}")
        return "{ " + ", ".join(parts) + " }"
    return js_to_string(val)


def js_inspect(val):
    """Used for nested values inside arrays/objects when printed."""
    if isinstance(val, str):
        return f"'{val}'"
    if isinstance(val, list):
        return "[ " + ", ".join(js_inspect(x) for x in val) + " ]" if val else "[]"
    if isinstance(val, dict):
        if not val:
            return "{}"
        parts = [f"{k}: {js_inspect(v)}" for k, v in val.items()]
        return "{ " + ", ".join(parts) + " }"
    return js_to_string(val)


def js_truthy(val):
    if val is UNDEFINED or val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0 and not (isinstance(val, float) and math.isnan(val))
    if isinstance(val, str):
        return len(val) > 0
    return True  # objects, arrays, functions are always truthy


def js_to_number(val):
    if val is UNDEFINED:
        return float("nan")
    if val is None:
        return 0
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        s = val.strip()
        if s == "":
            return 0
        try:
            if "." in s or "e" in s.lower():
                return float(s)
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return float("nan")
    if isinstance(val, list):
        if len(val) == 0:
            return 0
        if len(val) == 1:
            return js_to_number(val[0])
        return float("nan")
    return float("nan")


def normalize_number(n):
    """Keep ints as ints, floats as floats (mirrors JS number display rules)."""
    if isinstance(n, float) and n.is_integer() and not math.isinf(n) and not math.isnan(n):
        # Only collapse to int representation for display; arithmetic stays float-safe
        return n
    return n


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------

class Interpreter:
    def __init__(self):
        self.global_env = Environment()
        self.output_lines = []
        self._setup_globals()

    # ---------------- Setup builtins ----------------

    def _setup_globals(self):
        g = self.global_env
        g.declare("undefined", UNDEFINED)
        g.declare("NaN", float("nan"))
        g.declare("Infinity", float("inf"))

        # console object
        console = {
            "log": NativeFunction(self._console_log, "log"),
            "error": NativeFunction(self._console_log, "error"),
            "warn": NativeFunction(self._console_log, "warn"),
            "info": NativeFunction(self._console_log, "info"),
        }
        g.declare("console", console)

        # Math object
        math_obj = {
            "PI": math.pi,
            "E": math.e,
            "abs": NativeFunction(lambda x: abs(js_to_number(x)), "abs"),
            "floor": NativeFunction(lambda x: math.floor(js_to_number(x)), "floor"),
            "ceil": NativeFunction(lambda x: math.ceil(js_to_number(x)), "ceil"),
            "round": NativeFunction(self._math_round, "round"),
            "trunc": NativeFunction(lambda x: math.trunc(js_to_number(x)), "trunc"),
            "sqrt": NativeFunction(lambda x: math.sqrt(js_to_number(x)), "sqrt"),
            "cbrt": NativeFunction(lambda x: (js_to_number(x)) ** (1 / 3), "cbrt"),
            "pow": NativeFunction(lambda x, y: js_to_number(x) ** js_to_number(y), "pow"),
            "max": NativeFunction(lambda *args: max((js_to_number(a) for a in args), default=float("-inf")), "max"),
            "min": NativeFunction(lambda *args: min((js_to_number(a) for a in args), default=float("inf")), "min"),
            "random": NativeFunction(lambda: random.random(), "random"),
            "sign": NativeFunction(lambda x: (0 if js_to_number(x) == 0 else (1 if js_to_number(x) > 0 else -1)), "sign"),
            "log": NativeFunction(lambda x: math.log(js_to_number(x)), "log"),
            "log2": NativeFunction(lambda x: math.log2(js_to_number(x)), "log2"),
            "log10": NativeFunction(lambda x: math.log10(js_to_number(x)), "log10"),
            "exp": NativeFunction(lambda x: math.exp(js_to_number(x)), "exp"),
            "sin": NativeFunction(lambda x: math.sin(js_to_number(x)), "sin"),
            "cos": NativeFunction(lambda x: math.cos(js_to_number(x)), "cos"),
            "tan": NativeFunction(lambda x: math.tan(js_to_number(x)), "tan"),
            "hypot": NativeFunction(lambda *args: math.hypot(*[js_to_number(a) for a in args]), "hypot"),
        }
        g.declare("Math", math_obj)

        # JSON object
        json_obj = {
            "stringify": NativeFunction(self._json_stringify, "stringify"),
            "parse": NativeFunction(self._json_parse, "parse"),
        }
        g.declare("JSON", json_obj)

        # Object static methods
        object_ctor = NativeFunction(lambda *a: {}, "Object")
        object_ctor_dict = {
            "keys": NativeFunction(lambda obj: list(obj.keys()) if isinstance(obj, dict) else
                                    [str(i) for i in range(len(obj))], "keys"),
            "values": NativeFunction(lambda obj: list(obj.values()) if isinstance(obj, dict) else list(obj), "values"),
            "entries": NativeFunction(self._object_entries, "entries"),
            "assign": NativeFunction(self._object_assign, "assign"),
            "freeze": NativeFunction(lambda obj: obj, "freeze"),
            "fromEntries": NativeFunction(self._object_from_entries, "fromEntries"),
        }
        g.declare("Object", object_ctor_dict)

        # Array static methods
        array_obj = {
            "isArray": NativeFunction(lambda v: isinstance(v, list), "isArray"),
            "from": NativeFunction(self._array_from, "from"),
            "of": NativeFunction(lambda *args: list(args), "of"),
        }
        g.declare("Array", array_obj)

        # Number static
        number_obj = {
            "isInteger": NativeFunction(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer(), "isInteger"),
            "isFinite": NativeFunction(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v), "isFinite"),
            "isNaN": NativeFunction(lambda v: isinstance(v, float) and math.isnan(v), "isNaN"),
            "parseFloat": NativeFunction(self._parse_float, "parseFloat"),
            "parseInt": NativeFunction(self._parse_int, "parseInt"),
            "MAX_SAFE_INTEGER": 9007199254740991,
            "MIN_SAFE_INTEGER": -9007199254740991,
            "POSITIVE_INFINITY": float("inf"),
            "NEGATIVE_INFINITY": float("-inf"),
            "EPSILON": 2.220446049250313e-16,
        }
        g.declare("Number", number_obj)

        # String constructor (callable + namespace not really needed but add as func)
        g.declare("String", NativeFunction(lambda v=UNDEFINED: js_to_string(v) if v is not UNDEFINED else "", "String"))
        g.declare("Boolean", NativeFunction(lambda v=UNDEFINED: js_truthy(v), "Boolean"))
        g.declare("Number_fn", NativeFunction(lambda v=UNDEFINED: js_to_number(v) if v is not UNDEFINED else 0, "Number"))
        # Allow Number(x) call too - override Number identifier carefully:
        # We keep Number as dict above for Number.isInteger etc., but also need Number(x) callable.
        # Solution: make Number object callable-like by also supporting Call on dict via special-case in Call eval.

        # global functions
        g.declare("parseInt", NativeFunction(self._parse_int, "parseInt"))
        g.declare("parseFloat", NativeFunction(self._parse_float, "parseFloat"))
        g.declare("isNaN", NativeFunction(lambda v: math.isnan(js_to_number(v)) if isinstance(js_to_number(v), float) else False, "isNaN"))
        g.declare("isFinite", NativeFunction(lambda v: math.isfinite(js_to_number(v)), "isFinite"))

        # Date (minimal)
        g.declare("Date", NativeFunction(self._date_ctor, "Date"))

        # prompt() - terminal se input leta hai (browser ka alert/prompt simulate)
        def _prompt(msg=UNDEFINED):
            # pehle pending console.log output flush karo
            if self.output_lines:
                print("\n".join(self.output_lines), flush=True)
                self.output_lines = []
            # ab prompt message same line pe dikhao aur input lo
            prompt_msg = (js_to_string(msg) + " ") if msg is not UNDEFINED else ""
            try:
                return input(prompt_msg)
            except EOFError:
                return ""
        g.declare("prompt", NativeFunction(_prompt, "prompt"))

        # alert() - console pe print karta hai
        g.declare("alert", NativeFunction(lambda msg=UNDEFINED: (
            print(js_to_string(msg) if msg is not UNDEFINED else "")
        ), "alert"))

    # ---------------- Builtin implementations ----------------

    def _console_log(self, *args):
        line = " ".join(js_console_log_format(a) for a in args)
        self.output_lines.append(line)
        return UNDEFINED

    def _math_round(self, x):
        n = js_to_number(x)
        # JS Math.round rounds .5 toward +Infinity (unlike Python's banker's rounding)
        return math.floor(n + 0.5)

    def _parse_int(self, val, radix=UNDEFINED):
        s = js_to_string(val).strip()
        base = 10
        if radix is not UNDEFINED and js_to_number(radix) != 0:
            base = int(js_to_number(radix))
        # extract leading sign + valid digits for the base
        import re
        m = re.match(r"^[+-]?0[xX][0-9a-fA-F]+", s) if base == 16 or base == 0 else None
        try:
            if base == 16 and (s.lower().startswith("0x") or s.lower().startswith("-0x") or s.lower().startswith("+0x")):
                return int(s, 16)
            # generic: find longest valid prefix
            valid_chars = "0123456789abcdefghijklmnopqrstuvwxyz"[:base]
            sign = 1
            i = 0
            if i < len(s) and s[i] in "+-":
                sign = -1 if s[i] == "-" else 1
                i += 1
            j = i
            while j < len(s) and s[j].lower() in valid_chars:
                j += 1
            if j == i:
                return float("nan")
            return sign * int(s[i:j], base)
        except Exception:
            return float("nan")

    def _parse_float(self, val):
        s = js_to_string(val).strip()
        import re
        m = re.match(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", s)
        if not m or m.group(0) == "":
            return float("nan")
        try:
            return float(m.group(0))
        except ValueError:
            return float("nan")

    def _json_stringify(self, val, *_):
        return self._json_str(val)

    def _json_str(self, val, indent=0):
        if val is UNDEFINED:
            return "null"  # actually undefined in array becomes null, top-level undefined -> handled separately
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, (int, float)):
            return js_to_string(val)
        if isinstance(val, str):
            return self._json_escape(val)
        if isinstance(val, list):
            return "[" + ",".join(self._json_str(v) for v in val) + "]"
        if isinstance(val, dict):
            items = []
            for k, v in val.items():
                items.append(f'{self._json_escape(str(k))}:{self._json_str(v)}')
            return "{" + ",".join(items) + "}"
        return "null"

    def _json_escape(self, s):
        out = ['"']
        for ch in s:
            if ch == '"':
                out.append('\\"')
            elif ch == "\\":
                out.append("\\\\")
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        out.append('"')
        return "".join(out)

    def _json_parse(self, s, *_):
        import json
        return json.loads(js_to_string(s))

    def _object_entries(self, obj):
        if isinstance(obj, dict):
            return [[k, v] for k, v in obj.items()]
        return [[str(i), v] for i, v in enumerate(obj)]

    def _object_assign(self, target, *sources):
        for src in sources:
            if isinstance(src, dict):
                target.update(src)
        return target

    def _object_from_entries(self, entries):
        result = {}
        for pair in entries:
            result[js_to_string(pair[0])] = pair[1]
        return result

    def _array_from(self, iterable, map_fn=UNDEFINED):
        if isinstance(iterable, dict):
            if "length" in iterable:
                length = int(js_to_number(iterable["length"]))
                result = [UNDEFINED] * length
            else:
                result = list(iterable.values())
        elif isinstance(iterable, str):
            result = list(iterable)
        elif isinstance(iterable, list):
            result = list(iterable)
        else:
            result = []
        if map_fn is not UNDEFINED and callable_js(map_fn):
            result = [self.call_function(map_fn, [v, i]) for i, v in enumerate(result)]
        return result

    def _date_ctor(self, *args):
        # Minimal Date: returns a dict-like object with getTime, toISOString, etc.
        now = datetime.datetime.now()
        d = {
            "_ts": time.time() * 1000,
            "getTime": NativeFunction(lambda: time.time() * 1000, "getTime"),
            "getFullYear": NativeFunction(lambda: now.year, "getFullYear"),
            "getMonth": NativeFunction(lambda: now.month - 1, "getMonth"),
            "getDate": NativeFunction(lambda: now.day, "getDate"),
            "toISOString": NativeFunction(lambda: now.isoformat() + "Z", "toISOString"),
        }
        return d

    # ---------------- Program execution ----------------

    def run(self, source_or_ast):
        from .parser import parse
        if isinstance(source_or_ast, str):
            ast = parse(source_or_ast)
        else:
            ast = source_or_ast
        self.exec_block_statements(ast.body, self.global_env)
        return "\n".join(self.output_lines)

    # ---------------- Statement execution ----------------

    def exec_block_statements(self, statements, env):
        # Hoist function declarations so they can be called before their
        # textual position (matches JS function-declaration hoisting).
        for stmt in statements:
            if stmt.type == "FunctionDecl":
                env.declare(stmt.name, JSFunction(stmt.name, stmt.params, stmt.body, env))
        for stmt in statements:
            if stmt.type != "FunctionDecl":
                self.exec_statement(stmt, env)

    def exec_statement(self, node, env):
        method = getattr(self, f"exec_{node.type}", None)
        if method is None:
            raise JSThrow(f"Unsupported statement type: {node.type}")
        try:
            return method(node, env)
        except JSThrow as e:
            msg = str(e.value)
            if "line" not in msg.lower() and hasattr(node, "line") and node.line:
                raise JSThrow(f"{msg} at line {node.line}")
            raise

    def exec_Program(self, node, env):
        self.exec_block_statements(node.body, env)

    def exec_Block(self, node, env):
        block_env = Environment(env)
        self.exec_block_statements(node.body, block_env)

    def exec_Empty(self, node, env):
        pass

    def exec_ExpressionStatement(self, node, env):
        self.evaluate(node.expr, env)

    def exec_VarDecl(self, node, env):
        for name, init_expr in node.declarations:
            value = self.evaluate(init_expr, env) if init_expr is not None else UNDEFINED
            env.declare(name, value)

    def exec_FunctionDecl(self, node, env):
        # already hoisted in exec_block_statements, but handle direct calls too
        if node.name not in env.vars:
            env.declare(node.name, JSFunction(node.name, node.params, node.body, env))

    def exec_Return(self, node, env):
        value = self.evaluate(node.value, env) if node.value is not None else UNDEFINED
        raise ReturnSignal(value)

    def exec_Break(self, node, env):
        raise BreakSignal()

    def exec_Continue(self, node, env):
        raise ContinueSignal()

    def exec_If(self, node, env):
        if js_truthy(self.evaluate(node.cond, env)):
            self.exec_statement(node.then, env)
        elif node.otherwise is not None:
            self.exec_statement(node.otherwise, env)

    def exec_While(self, node, env):
        while js_truthy(self.evaluate(node.cond, env)):
            try:
                self.exec_statement(node.body, Environment(env))
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def exec_DoWhile(self, node, env):
        while True:
            try:
                self.exec_statement(node.body, Environment(env))
            except BreakSignal:
                break
            except ContinueSignal:
                pass
            if not js_truthy(self.evaluate(node.cond, env)):
                break

    def exec_For(self, node, env):
        for_env = Environment(env)
        if node.init is not None:
            if node.init.type == "VarDecl":
                self.exec_VarDecl(node.init, for_env)
            else:
                self.exec_statement(node.init, for_env)
        while node.cond is None or js_truthy(self.evaluate(node.cond, for_env)):
            iter_env = Environment(for_env)
            try:
                self.exec_statement(node.body, iter_env)
            except BreakSignal:
                break
            except ContinueSignal:
                pass
            if node.update is not None:
                self.evaluate(node.update, for_env)

    def exec_ForOf(self, node, env):
        iterable = self.evaluate(node.iterable, env)
        items = self._iterate(iterable)
        for item in items:
            iter_env = Environment(env)
            self._bind_for_target(node.left, item, iter_env)
            try:
                self.exec_statement(node.body, iter_env)
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def exec_ForIn(self, node, env):
        iterable = self.evaluate(node.iterable, env)
        if isinstance(iterable, dict):
            keys = list(iterable.keys())
        elif isinstance(iterable, list):
            keys = [str(i) for i in range(len(iterable))]
        elif isinstance(iterable, str):
            keys = [str(i) for i in range(len(iterable))]
        else:
            keys = []
        for key in keys:
            iter_env = Environment(env)
            self._bind_for_target(node.left, key, iter_env)
            try:
                self.exec_statement(node.body, iter_env)
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def _bind_for_target(self, left_node, value, env):
        if left_node.type == "VarDecl":
            name = left_node.declarations[0][0]
            env.declare(name, value)
        elif left_node.type == "ExpressionStatement":
            self.assign_to_target(left_node.expr, value, env)

    def _iterate(self, val):
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return list(val)
        if isinstance(val, dict):
            if "_entries_iter" in val:
                return val["_entries_iter"]
            return list(val.values())
        return []

    def exec_Switch(self, node, env):
        disc_val = self.evaluate(node.discriminant, env)
        switch_env = Environment(env)
        matched = False
        try:
            for case in node.cases:
                if not matched:
                    if case["test"] is None:
                        continue  # skip default until no match found in first pass
                    test_val = self.evaluate(case["test"], switch_env)
                    if strict_equals(disc_val, test_val):
                        matched = True
                if matched:
                    for stmt in case["body"]:
                        self.exec_statement(stmt, switch_env)
            if not matched:
                # second pass: run default and everything after it
                run = False
                for case in node.cases:
                    if case["test"] is None:
                        run = True
                    if run:
                        for stmt in case["body"]:
                            self.exec_statement(stmt, switch_env)
        except BreakSignal:
            pass

    # ---------------- Expression evaluation ----------------

    def evaluate(self, node, env):
        method = getattr(self, f"eval_{node.type}", None)
        if method is None:
            raise JSThrow(f"Unsupported expression type: {node.type}")
        try:
            return method(node, env)
        except JSThrow as e:
            # Agar error mein line number nahi hai, to node ki line add karo
            msg = str(e.value)
            if "line" not in msg.lower() and hasattr(node, "line") and node.line:
                raise JSThrow(f"{msg} (at line {node.line})")
            raise

    def eval_Literal(self, node, env):
        return node.value

    def eval_Identifier(self, node, env):
        if node.name == "undefined":
            return UNDEFINED
        try:
            return env.get(node.name)
        except JSThrow as e:
            msg = str(e.value)
            line = getattr(node, "line", 0)
            if line and "line" not in msg.lower():
                raise JSThrow(f"{msg} at line {line}")
            raise

    def eval_This(self, node, env):
        try:
            return env.get("this")
        except JSThrow:
            return UNDEFINED

    def eval_Template(self, node, env):
        parts = []
        for kind, content in node.parts:
            if kind == "str":
                parts.append(content)
            else:
                val = self.evaluate(content, env)
                parts.append(js_to_string(val))
        return "".join(parts)

    def eval_ArrayLiteral(self, node, env):
        result = []
        for el in node.elements:
            if el.type == "Spread":
                spread_val = self.evaluate(el.value, env)
                result.extend(self._iterate(spread_val))
            else:
                result.append(self.evaluate(el, env))
        return result

    def eval_ObjectLiteral(self, node, env):
        result = {}
        for prop in node.properties:
            if prop["type"] == "spread":
                spread_val = self.evaluate(prop["value"], env)
                if isinstance(spread_val, dict):
                    result.update(spread_val)
            elif prop["type"] == "computed":
                key = js_to_string(self.evaluate(prop["key"], env))
                result[key] = self.evaluate(prop["value"], env)
            else:
                key = prop["key"]
                value = self.evaluate(prop["value"], env)
                if isinstance(value, (JSFunction,)) and value.this_val is None:
                    pass
                result[key] = value
        return result

    def eval_FunctionExpr(self, node, env):
        return JSFunction(node.name, node.params, node.body, env)

    def eval_ArrowFunction(self, node, env):
        this_val = None
        try:
            this_val = env.get("this")
        except JSThrow:
            this_val = None
        return JSFunction(None, node.params, node.body, env, expr_body=node.expr_body, this_val=this_val)

    def eval_Sequence(self, node, env):
        self.evaluate(node.left, env)
        return self.evaluate(node.right, env)

    def eval_Conditional(self, node, env):
        if js_truthy(self.evaluate(node.test, env)):
            return self.evaluate(node.consequent, env)
        return self.evaluate(node.alternate, env)

    def eval_Logical(self, node, env):
        left = self.evaluate(node.left, env)
        if node.op == "&&":
            if not js_truthy(left):
                return left
            return self.evaluate(node.right, env)
        if node.op == "||":
            if js_truthy(left):
                return left
            return self.evaluate(node.right, env)
        if node.op == "??":
            if left is not UNDEFINED and left is not None:
                return left
            return self.evaluate(node.right, env)

    def eval_Unary(self, node, env):
        if node.op == "typeof":
            try:
                val = self.evaluate(node.operand, env)
            except JSThrow:
                return "undefined"
            return js_typeof(val)
        if node.op == "delete":
            if node.operand.type == "Member":
                obj = self.evaluate(node.operand.obj, env)
                if node.operand.computed:
                    key = self.evaluate(node.operand.prop, env)
                else:
                    key = node.operand.prop.value
                if isinstance(obj, dict):
                    key_s = js_to_string(key) if not isinstance(key, str) else key
                    obj.pop(key_s, None)
                    return True
                if isinstance(obj, list):
                    idx = int(js_to_number(key))
                    if 0 <= idx < len(obj):
                        obj[idx] = UNDEFINED
                    return True
            return True

        val = self.evaluate(node.operand, env)
        if node.op == "-":
            return -js_to_number(val)
        if node.op == "+":
            return js_to_number(val)
        if node.op == "!":
            return not js_truthy(val)
        if node.op == "~":
            return ~int(js_to_number(val))

    def eval_UpdateExpression(self, node, env):
        old_val = js_to_number(self.evaluate(node.operand, env))
        new_val = old_val + 1 if node.op == "++" else old_val - 1
        self.assign_to_target(node.operand, new_val, env)
        return new_val if node.prefix else old_val

    def eval_Binary(self, node, env):
        left = self.evaluate(node.left, env)
        right = self.evaluate(node.right, env)
        return apply_binary_op(node.op, left, right)

    def eval_Assign(self, node, env):
        if node.op == "=":
            value = self.evaluate(node.value, env)
        else:
            current = self.evaluate(node.target, env)
            rhs = self.evaluate(node.value, env)
            op = node.op[:-1]  # strip trailing '='
            value = apply_binary_op(op, current, rhs)
        self.assign_to_target(node.target, value, env)
        return value

    def assign_to_target(self, target, value, env):
        if target.type == "Identifier":
            env.set(target.name, value)
        elif target.type == "Member":
            obj = self.evaluate(target.obj, env)
            if target.computed:
                key = self.evaluate(target.prop, env)
            else:
                key = target.prop.value
            if isinstance(obj, list):
                idx = key
                if isinstance(idx, str):
                    idx = int(js_to_number(idx))
                idx = int(idx)
                while len(obj) <= idx:
                    obj.append(UNDEFINED)
                obj[idx] = value
            elif isinstance(obj, dict):
                key_s = key if isinstance(key, str) else js_to_string(key)
                obj[key_s] = value
            else:
                raise JSThrow("TypeError: cannot set property on non-object")
        elif target.type == "ArrayLiteral":
            # array destructuring: [a, b] = [1, 2]
            values = self._iterate(value)
            for i, el in enumerate(target.elements):
                if el.type == "Spread":
                    self.assign_to_target(el.value, values[i:], env)
                    break
                v = values[i] if i < len(values) else UNDEFINED
                self.assign_to_target(el, v, env)
        elif target.type == "ObjectLiteral":
            for prop in target.properties:
                key = prop["key"]
                v = value.get(key, UNDEFINED) if isinstance(value, dict) else UNDEFINED
                self.assign_to_target(prop["value"], v, env)
        else:
            raise JSThrow(f"Invalid assignment target: {target.type}")

    def eval_Member(self, node, env):
        obj = self.evaluate(node.obj, env)
        if node.computed:
            key = self.evaluate(node.prop, env)
        else:
            key = node.prop.value
        return self.get_member(obj, key)

    def get_member(self, obj, key):
        # Handle "length" and array/string methods/properties
        if isinstance(obj, str):
            return self._string_member(obj, key)
        if isinstance(obj, list):
            return self._array_member(obj, key)
        if isinstance(obj, dict):
            key_s = key if isinstance(key, str) else js_to_string(key)
            if key_s in obj:
                return obj[key_s]
            # also check Object dunder helper methods like hasOwnProperty
            if key_s == "hasOwnProperty":
                return NativeFunction(lambda k: js_to_string(k) in obj, "hasOwnProperty")
            return UNDEFINED
        if obj is UNDEFINED or obj is None:
            raise JSThrow(f"TypeError: Cannot read properties of {js_to_string(obj)} (reading '{key}')")
        if isinstance(obj, (int, float)):
            return self._number_member(obj, key)
        if isinstance(obj, bool):
            return UNDEFINED
        return UNDEFINED

    # ---- string members/methods ----
    def _string_member(self, s, key):
        if key == "length":
            return len(s)
        if isinstance(key, (int,)) or (isinstance(key, str) and key.lstrip("-").isdigit()):
            idx = int(key)
            if 0 <= idx < len(s):
                return s[idx]
            return UNDEFINED
        methods = {
            "toUpperCase": lambda: s.upper(),
            "toLowerCase": lambda: s.lower(),
            "trim": lambda: s.strip(),
            "trimStart": lambda: s.lstrip(),
            "trimEnd": lambda: s.rstrip(),
            "charAt": lambda i=0: s[int(js_to_number(i))] if 0 <= int(js_to_number(i)) < len(s) else "",
            "charCodeAt": lambda i=0: ord(s[int(js_to_number(i))]) if 0 <= int(js_to_number(i)) < len(s) else float("nan"),
            "indexOf": lambda sub, start=0: s.find(sub, int(js_to_number(start))),
            "lastIndexOf": lambda sub: s.rfind(sub),
            "includes": lambda sub: sub in s,
            "startsWith": lambda sub, pos=0: s[int(js_to_number(pos)):].startswith(sub),
            "endsWith": lambda sub: s.endswith(sub),
            "slice": lambda *a: self._js_slice(s, a),
            "substring": lambda *a: self._js_substring(s, a),
            "substr": lambda *a: self._js_substr(s, a),
            "split": lambda sep=UNDEFINED, limit=UNDEFINED: self._string_split(s, sep, limit),
            "replace": lambda pat, repl: self._string_replace(s, pat, repl, all_=False),
            "replaceAll": lambda pat, repl: self._string_replace(s, pat, repl, all_=True),
            "concat": lambda *a: s + "".join(js_to_string(x) for x in a),
            "repeat": lambda n: s * int(js_to_number(n)),
            "padStart": lambda n, pad=" ": self._pad(s, n, pad, start=True),
            "padEnd": lambda n, pad=" ": self._pad(s, n, pad, start=False),
            "at": lambda i: (s[int(js_to_number(i))] if -len(s) <= int(js_to_number(i)) < len(s) else UNDEFINED),
            "toString": lambda: s,
            "valueOf": lambda: s,
            "match": lambda pat: self._string_match(s, pat),
            "normalize": lambda *a: s,
            "codePointAt": lambda i=0: ord(s[int(js_to_number(i))]) if 0 <= int(js_to_number(i)) < len(s) else UNDEFINED,
        }
        if key in methods:
            return NativeFunction(methods[key], key)
        return UNDEFINED

    def _pad(self, s, n, pad, start):
        n = int(js_to_number(n))
        pad = js_to_string(pad) or " "
        if len(s) >= n:
            return s
        needed = n - len(s)
        full_pad = (pad * (needed // len(pad) + 1))[:needed]
        return (full_pad + s) if start else (s + full_pad)

    def _js_slice(self, seq, args):
        length = len(seq)
        start = int(js_to_number(args[0])) if len(args) > 0 and args[0] is not UNDEFINED else 0
        end = int(js_to_number(args[1])) if len(args) > 1 and args[1] is not UNDEFINED else length
        if start < 0:
            start = max(length + start, 0)
        if end < 0:
            end = max(length + end, 0)
        start = min(start, length)
        end = min(end, length)
        if start >= end:
            return seq[0:0]
        return seq[start:end]

    def _js_substring(self, s, args):
        length = len(s)
        a = int(js_to_number(args[0])) if len(args) > 0 and args[0] is not UNDEFINED else 0
        b = int(js_to_number(args[1])) if len(args) > 1 and args[1] is not UNDEFINED else length
        a = max(0, min(a, length))
        b = max(0, min(b, length))
        if a > b:
            a, b = b, a
        return s[a:b]

    def _js_substr(self, s, args):
        length = len(s)
        start = int(js_to_number(args[0])) if len(args) > 0 else 0
        if start < 0:
            start = max(length + start, 0)
        count = int(js_to_number(args[1])) if len(args) > 1 and args[1] is not UNDEFINED else length - start
        return s[start:start + max(count, 0)]

    def _string_split(self, s, sep, limit):
        if sep is UNDEFINED:
            result = [s]
        elif sep == "":
            result = list(s)
        else:
            result = s.split(sep)
        if limit is not UNDEFINED:
            result = result[:int(js_to_number(limit))]
        return result

    def _string_replace(self, s, pat, repl, all_):
        if isinstance(repl, (JSFunction, NativeFunction)):
            if all_:
                # naive global replace with callback
                out = []
                idx = 0
                while True:
                    pos = s.find(pat, idx)
                    if pos == -1:
                        out.append(s[idx:])
                        break
                    out.append(s[idx:pos])
                    out.append(js_to_string(self.call_function(repl, [pat, pos, s])))
                    idx = pos + len(pat) if len(pat) > 0 else pos + 1
                return "".join(out)
            else:
                pos = s.find(pat)
                if pos == -1:
                    return s
                replacement = js_to_string(self.call_function(repl, [pat, pos, s]))
                return s[:pos] + replacement + s[pos + len(pat):]
        repl_s = js_to_string(repl)
        if all_:
            return s.replace(pat, repl_s)
        return s.replace(pat, repl_s, 1)

    def _string_match(self, s, pat):
        return None  # regex not commonly needed for these test cases

    # ---- number members ----
    def _number_member(self, n, key):
        methods = {
            "toFixed": lambda digits=0: f"{n:.{int(js_to_number(digits))}f}",
            "toString": lambda radix=10: self._number_to_string(n, radix),
            "toPrecision": lambda p=None: js_to_string(n) if p is None else f"{n:.{int(js_to_number(p))}g}",
            "valueOf": lambda: n,
        }
        if key in methods:
            return NativeFunction(methods[key], key)
        return UNDEFINED

    def _number_to_string(self, n, radix=10):
        radix = int(js_to_number(radix))
        if radix == 10:
            return js_to_string(n)
        n_int = int(n)
        if n_int == 0:
            return "0"
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        neg = n_int < 0
        n_int = abs(n_int)
        out = []
        while n_int > 0:
            out.append(digits[n_int % radix])
            n_int //= radix
        if neg:
            out.append("-")
        return "".join(reversed(out))

    # ---- array members/methods ----
    def _array_member(self, arr, key):
        if key == "length":
            return len(arr)
        if isinstance(key, (int,)) or (isinstance(key, str) and key.lstrip("-").isdigit()):
            idx = int(key)
            if idx < 0:
                idx += len(arr)
            if 0 <= idx < len(arr):
                return arr[idx]
            return UNDEFINED

        methods = {
            "push": lambda *items: (arr.extend(items), len(arr))[1],
            "pop": lambda: arr.pop() if arr else UNDEFINED,
            "shift": lambda: arr.pop(0) if arr else UNDEFINED,
            "unshift": lambda *items: (arr.__setitem__(slice(0, 0), items), len(arr))[1],
            "slice": lambda *a: self._js_slice(arr, a),
            "splice": lambda *a: self._array_splice(arr, a),
            "concat": lambda *others: arr + [x for o in others for x in (o if isinstance(o, list) else [o])],
            "includes": lambda v: any(strict_equals(x, v) for x in arr),
            "indexOf": lambda v, start=0: self._array_index_of(arr, v, start),
            "lastIndexOf": lambda v: self._array_last_index_of(arr, v),
            "join": lambda sep=",": (sep if isinstance(sep, str) else js_to_string(sep)).join(
                "" if (x is UNDEFINED or x is None) else js_to_string(x) for x in arr) if arr or True else "",
            "reverse": lambda: (arr.reverse(), arr)[1],
            "sort": lambda cmp=UNDEFINED: self._array_sort(arr, cmp),
            "map": lambda fn: [self.call_function(fn, [v, i, arr]) for i, v in enumerate(arr)],
            "filter": lambda fn: [v for i, v in enumerate(arr) if js_truthy(self.call_function(fn, [v, i, arr]))],
            "forEach": lambda fn: self._array_for_each(arr, fn),
            "reduce": lambda fn, *init: self._array_reduce(arr, fn, init),
            "reduceRight": lambda fn, *init: self._array_reduce(list(reversed(arr)), fn, init),
            "find": lambda fn: next((v for i, v in enumerate(arr) if js_truthy(self.call_function(fn, [v, i, arr]))), UNDEFINED),
            "findIndex": lambda fn: next((i for i, v in enumerate(arr) if js_truthy(self.call_function(fn, [v, i, arr]))), -1),
            "findLast": lambda fn: next((v for i, v in reversed(list(enumerate(arr))) if js_truthy(self.call_function(fn, [v, i, arr]))), UNDEFINED),
            "some": lambda fn: any(js_truthy(self.call_function(fn, [v, i, arr])) for i, v in enumerate(arr)),
            "every": lambda fn: all(js_truthy(self.call_function(fn, [v, i, arr])) for i, v in enumerate(arr)),
            "flat": lambda depth=1: self._array_flat(arr, int(js_to_number(depth)) if depth is not UNDEFINED else 1),
            "flatMap": lambda fn: self._array_flat([self.call_function(fn, [v, i, arr]) for i, v in enumerate(arr)], 1),
            "fill": lambda val, *a: self._array_fill(arr, val, a),
            "keys": lambda: list(range(len(arr))),
            "entries": lambda: [[i, v] for i, v in enumerate(arr)],
            "values": lambda: list(arr),
            "at": lambda i: (arr[int(js_to_number(i))] if -len(arr) <= int(js_to_number(i)) < len(arr) else UNDEFINED),
            "toString": lambda: ",".join(js_to_string(x) for x in arr),
        }
        if key in methods:
            return NativeFunction(methods[key], key)
        return UNDEFINED

    def _array_index_of(self, arr, v, start=0):
        start = int(js_to_number(start)) if start is not UNDEFINED else 0
        if start < 0:
            start = max(0, len(arr) + start)
        for i in range(start, len(arr)):
            if strict_equals(arr[i], v):
                return i
        return -1

    def _array_last_index_of(self, arr, v):
        for i in range(len(arr) - 1, -1, -1):
            if strict_equals(arr[i], v):
                return i
        return -1

    def _array_splice(self, arr, args):
        length = len(arr)
        start = int(js_to_number(args[0])) if len(args) > 0 else 0
        if start < 0:
            start = max(length + start, 0)
        start = min(start, length)
        if len(args) > 1:
            delete_count = int(js_to_number(args[1]))
            delete_count = max(0, min(delete_count, length - start))
        else:
            delete_count = length - start
        removed = arr[start:start + delete_count]
        items = list(args[2:])
        arr[start:start + delete_count] = items
        return removed

    def _array_sort(self, arr, cmp):
        if cmp is UNDEFINED or cmp is None:
            # default JS sort: convert to strings and compare
            arr.sort(key=lambda x: js_to_string(x))
        else:
            import functools

            def comparator(a, b):
                result = self.call_function(cmp, [a, b])
                num = js_to_number(result)
                if num < 0:
                    return -1
                if num > 0:
                    return 1
                return 0
            arr.sort(key=functools.cmp_to_key(comparator))
        return arr

    def _array_for_each(self, arr, fn):
        for i, v in enumerate(arr):
            self.call_function(fn, [v, i, arr])
        return UNDEFINED

    def _array_reduce(self, arr, fn, init):
        if init:
            acc = init[0]
            start_idx = 0
        else:
            if not arr:
                raise JSThrow("TypeError: Reduce of empty array with no initial value")
            acc = arr[0]
            start_idx = 1
        for i in range(start_idx, len(arr)):
            acc = self.call_function(fn, [acc, arr[i], i, arr])
        return acc

    def _array_flat(self, arr, depth):
        if depth <= 0:
            return list(arr)
        result = []
        for x in arr:
            if isinstance(x, list):
                result.extend(self._array_flat(x, depth - 1))
            else:
                result.append(x)
        return result

    def _array_fill(self, arr, val, args):
        length = len(arr)
        start = int(js_to_number(args[0])) if len(args) > 0 else 0
        end = int(js_to_number(args[1])) if len(args) > 1 else length
        if start < 0:
            start += length
        if end < 0:
            end += length
        for i in range(max(0, start), min(length, end)):
            arr[i] = val
        return arr

    # ---------------- Function calls ----------------

    def eval_Call(self, node, env):
        # Determine `this` if calling a method (obj.method())
        this_val = UNDEFINED
        if node.callee.type == "Member":
            this_val = self.evaluate(node.callee.obj, env)
            if node.callee.computed:
                key = self.evaluate(node.callee.prop, env)
            else:
                key = node.callee.prop.value

            # Special-case Number(x) when callee is the 'Number' identifier handled elsewhere
            func = self.get_member(this_val, key)
        else:
            func = self.evaluate(node.callee, env)
            # special-case: Number(x), String(x), Boolean(x), Array(...) used as constructors/functions
            if node.callee.type == "Identifier" and node.callee.name == "Number":
                args = self._eval_args(node.arguments, env)
                return js_to_number(args[0]) if args else 0
            if node.callee.type == "Identifier" and node.callee.name == "Array" and not isinstance(func, dict):
                pass

        args = self._eval_args(node.arguments, env)

        if isinstance(func, dict) and node.callee.type == "Identifier" and node.callee.name == "Array":
            # Array(n) -> array of length n with undefined; Array(a,b,c) -> [a,b,c]
            if len(args) == 1 and isinstance(args[0], (int, float)):
                return [UNDEFINED] * int(args[0])
            return list(args)

        return self.call_function(func, args, this_val)

    def _eval_args(self, arg_nodes, env):
        args = []
        for a in arg_nodes:
            if a.type == "Spread":
                spread_val = self.evaluate(a.value, env)
                args.extend(self._iterate(spread_val))
            else:
                args.append(self.evaluate(a, env))
        return args

    def call_function(self, func, args, this_val=UNDEFINED):
        if isinstance(func, NativeFunction):
            return func(*args)

        if isinstance(func, JSFunction):
            call_env = Environment(func.closure_env)

            # `this` binding: arrow functions inherit enclosing `this`
            if func.this_val is not None:
                call_env.declare("this", func.this_val)
            elif this_val is not UNDEFINED:
                call_env.declare("this", this_val)
            else:
                call_env.declare("this", UNDEFINED)

            # bind parameters (supports defaults + rest params)
            for i, param in enumerate(func.params):
                if param["rest"]:
                    call_env.declare(param["name"], list(args[i:]))
                    break
                if i < len(args) and args[i] is not UNDEFINED:
                    call_env.declare(param["name"], args[i])
                elif param["default"] is not None:
                    call_env.declare(param["name"], self.evaluate(param["default"], call_env))
                elif i < len(args):
                    call_env.declare(param["name"], args[i])
                else:
                    call_env.declare(param["name"], UNDEFINED)

            # arguments object (array-like)
            call_env.declare("arguments", list(args))

            if func.expr_body:
                return self.evaluate(func.body, call_env)

            try:
                self.exec_block_statements(func.body.body, call_env)
            except ReturnSignal as r:
                return r.value
            return UNDEFINED

        raise JSThrow(f"TypeError: {js_to_string(func)} is not a function")

    def eval_New(self, node, env):
        # Minimal support: `new Array()`, `new Object()`, `new Date()`, user classes not required for tests
        if node.callee.type == "Identifier":
            name = node.callee.name
            args = self._eval_args(node.arguments, env)
            if name == "Array":
                if len(args) == 1 and isinstance(args[0], (int, float)):
                    return [UNDEFINED] * int(args[0])
                return list(args)
            if name == "Object":
                return {}
            if name == "Date":
                return self._date_ctor(*args)
        func = self.evaluate(node.callee, env)
        args = self._eval_args(node.arguments, env)
        if isinstance(func, JSFunction):
            instance = {}
            instance["__proto__"] = func
            call_env = Environment(func.closure_env)
            call_env.declare("this", instance)
            for i, param in enumerate(func.params):
                val = args[i] if i < len(args) else UNDEFINED
                call_env.declare(param["name"], val)
            try:
                self.exec_block_statements(func.body.body, call_env)
            except ReturnSignal as r:
                if isinstance(r.value, dict):
                    return r.value
            return instance
        raise JSThrow("TypeError: not a constructor")


def callable_js(val):
    return isinstance(val, (JSFunction, NativeFunction))


# ---------------------------------------------------------------------------
# Binary operators (with JS-style coercion rules)
# ---------------------------------------------------------------------------

def strict_equals(a, b):
    if a is UNDEFINED and b is UNDEFINED:
        return True
    if a is UNDEFINED or b is UNDEFINED:
        return False
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) == type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return a is b


def loose_equals(a, b):
    if (a is UNDEFINED or a is None) and (b is UNDEFINED or b is None):
        return True
    if (a is UNDEFINED or a is None) or (b is UNDEFINED or b is None):
        return False
    if type(a) == type(b):
        return strict_equals(a, b)
    # number/string coercion
    if isinstance(a, (int, float)) and isinstance(b, str):
        return a == js_to_number(b)
    if isinstance(a, str) and isinstance(b, (int, float)):
        return js_to_number(a) == b
    if isinstance(a, bool):
        return js_to_number(a) == js_to_number(b) if isinstance(b, (int, float)) else loose_equals(js_to_number(a), b)
    if isinstance(b, bool):
        return loose_equals(a, js_to_number(b))
    return a == b


def apply_binary_op(op, left, right):
    if op == "+":
        if isinstance(left, str) or isinstance(right, str):
            return js_to_string(left) + js_to_string(right)
        if isinstance(left, list) or isinstance(right, list) or isinstance(left, dict) or isinstance(right, dict):
            # JS object + anything -> string concatenation via toString
            if isinstance(left, (list, dict)) or isinstance(right, (list, dict)):
                return js_to_string(left) + js_to_string(right)
        ln, rn = js_to_number(left), js_to_number(right)
        return _norm_arith(ln + rn)
    if op == "-":
        return _norm_arith(js_to_number(left) - js_to_number(right))
    if op == "*":
        return _norm_arith(js_to_number(left) * js_to_number(right))
    if op == "/":
        r = js_to_number(right)
        l = js_to_number(left)
        if r == 0:
            if l == 0 or math.isnan(l):
                return float("nan")
            return float("inf") if (l > 0) == (not str(r).startswith("-")) else float("-inf")
        return _norm_arith(l / r)
    if op == "%":
        l, r = js_to_number(left), js_to_number(right)
        if r == 0:
            return float("nan")
        result = math.fmod(l, r)
        return _norm_arith(result)
    if op == "**":
        return _norm_arith(js_to_number(left) ** js_to_number(right))

    if op == "==":
        return loose_equals(left, right)
    if op == "!=":
        return not loose_equals(left, right)
    if op == "===":
        return strict_equals(left, right)
    if op == "!==":
        return not strict_equals(left, right)

    if op in ("<", ">", "<=", ">="):
        if isinstance(left, str) and isinstance(right, str):
            l, r = left, right
        else:
            l, r = js_to_number(left), js_to_number(right)
            if isinstance(l, float) and math.isnan(l):
                return False
            if isinstance(r, float) and math.isnan(r):
                return False
        if op == "<":
            return l < r
        if op == ">":
            return l > r
        if op == "<=":
            return l <= r
        if op == ">=":
            return l >= r

    if op == "&":
        return int(js_to_number(left)) & int(js_to_number(right))
    if op == "|":
        return int(js_to_number(left)) | int(js_to_number(right))
    if op == "^":
        return int(js_to_number(left)) ^ int(js_to_number(right))
    if op == "instanceof":
        return False  # minimal

    raise JSThrow(f"Unsupported operator: {op}")


def _norm_arith(n):
    """JS numbers are all doubles, but for clean output we keep ints as ints
    when the result is mathematically an integer (matches console.log output
    like '7' instead of '7.0')."""
    if isinstance(n, float):
        if math.isnan(n) or math.isinf(n):
            return n
        if n.is_integer():
            return int(n)
    return n