    # JS Runtime in Python — Thunder Hackathon 2.0

Ek mini JavaScript interpreter, pure Python mein likha hua. Koi exec() ya
eval() ka use nahi — sab kuch khud se Lexer -> Parser -> Interpreter
pipeline se chalta hai.

## Kaise chalayein

python main.py path/to/script.js \n  
python main.py -c "console.log(1+1)" \n
echo "console.log('hi')" | python3 main.py \ n 

## Architecture

jsinterp/
├── lexer.py       -> JS code ko tokens mein todta hai
├── ast_nodes.py   -> AST node ka generic representation
├── parser.py      -> Recursive descent parser (tokens -> AST)
└── interpreter.py -> Tree-walking interpreter (AST -> output)
main.py            -> CLI entry point

## Kaise kaam karta hai

1. LEXER   - Source code ko tokens mein todta hai
2. PARSER  - Tokens se AST (Abstract Syntax Tree) banata hai
3. INTERPRETER - AST ko walk karke execute karta hai

## Supported Features

- Variables: let, const, var
- Types: number, string, boolean, null, undefined, object, array, function
- Operators: arithmetic, comparison (==, ===), logical (&&, ||, ??),
  assignment (+=, -= etc.), spread/rest (...)
- Control flow: if/else, switch, for, for...of, for...in,
  while, do...while, break, continue
- Functions: declarations, expressions, arrow functions,
  closures, default params, rest params, callbacks
- Array methods: push, pop, shift, unshift, slice, splice,
  concat, includes, indexOf, sort, reverse, map, filter,
  reduce, find, some, every, flat
- String methods: replace, replaceAll, substring, slice, split,
  trim, toUpperCase, toLowerCase, includes, startsWith,
  endsWith, indexOf
- Math object: Math.floor, Math.ceil, Math.round, Math.random, etc.
- Template literals: `Hello ${name}`
- Type coercion: "5" - 2 = 3, 1 + "1" = "11"

## All 5 Test Cases Pass

TC1 - Odd/Even Checker      ✅
TC2 - Triangle Pattern       ✅
TC3 - Armstrong Number       ✅
TC4 - Array Reverse          ✅
TC5 - String Palindrome      ✅

## Chalane ka tarika

cd hackathon2.0
python main.py test.js