from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ast_nodes import (
    ArrayIndex,
    Assert,
    Assign,
    Assume,
    BinaryOp,
    Block,
    Bool,
    Call,
    ErrorNode,
    Expr,
    Function,
    Ident,
    If,
    Int,
    Program,
    SourcePos,
    Stmt,
    UnaryOp,
    While,
)
from funnylex import DEFAULT_SPEC, build
from lexer import EOF_KIND, Lexer, Token


# ==================== МНОЖЕСТВА FIRST И FOLLOW (ДЛЯ ЗАЩИТЫ И ПАНИКИ) ====================

FIRST_SETS: Dict[str, Set[str]] = {
    "program": {"FUNCTION", EOF_KIND},
    "function": {"FUNCTION", "IDENT"},
    "params": {"IDENT", "INT_TYPE", "BOOL_TYPE"},
    "requires": {"REQUIRES"},
    "ensures": {"ENSURES"},
    "block": {"LBRACE"},
    "stmt": {"IDENT", "IF", "WHILE", "ASSERT", "ASSUME", "LBRACE"},
    "assign": {"IDENT"},
    "if": {"IF"},
    "while": {"WHILE"},
    "assert": {"ASSERT"},
    "assume": {"ASSUME"},
    "expr": {"NOT", "BANG", "MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "or_expr": {"NOT", "BANG", "MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "and_expr": {"NOT", "BANG", "MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "not_expr": {"NOT", "BANG", "MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "cmp_expr": {"MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "add_expr": {"MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "mul_expr": {"MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "unary": {"MINUS", "INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
    "primary": {"INT", "TRUE", "FALSE", "IDENT", "LPAREN"},
}

FOLLOW_SETS: Dict[str, Set[str]] = {
    "program": {EOF_KIND},
    "function": {"FUNCTION", "IDENT", EOF_KIND},
    "params": {"RPAREN"},
    "requires": {"ENSURES", "LBRACE"},
    "ensures": {"LBRACE"},
    "block": {"FUNCTION", "IDENT", "IF", "WHILE", "ASSERT", "ASSUME", "LBRACE", "RBRACE", "ELSE", EOF_KIND},
    "stmt": {"IDENT", "IF", "WHILE", "ASSERT", "ASSUME", "LBRACE", "RBRACE"},
    "assign": {"SEMI", "IDENT", "IF", "WHILE", "ASSERT", "ASSUME", "LBRACE", "RBRACE"},
    "expr": {
        "SEMI",
        "RPAREN",
        "RBRACKET",
        "COMMA",
        "LBRACE",
        "ENSURES",
        "OR",
        "OR_SYM",
        "AND",
        "AND_SYM",
        "IMPLIES",
    },
}


@dataclass(frozen=True)
class ParseErrorItem:
    line: int
    col: int
    message: str
    stage: str = "syntax"

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "line": self.line,
            "col": self.col,
            "message": self.message,
        }

    def __str__(self) -> str:
        return f"error: {self.message} at {self.line}:{self.col}"


class _PanicSignal(Exception):
    """Внутреннее исключение для перехода в error_recover(A)."""
    pass


class Parser:
    """
    LL(1)-парсер языка Funny методом рекурсивного спуска (по слайдам 6, 9, 10, 11 HW2.pptx).
    Использует потоковый интерфейс лексера: self.lex.next_token() и self.lex.peek().
    """

    def __init__(self, lexer: Lexer):
        self.lex: Lexer = lexer
        self.errors: List[ParseErrorItem] = []
        self.tok: Token = self._pull_valid_token()

    def _pull_valid_token(self) -> Token:
        """
        Считывает следующий токен из лексера через next_token().
        Если токен содержит лексическую ошибку (TRAP / @error), регистрирует её с позицией
        и продолжает чтение до первого валидного токена или EOF.
        """
        while True:
            t = self.lex.next_token()
            if t.is_error:
                self.errors.append(
                    ParseErrorItem(
                        line=t.line,
                        col=t.col,
                        message=t.error or f"lexical error on {t.lexeme!r}",
                        stage="lexical",
                    )
                )
                if t.kind == EOF_KIND:
                    return t
                continue
            return t

    def peek(self) -> Token:
        return self.tok

    def eof(self) -> bool:
        return self.tok.kind == EOF_KIND

    def next_token(self) -> Token:
        prev = self.tok
        if not self.eof():
            self.tok = self._pull_valid_token()
        return prev

    def _pos(self, tok: Optional[Token] = None) -> SourcePos:
        t = tok or self.tok
        return SourcePos(line=t.line, col=t.col)

    def error(self, msg: str, tok: Optional[Token] = None) -> None:
        t = tok or self.tok
        self.errors.append(ParseErrorItem(line=t.line, col=t.col, message=msg, stage="syntax"))

    def expect(self, kind: str, label: Optional[str] = None) -> Token:
        if self.tok.kind != kind:
            shown_expected = label or kind
            shown_got = "EOF" if self.tok.kind == EOF_KIND else (self.tok.lexeme or self.tok.kind)
            self.error(f"expected {shown_expected!r} but got {shown_got!r}", self.tok)
            raise _PanicSignal()
        return self.next_token()

    def error_recover(self, nonterminal: str) -> None:
        """
        Режим паники строго по слайду 9 HW2.pptx:
            sync = FOLLOW(A) U {";", "}"}
            while peek() not in sync and not eof():
                next_token()
            if peek() == ";":
                next_token()
        Дополнительно гарантируется продвижение хотя бы на 1 токен, если текущий токен
        уже оказался в sync и не был съеден (защита от бесконечного цикла).
        """
        sync = set(FOLLOW_SETS.get(nonterminal, set())) | {"SEMI", "RBRACE"}
        while self.tok.kind not in sync and not self.eof():
            self.next_token()
        if self.tok.kind == "SEMI":
            self.next_token()

    # ==================== ПРАВИЛА ГРАММАТИКИ FUNNY ====================

    def parse_program(self) -> Program:
        """program := function+ (пустой ввод фиксируется как ошибка по слайду 13)."""
        start_pos = self._pos()
        if self.eof():
            self.error("unexpected empty input: expected at least one 'function'", self.tok)
            return Program(functions=[], pos=start_pos)

        functions: List[Function] = []
        while not self.eof():
            if self.tok.kind in ("FUNCTION", "IDENT"):
                # Проверяем, не является ли одиночный IDENT в конце лишним мусорным токеном после функции
                if self.tok.kind == "IDENT" and self.lex.peek().kind != "LPAREN" and functions:
                    self.error(f"unexpected token {self.tok.lexeme!r} after function declaration", self.tok)
                    self.next_token()
                    continue
                try:
                    functions.append(self.parse_function())
                except _PanicSignal:
                    # Восстановление на уровне функции: ищем следующую FUNCTION или '}' или EOF
                    while not self.eof() and self.tok.kind not in ("FUNCTION", "RBRACE"):
                        self.next_token()
                    if self.tok.kind == "RBRACE":
                        self.next_token()
            else:
                self.error(f"unexpected token {self.tok.lexeme!r} at top level", self.tok)
                self.next_token()

        return Program(functions=functions, pos=start_pos)

    def parse_function(self) -> Function:
        """
        function := "function" IDENT "(" params ")" "returns" IDENT requires? ensures? block
        Также поддерживает сокращенную запись без ключевого слова "function" и типизированные параметры.
        """
        start_tok = self.tok
        if self.tok.kind == "FUNCTION":
            self.next_token()
        name_tok = self.expect("IDENT", "function name (IDENT)")
        self.expect("LPAREN", "(")
        params = self.parse_params()
        self.expect("RPAREN", ")")
        self.expect("RETURNS", "returns")

        # Поддержка как `returns r`, так и `returns (r: int)`
        if self.tok.kind == "LPAREN":
            self.next_token()
            ret_list = self.parse_params()
            self.expect("RPAREN", ")")
            ret_name = ret_list[0] if ret_list else ""
        else:
            ret_name = self.expect("IDENT", "return variable (IDENT)").lexeme
            if self.tok.kind == "COLON":
                self._skip_optional_type()

        req = self.parse_requires() if self.tok.kind == "REQUIRES" else None
        ens = self.parse_ensures() if self.tok.kind == "ENSURES" else None
        body = self.parse_block()
        return Function(
            name=name_tok.lexeme,
            params=params,
            returns=ret_name,
            requires=req,
            ensures=ens,
            body=body,
            pos=self._pos(start_tok),
        )

    def _skip_optional_type(self) -> None:
        """Опциональная поддержка аннотаций типов `: int[]` для совместимости с полным Funny."""
        if self.tok.kind == "COLON":
            self.next_token()
            if self.tok.kind in ("INT_TYPE", "BOOL_TYPE", "IDENT"):
                self.next_token()
            if self.tok.kind == "LBRACKET":
                self.next_token()
                if self.tok.kind == "RBRACKET":
                    self.next_token()

    def parse_params(self) -> List[str]:
        """params := (IDENT ("," IDENT)*)?"""
        params: List[str] = []
        if self.tok.kind == "RPAREN":
            return params
        if self.tok.kind in ("INT_TYPE", "BOOL_TYPE"):
            self.next_token()
        first = self.expect("IDENT", "parameter name (IDENT)")
        self._skip_optional_type()
        params.append(first.lexeme)
        while self.tok.kind == "COMMA":
            self.next_token()
            if self.tok.kind in ("INT_TYPE", "BOOL_TYPE"):
                self.next_token()
            p = self.expect("IDENT", "parameter name (IDENT)")
            self._skip_optional_type()
            params.append(p.lexeme)
        return params

    def parse_requires(self) -> Expr:
        """requires := "requires" expr"""
        self.expect("REQUIRES", "requires")
        expr = self.parse_expr()
        if self.tok.kind == "SEMI":
            self.next_token()
        return expr

    def parse_ensures(self) -> Expr:
        """ensures := "ensures" expr"""
        self.expect("ENSURES", "ensures")
        expr = self.parse_expr()
        if self.tok.kind == "SEMI":
            self.next_token()
        return expr

    def parse_block(self) -> Block:
        """block := "{" stmt* "}" """
        lbrace = self.expect("LBRACE", "{")
        stmts: List[Stmt] = []
        while self.tok.kind != "RBRACE" and not self.eof():
            before_pos = (self.tok.line, self.tok.col, self.tok.offset)
            try:
                stmts.append(self.parse_stmt())
            except _PanicSignal:
                err_pos = self._pos()
                self.error_recover("stmt")
                # Если error_recover остановился на токене из FOLLOW(stmt), но указатель не сдвинулся,
                # принудительно продвигаем на 1 токен (кроме RBRACE), чтобы исключить зацикливание.
                after_pos = (self.tok.line, self.tok.col, self.tok.offset)
                if after_pos == before_pos and self.tok.kind != "RBRACE" and not self.eof():
                    self.next_token()
                stmts.append(ErrorNode(message="recovered from syntax error", pos=err_pos))
        self.expect("RBRACE", "}")
        return Block(stmts=stmts, pos=self._pos(lbrace))

    def parse_stmt(self) -> Stmt:
        """stmt := assign | if | while | assert | assume | block"""
        kind = self.tok.kind
        if kind == "IDENT":
            return self.parse_assign_or_call()
        if kind == "IF":
            return self.parse_if()
        if kind == "WHILE":
            return self.parse_while()
        if kind == "ASSERT":
            return self.parse_assert()
        if kind == "ASSUME":
            return self.parse_assume()
        if kind == "LBRACE":
            return self.parse_block()

        self.error(f"unexpected {self.tok.lexeme or self.tok.kind!r}: expected statement", self.tok)
        self.next_token()
        raise _PanicSignal()

    def parse_assign_or_call(self) -> Stmt:
        """
        Левая факторизация правила assign:
            assign      := IDENT assign_tail
            assign_tail := "=" expr ";"?
                         | "[" expr "]" "=" expr ";"?
        """
        ident_tok = self.expect("IDENT", "variable name (IDENT)")
        pos = self._pos(ident_tok)
        base_ident = Ident(name=ident_tok.lexeme, pos=pos)

        # Опциональная аннотация типа при объявлении с инициализацией `x: int = 1;`
        if self.tok.kind == "COLON":
            self._skip_optional_type()

        if self.tok.kind == "LBRACKET":
            lb = self.next_token()
            idx_expr = self.parse_expr()
            self.expect("RBRACKET", "]")
            target: Ident | ArrayIndex = ArrayIndex(base=base_ident, index=idx_expr, pos=self._pos(lb))
            self.expect("ASSIGN", "=")
            val_expr = self.parse_expr()
            self._consume_stmt_semi()
            return Assign(target=target, value=val_expr, pos=pos)

        if self.tok.kind == "ASSIGN":
            self.next_token()
            val_expr = self.parse_expr()
            self._consume_stmt_semi()
            return Assign(target=base_ident, value=val_expr, pos=pos)

        self.error(
            f"expected '=' or '[' after identifier {ident_tok.lexeme!r}, got {self.tok.lexeme or self.tok.kind!r}",
            self.tok,
        )
        raise _PanicSignal()

    def _consume_stmt_semi(self) -> None:
        """В тестах слайда 13 точка с запятой стоит после операторов присваивания, assert и assume."""
        self.expect("SEMI", ";")

    def parse_if(self) -> If:
        """if := "if" "(" expr ")" block ("else" block)?"""
        kw = self.expect("IF", "if")
        self.expect("LPAREN", "(")
        cond = self.parse_expr()
        self.expect("RPAREN", ")")
        then_block = self.parse_block()
        else_block: Optional[Block] = None
        if self.tok.kind == "ELSE":
            self.next_token()
            else_block = self.parse_block()
        return If(cond=cond, then_branch=then_block, else_branch=else_block, pos=self._pos(kw))

    def parse_while(self) -> While:
        """while := "while" "(" expr ")" block"""
        kw = self.expect("WHILE", "while")
        self.expect("LPAREN", "(")
        cond = self.parse_expr()
        self.expect("RPAREN", ")")
        body = self.parse_block()
        return While(cond=cond, body=body, pos=self._pos(kw))

    def parse_assert(self) -> Assert:
        """assert := "assert" expr ";" """
        kw = self.expect("ASSERT", "assert")
        expr = self.parse_expr()
        self._consume_stmt_semi()
        return Assert(expr=expr, pos=self._pos(kw))

    def parse_assume(self) -> Assume:
        """assume := "assume" expr ";" """
        kw = self.expect("ASSUME", "assume")
        expr = self.parse_expr()
        self._consume_stmt_semi()
        return Assume(expr=expr, pos=self._pos(kw))

    # ==================== ВЫРАЖЕНИЯ (СТРОГО ПО СЛАЙДУ 4 HW2.pptx) ====================
    # expr     := or_expr
    # or_expr  := and_expr ("or" and_expr)*
    # and_expr := not_expr ("and" not_expr)*
    # not_expr := "not" not_expr | cmp_expr
    # cmp_expr := add_expr (("==" | "!=" | "<" | "<=" | ">" | ">=") add_expr)?
    # add_expr := mul_expr (("+" | "-") mul_expr)*
    # mul_expr := unary (("*" | "/") unary)*
    # unary    := "-" unary | primary
    # primary  := INT | "true" | "false" | IDENT | IDENT "[" expr "]" | IDENT "(" args ")" | "(" expr ")"

    def parse_expr(self) -> Expr:
        return self.parse_or_expr()

    def parse_or_expr(self) -> Expr:
        left = self.parse_and_expr()
        while self.tok.kind in ("OR", "OR_SYM"):
            op_tok = self.next_token()
            right = self.parse_and_expr()
            left = BinaryOp(op="or", left=left, right=right, pos=self._pos(op_tok))
        return left

    def parse_and_expr(self) -> Expr:
        left = self.parse_not_expr()
        while self.tok.kind in ("AND", "AND_SYM"):
            op_tok = self.next_token()
            right = self.parse_not_expr()
            left = BinaryOp(op="and", left=left, right=right, pos=self._pos(op_tok))
        return left

    def parse_not_expr(self) -> Expr:
        if self.tok.kind in ("NOT", "BANG"):
            op_tok = self.next_token()
            operand = self.parse_not_expr()
            return UnaryOp(op="not", operand=operand, pos=self._pos(op_tok))
        return self.parse_cmp_expr()

    def parse_cmp_expr(self) -> Expr:
        left = self.parse_add_expr()
        if self.tok.kind in ("EQ", "NEQ", "LT", "LE", "GT", "GE"):
            op_tok = self.next_token()
            right = self.parse_add_expr()
            return BinaryOp(op=op_tok.lexeme, left=left, right=right, pos=self._pos(op_tok))
        return left

    def parse_add_expr(self) -> Expr:
        left = self.parse_mul_expr()
        while self.tok.kind in ("PLUS", "MINUS"):
            op_tok = self.next_token()
            right = self.parse_mul_expr()
            left = BinaryOp(op=op_tok.lexeme, left=left, right=right, pos=self._pos(op_tok))
        return left

    def parse_mul_expr(self) -> Expr:
        left = self.parse_unary()
        while self.tok.kind in ("STAR", "SLASH", "PERCENT"):
            op_tok = self.next_token()
            right = self.parse_unary()
            left = BinaryOp(op=op_tok.lexeme, left=left, right=right, pos=self._pos(op_tok))
        return left

    def parse_unary(self) -> Expr:
        if self.tok.kind == "MINUS":
            op_tok = self.next_token()
            operand = self.parse_unary()
            return UnaryOp(op="-", operand=operand, pos=self._pos(op_tok))
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        tok = self.tok
        pos = self._pos(tok)

        if tok.kind == "INT":
            self.next_token()
            return Int(value=int(tok.lexeme), pos=pos)

        if tok.kind == "TRUE":
            self.next_token()
            return Bool(value=True, pos=pos)

        if tok.kind == "FALSE":
            self.next_token()
            return Bool(value=False, pos=pos)

        if tok.kind == "IDENT":
            # Левая факторизация для primary:
            # primary := IDENT primary_tail
            # primary_tail := "[" expr "]" | "(" args? ")" | ε
            self.next_token()
            base = Ident(name=tok.lexeme, pos=pos)
            if self.tok.kind == "LBRACKET":
                lb = self.next_token()
                idx = self.parse_expr()
                self.expect("RBRACKET", "]")
                return ArrayIndex(base=base, index=idx, pos=self._pos(lb))
            if self.tok.kind == "LPAREN":
                self.next_token()
                args: List[Expr] = []
                if self.tok.kind != "RPAREN":
                    args.append(self.parse_expr())
                    while self.tok.kind == "COMMA":
                        self.next_token()
                        args.append(self.parse_expr())
                self.expect("RPAREN", ")")
                return Call(name=tok.lexeme, args=args, pos=pos)
            return base

        if tok.kind == "LPAREN":
            self.next_token()
            inner = self.parse_expr()
            self.expect("RPAREN", ")")
            return inner

        got = "EOF" if tok.kind == EOF_KIND else (tok.lexeme or tok.kind)
        self.error(f"expected expression but got {got!r}", tok)
        raise _PanicSignal()


def parse_text(
    text: str,
    lexer: Optional[Lexer] = None,
    spec_path: Path = DEFAULT_SPEC,
) -> Tuple[Program, List[ParseErrorItem]]:
    if lexer is None:
        lexer = Lexer(build(spec_path).tables)
    lexer.reset(text)
    parser = Parser(lexer)
    prog = parser.parse_program()
    return prog, parser.errors
