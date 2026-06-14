"""
PARSER (Recursive Descent)
---------------------------
Yeh module tokens lekar AST banata hai.

CONCEPT: Recursive Descent Parsing
Har grammar rule ke liye ek function. Operator precedence (kis operator ko
pehle evaluate karna hai) ko handle karne ke liye functions ek chain mein
call hote hain - lowest precedence (assignment, ternary) se shuru hoke
highest precedence (function calls, member access) tak.

Precedence chain (low -> high):
  assignment -> ternary -> logical_or -> logical_and -> equality ->
  relational -> additive -> multiplicative -> exponent -> unary -> postfix -> primary

JS Grammar (simplified) jo hum support kar rahe hain:
  Program        -> Statement*
  Statement      -> VarDecl | IfStmt | ForStmt | WhileStmt | DoWhileStmt |
                     FunctionDecl | ReturnStmt | BreakStmt | ContinueStmt |
                     SwitchStmt | Block | ExpressionStmt
  Expression     -> Assignment
  Assignment     -> Ternary ( ('=' | '+=' | '-=' | ...) Assignment )?
  ...
"""

from .lexer import Lexer, Token
from .ast_nodes import Node


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # ---------- helper methods ----------

    def peek(self, offset=0):
        return self.tokens[self.pos + offset]

    def current(self):
        return self.tokens[self.pos]

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def check_op(self, value, offset=0):
        tok = self.peek(offset)
        return tok.type == "OP" and tok.value == value

    def check_kw(self, value, offset=0):
        tok = self.peek(offset)
        return tok.type == "KEYWORD" and tok.value == value

    def expect_op(self, value):
        tok = self.current()
        if tok.type == "OP" and tok.value == value:
            return self.advance()
        raise SyntaxError(f"Expected '{value}' but got {tok} at line {tok.line}")

    def expect_kw(self, value):
        tok = self.current()
        if tok.type == "KEYWORD" and tok.value == value:
            return self.advance()
        raise SyntaxError(f"Expected keyword '{value}' but got {tok} at line {tok.line}")

    def expect_ident(self):
        tok = self.current()
        if tok.type == "IDENT":
            return self.advance()
        raise SyntaxError(f"Expected identifier but got {tok} at line {tok.line}")

    def skip_semi(self):
        # JS semicolons optional kaafi jagah - hum agar ho to skip kar dete hain
        if self.check_op(";"):
            self.advance()

    # ---------- program / statements ----------

    def parse_program(self):
        statements = []
        while self.current().type != "EOF":
            statements.append(self.parse_statement())
        return Node("Program", body=statements)

    def parse_statement(self):
        tok = self.current()

        if tok.type == "KEYWORD":
            if tok.value in ("let", "const", "var"):
                node = self.parse_var_decl()
                self.skip_semi()
                return node
            if tok.value == "function":
                return self.parse_function_decl()
            if tok.value == "if":
                return self.parse_if()
            if tok.value == "for":
                return self.parse_for()
            if tok.value == "while":
                return self.parse_while()
            if tok.value == "do":
                return self.parse_do_while()
            if tok.value == "return":
                self.advance()
                if self.check_op(";") or self.check_op("}"):
                    val = None
                else:
                    val = self.parse_expression()
                self.skip_semi()
                return Node("Return", value=val)
            if tok.value == "break":
                self.advance()
                self.skip_semi()
                return Node("Break")
            if tok.value == "continue":
                self.advance()
                self.skip_semi()
                return Node("Continue")
            if tok.value == "switch":
                return self.parse_switch()

        if self.check_op("{"):
            return self.parse_block()

        if self.check_op(";"):
            self.advance()
            return Node("Empty")

        # Expression statement
        expr = self.parse_expression()
        self.skip_semi()
        return Node("ExpressionStatement", expr=expr)

    def parse_block(self):
        self.expect_op("{")
        body = []
        while not self.check_op("}"):
            body.append(self.parse_statement())
        self.expect_op("}")
        return Node("Block", body=body)

    def parse_var_decl(self):
        kind = self.advance().value  # let/const/var
        declarations = []
        while True:
            name = self.expect_ident().value
            init = None
            if self.check_op("="):
                self.advance()
                init = self.parse_assignment()
            declarations.append((name, init))
            if self.check_op(","):
                self.advance()
                continue
            break
        return Node("VarDecl", kind=kind, declarations=declarations)

    def parse_function_decl(self):
        self.expect_kw("function")
        name = self.expect_ident().value
        params = self.parse_params()
        body = self.parse_block()
        return Node("FunctionDecl", name=name, params=params, body=body)

    def parse_params(self):
        self.expect_op("(")
        params = []
        while not self.check_op(")"):
            # rest parameter: ...args
            is_rest = False
            if self.check_op("..."):
                self.advance()
                is_rest = True
            pname = self.expect_ident().value
            default = None
            if self.check_op("="):
                self.advance()
                default = self.parse_assignment()
            params.append({"name": pname, "default": default, "rest": is_rest})
            if self.check_op(","):
                self.advance()
        self.expect_op(")")
        return params

    def parse_if(self):
        self.expect_kw("if")
        self.expect_op("(")
        cond = self.parse_expression()
        self.expect_op(")")
        then_branch = self.parse_statement()
        else_branch = None
        if self.check_kw("else"):
            self.advance()
            else_branch = self.parse_statement()
        return Node("If", cond=cond, then=then_branch, otherwise=else_branch)

    def parse_for(self):
        self.expect_kw("for")
        self.expect_op("(")

        # init
        if self.check_op(";"):
            init = None
            self.advance()
        else:
            if self.current().type == "KEYWORD" and self.current().value in ("let", "const", "var"):
                init = self.parse_var_decl()
            else:
                init = Node("ExpressionStatement", expr=self.parse_expression())

            # for...of / for...in
            if self.check_kw("of") or self.check_kw("in"):
                kind = self.advance().value
                iterable = self.parse_expression()
                self.expect_op(")")
                body = self.parse_statement()
                return Node("ForOf" if kind == "of" else "ForIn", left=init, iterable=iterable, body=body)

            self.expect_op(";")

        # condition
        if self.check_op(";"):
            cond = None
        else:
            cond = self.parse_expression()
        self.expect_op(";")

        # update
        if self.check_op(")"):
            update = None
        else:
            update = self.parse_expression()
        self.expect_op(")")

        body = self.parse_statement()
        return Node("For", init=init, cond=cond, update=update, body=body)

    def parse_while(self):
        self.expect_kw("while")
        self.expect_op("(")
        cond = self.parse_expression()
        self.expect_op(")")
        body = self.parse_statement()
        return Node("While", cond=cond, body=body)

    def parse_do_while(self):
        self.expect_kw("do")
        body = self.parse_statement()
        self.expect_kw("while")
        self.expect_op("(")
        cond = self.parse_expression()
        self.expect_op(")")
        self.skip_semi()
        return Node("DoWhile", cond=cond, body=body)

    def parse_switch(self):
        self.expect_kw("switch")
        self.expect_op("(")
        disc = self.parse_expression()
        self.expect_op(")")
        self.expect_op("{")
        cases = []
        while not self.check_op("}"):
            if self.check_kw("case"):
                self.advance()
                test = self.parse_expression()
                self.expect_op(":")
                body = []
                while not (self.check_kw("case") or self.check_kw("default") or self.check_op("}")):
                    body.append(self.parse_statement())
                cases.append({"test": test, "body": body})
            elif self.check_kw("default"):
                self.advance()
                self.expect_op(":")
                body = []
                while not (self.check_kw("case") or self.check_kw("default") or self.check_op("}")):
                    body.append(self.parse_statement())
                cases.append({"test": None, "body": body})
            else:
                raise SyntaxError(f"Unexpected token in switch: {self.current()}")
        self.expect_op("}")
        return Node("Switch", discriminant=disc, cases=cases)

    # ---------- expressions (operator precedence) ----------

    def parse_expression(self):
        # Handles comma operator at top-level expression context (rare in our test cases)
        expr = self.parse_assignment()
        while self.check_op(","):
            self.advance()
            right = self.parse_assignment()
            expr = Node("Sequence", left=expr, right=right)
        return expr

    ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "%=", "**="}

    def parse_assignment(self):
        left = self.parse_ternary()
        if self.current().type == "OP" and self.current().value in self.ASSIGN_OPS:
            op = self.advance().value
            right = self.parse_assignment()
            return Node("Assign", op=op, target=left, value=right)
        return left

    def parse_ternary(self):
        cond = self.parse_logical_or()
        if self.check_op("?"):
            self.advance()
            consequent = self.parse_assignment()
            self.expect_op(":")
            alternate = self.parse_assignment()
            return Node("Conditional", test=cond, consequent=consequent, alternate=alternate)
        return cond

    def parse_logical_or(self):
        left = self.parse_logical_and()
        while self.check_op("||") or self.check_op("??"):
            op = self.advance().value
            right = self.parse_logical_and()
            left = Node("Logical", op=op, left=left, right=right)
        return left

    def parse_logical_and(self):
        left = self.parse_equality()
        while self.check_op("&&"):
            op = self.advance().value
            right = self.parse_equality()
            left = Node("Logical", op=op, left=left, right=right)
        return left

    def parse_equality(self):
        left = self.parse_relational()
        while self.current().type == "OP" and self.current().value in ("==", "!=", "===", "!=="):
            op = self.advance().value
            right = self.parse_relational()
            left = Node("Binary", op=op, left=left, right=right)
        return left

    def parse_relational(self):
        left = self.parse_additive()
        while True:
            if self.current().type == "OP" and self.current().value in ("<", ">", "<=", ">="):
                op = self.advance().value
                right = self.parse_additive()
                left = Node("Binary", op=op, left=left, right=right)
            elif self.check_kw("instanceof"):
                self.advance()
                right = self.parse_additive()
                left = Node("Binary", op="instanceof", left=left, right=right)
            else:
                break
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.current().type == "OP" and self.current().value in ("+", "-"):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = Node("Binary", op=op, left=left, right=right)
        return left

    def parse_multiplicative(self):
        left = self.parse_exponent()
        while self.current().type == "OP" and self.current().value in ("*", "/", "%"):
            op = self.advance().value
            right = self.parse_exponent()
            left = Node("Binary", op=op, left=left, right=right)
        return left

    def parse_exponent(self):
        left = self.parse_unary()
        if self.check_op("**"):
            self.advance()
            right = self.parse_exponent()  # right-associative
            return Node("Binary", op="**", left=left, right=right)
        return left

    def parse_unary(self):
        tok = self.current()
        if tok.type == "OP" and tok.value in ("!", "-", "+", "~"):
            self.advance()
            operand = self.parse_unary()
            return Node("Unary", op=tok.value, operand=operand)
        if tok.type == "OP" and tok.value in ("++", "--"):
            self.advance()
            operand = self.parse_unary()
            return Node("UpdateExpression", op=tok.value, operand=operand, prefix=True)
        if tok.type == "KEYWORD" and tok.value == "typeof":
            self.advance()
            operand = self.parse_unary()
            return Node("Unary", op="typeof", operand=operand)
        if tok.type == "KEYWORD" and tok.value == "delete":
            self.advance()
            operand = self.parse_unary()
            return Node("Unary", op="delete", operand=operand)
        if tok.type == "KEYWORD" and tok.value == "new":
            self.advance()
            callee = self.parse_member_chain(self.parse_primary())
            args = []
            if self.check_op("("):
                args = self.parse_arguments()
            return Node("New", callee=callee, arguments=args)
        return self.parse_postfix()

    def parse_postfix(self):
        expr = self.parse_call_member()
        if self.current().type == "OP" and self.current().value in ("++", "--"):
            op = self.advance().value
            return Node("UpdateExpression", op=op, operand=expr, prefix=False)
        return expr

    def parse_call_member(self):
        expr = self.parse_primary()
        return self.parse_member_chain(expr)

    def parse_member_chain(self, expr):
        while True:
            if self.check_op("."):
                self.advance()
                prop = self.advance().value  # IDENT or keyword used as prop name
                expr = Node("Member", obj=expr, prop=Node("Literal", value=prop), computed=False)
            elif self.check_op("["):
                self.advance()
                prop = self.parse_expression()
                self.expect_op("]")
                expr = Node("Member", obj=expr, prop=prop, computed=True)
            elif self.check_op("("):
                args = self.parse_arguments()
                expr = Node("Call", callee=expr, arguments=args)
            else:
                break
        return expr

    def parse_arguments(self):
        self.expect_op("(")
        args = []
        while not self.check_op(")"):
            if self.check_op("..."):
                self.advance()
                args.append(Node("Spread", value=self.parse_assignment()))
            else:
                args.append(self.parse_assignment())
            if self.check_op(","):
                self.advance()
        self.expect_op(")")
        return args

    # ---------- primary expressions ----------

    def parse_primary(self):
        tok = self.current()

        if tok.type == "NUMBER":
            self.advance()
            return Node("Literal", value=tok.value)

        if tok.type == "STRING":
            self.advance()
            return Node("Literal", value=tok.value)

        if tok.type == "TEMPLATE":
            self.advance()
            parts = []
            for kind, content in tok.value:
                if kind == "str":
                    parts.append(("str", content))
                else:
                    sub_tokens = Lexer(content).tokenize()
                    sub_ast = Parser(sub_tokens).parse_expression()
                    parts.append(("expr", sub_ast))
            return Node("Template", parts=parts)

        if tok.type == "KEYWORD":
            if tok.value == "true":
                self.advance()
                return Node("Literal", value=True)
            if tok.value == "false":
                self.advance()
                return Node("Literal", value=False)
            if tok.value == "null":
                self.advance()
                return Node("Literal", value=None)
            if tok.value == "undefined":
                self.advance()
                return Node("Identifier", name="undefined")
            if tok.value == "this":
                self.advance()
                return Node("This")
            if tok.value == "function":
                return self.parse_function_expr()

        if tok.type == "IDENT":
            # could be arrow function: ident => ...
            if self.peek(1).type == "OP" and self.peek(1).value == "=>":
                self.advance()
                param_name = tok.value
                self.advance()  # =>
                return self.finish_arrow_function([{"name": param_name, "default": None, "rest": False}])
            self.advance()
            return Node("Identifier", name=tok.value)

        if self.check_op("("):
            # Could be: (expr) OR arrow function params (a, b) => ...
            if self._is_arrow_function_ahead():
                params = self.parse_params()
                self.expect_op("=>")
                return self.finish_arrow_function(params)
            self.advance()
            expr = self.parse_expression()
            self.expect_op(")")
            return expr

        if self.check_op("["):
            return self.parse_array_literal()

        if self.check_op("{"):
            return self.parse_object_literal()

        raise SyntaxError(f"Unexpected token in expression: {tok} at line {tok.line}")

    def _is_arrow_function_ahead(self):
        """Lookahead to check if '(' starts arrow function params by finding matching ')'
        and checking if '=>' follows."""
        depth = 0
        i = self.pos
        while i < len(self.tokens):
            t = self.tokens[i]
            if t.type == "OP" and t.value == "(":
                depth += 1
            elif t.type == "OP" and t.value == ")":
                depth -= 1
                if depth == 0:
                    nxt = self.tokens[i + 1] if i + 1 < len(self.tokens) else None
                    return nxt is not None and nxt.type == "OP" and nxt.value == "=>"
            i += 1
        return False

    def finish_arrow_function(self, params):
        if self.check_op("{"):
            body = self.parse_block()
            is_expr_body = False
        else:
            body = self.parse_assignment()
            is_expr_body = True
        return Node("ArrowFunction", params=params, body=body, expr_body=is_expr_body)

    def parse_function_expr(self):
        self.expect_kw("function")
        name = None
        if self.current().type == "IDENT":
            name = self.advance().value
        params = self.parse_params()
        body = self.parse_block()
        return Node("FunctionExpr", name=name, params=params, body=body)

    def parse_array_literal(self):
        self.expect_op("[")
        elements = []
        while not self.check_op("]"):
            if self.check_op(","):
                # elision (sparse array) - represent as undefined
                elements.append(Node("Identifier", name="undefined"))
                self.advance()
                continue
            if self.check_op("..."):
                self.advance()
                elements.append(Node("Spread", value=self.parse_assignment()))
            else:
                elements.append(self.parse_assignment())
            if self.check_op(","):
                self.advance()
        self.expect_op("]")
        return Node("ArrayLiteral", elements=elements)

    def parse_object_literal(self):
        self.expect_op("{")
        properties = []
        while not self.check_op("}"):
            if self.check_op("..."):
                self.advance()
                properties.append({"type": "spread", "value": self.parse_assignment()})
                if self.check_op(","):
                    self.advance()
                continue

            # computed key: [expr]: value
            if self.check_op("["):
                self.advance()
                key_expr = self.parse_expression()
                self.expect_op("]")
                self.expect_op(":")
                value = self.parse_assignment()
                properties.append({"type": "computed", "key": key_expr, "value": value})
                if self.check_op(","):
                    self.advance()
                continue

            # key: identifier, string, or number
            tok = self.current()
            if tok.type in ("IDENT", "KEYWORD"):
                key = self.advance().value
            elif tok.type == "STRING":
                key = self.advance().value
            elif tok.type == "NUMBER":
                key = str(self.advance().value)
            else:
                raise SyntaxError(f"Unexpected token in object literal: {tok}")

            # method shorthand: key(...) { ... }
            if self.check_op("("):
                params = self.parse_params()
                body = self.parse_block()
                value = Node("FunctionExpr", name=None, params=params, body=body)
                properties.append({"type": "normal", "key": key, "value": value})
            elif self.check_op(":"):
                self.advance()
                value = self.parse_assignment()
                properties.append({"type": "normal", "key": key, "value": value})
            else:
                # shorthand: { x } means { x: x }
                value = Node("Identifier", name=key)
                properties.append({"type": "normal", "key": key, "value": value})

            if self.check_op(","):
                self.advance()
        self.expect_op("}")
        return Node("ObjectLiteral", properties=properties)


def parse(source):
    tokens = Lexer(source).tokenize()
    return Parser(tokens).parse_program()
