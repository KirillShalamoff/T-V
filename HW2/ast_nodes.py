from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass(frozen=True)
class SourcePos:
    line: int
    col: int

    def to_dict(self) -> Dict[str, int]:
        return {"line": self.line, "col": self.col}

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"


# ==================== УЗЛЫ AST (СТРОГО ПО СЛАЙДУ 8 HW2.pptx) ====================

@dataclass(frozen=True)
class Int:
    value: int
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "Int", "value": self.value, "pos": self.pos.to_dict() if self.pos else None}

    def to_sexpr(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Bool:
    value: bool
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "Bool", "value": self.value, "pos": self.pos.to_dict() if self.pos else None}

    def to_sexpr(self) -> str:
        return "true" if self.value else "false"


@dataclass(frozen=True)
class Ident:
    name: str
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "Ident", "name": self.name, "pos": self.pos.to_dict() if self.pos else None}

    def to_sexpr(self) -> str:
        return self.name


@dataclass(frozen=True)
class ArrayIndex:
    base: "Expr"
    index: "Expr"
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "ArrayIndex",
            "base": self.base.to_dict(),
            "index": self.index.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return f"(index {self.base.to_sexpr()} {self.index.to_sexpr()})"


@dataclass(frozen=True)
class ArrayUpdate:
    """
    Функциональное обновление массива (сахар для a[i] = val -> a = update(a, i, val)).
    """
    base: "Expr"
    index: "Expr"
    value: "Expr"
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "ArrayUpdate",
            "base": self.base.to_dict(),
            "index": self.index.to_dict(),
            "value": self.value.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return f"(update {self.base.to_sexpr()} {self.index.to_sexpr()} {self.value.to_sexpr()})"


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: "Expr"
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "UnaryOp",
            "op": self.op,
            "operand": self.operand.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return f"({self.op} {self.operand.to_sexpr()})"


@dataclass(frozen=True)
class BinaryOp:
    op: str
    left: "Expr"
    right: "Expr"
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "BinaryOp",
            "op": self.op,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return f"({self.op} {self.left.to_sexpr()} {self.right.to_sexpr()})"


@dataclass(frozen=True)
class Call:
    name: str
    args: List["Expr"]
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Call",
            "name": self.name,
            "args": [a.to_dict() for a in self.args],
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        args_s = " ".join(a.to_sexpr() for a in self.args)
        return f"(call {self.name}" + (f" {args_s})" if args_s else ")")


Expr = Union[Int, Bool, Ident, ArrayIndex, ArrayUpdate, UnaryOp, BinaryOp, Call]


# ==================== ОПЕРАТОРЫ (STMT) ====================

@dataclass(frozen=True)
class Assign:
    """
    Узел присваивания: Assign(target, value).
    - Для обычного присваивания `r = x + 1;` -> target=Ident("r"), value=BinaryOp(...)
    - Для присваивания в массив `a[i] = v;` -> target=ArrayIndex(Ident("a"), i), value=v,
      а свойство `desugared` возвращает чистое функциональное копирование:
      Assign(target=Ident("a"), value=ArrayUpdate(Ident("a"), i, v)).
    """
    target: Union[Ident, ArrayIndex]
    value: Expr
    pos: Optional[SourcePos] = None

    @property
    def is_array_sugar(self) -> bool:
        return isinstance(self.target, ArrayIndex)

    def desugared(self) -> "Assign":
        if isinstance(self.target, ArrayIndex):
            return Assign(
                target=self.target.base if isinstance(self.target.base, Ident) else Ident(str(self.target.base)),
                value=ArrayUpdate(
                    base=self.target.base,
                    index=self.target.index,
                    value=self.value,
                    pos=self.pos,
                ),
                pos=self.pos,
            )
        return self

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": "Assign",
            "target": self.target.to_dict(),
            "value": self.value.to_dict(),
        }
        if isinstance(self.target, ArrayIndex):
            d["functional_sugar"] = {
                "target": self.target.base.to_dict(),
                "value": ArrayUpdate(
                    base=self.target.base,
                    index=self.target.index,
                    value=self.value,
                    pos=self.pos,
                ).to_dict(),
            }
        d["pos"] = self.pos.to_dict() if self.pos else None
        return d

    def to_sexpr(self) -> str:
        if isinstance(self.target, ArrayIndex):
            return f"(= {self.target.base.to_sexpr()} (update {self.target.base.to_sexpr()} {self.target.index.to_sexpr()} {self.value.to_sexpr()}))"
        return f"(= {self.target.to_sexpr()} {self.value.to_sexpr()})"


@dataclass(frozen=True)
class Block:
    stmts: List["Stmt"] = field(default_factory=list)
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Block",
            "stmts": [s.to_dict() for s in self.stmts],
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        if not self.stmts:
            return "(block)"
        inner = " ".join(s.to_sexpr() for s in self.stmts)
        return f"(block {inner})"


@dataclass(frozen=True)
class If:
    cond: Expr
    then_branch: Block
    else_branch: Optional[Block] = None
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "If",
            "cond": self.cond.to_dict(),
            "then": self.then_branch.to_dict(),
            "else": self.else_branch.to_dict() if self.else_branch else None,
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        if self.else_branch:
            return f"(if {self.cond.to_sexpr()} {self.then_branch.to_sexpr()} {self.else_branch.to_sexpr()})"
        return f"(if {self.cond.to_sexpr()} {self.then_branch.to_sexpr()})"


@dataclass(frozen=True)
class While:
    cond: Expr
    body: Block
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "While",
            "cond": self.cond.to_dict(),
            "body": self.body.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return f"(while {self.cond.to_sexpr()} {self.body.to_sexpr()})"


@dataclass(frozen=True)
class Assert:
    expr: Expr
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Assert",
            "expr": self.expr.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return f"(assert {self.expr.to_sexpr()})"


@dataclass(frozen=True)
class Assume:
    expr: Expr
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Assume",
            "expr": self.expr.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return f"(assume {self.expr.to_sexpr()})"


@dataclass(frozen=True)
class ErrorNode:
    message: str
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Error",
            "message": self.message,
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        return "(error)"


Stmt = Union[Assign, Block, If, While, Assert, Assume, ErrorNode]


# ==================== ФУНКЦИИ И ПРОГРАММА ====================

@dataclass(frozen=True)
class Function:
    name: str
    params: List[str]
    returns: str
    requires: Optional[Expr]
    ensures: Optional[Expr]
    body: Block
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Function",
            "name": self.name,
            "params": self.params,
            "returns": self.returns,
            "requires": self.requires.to_dict() if self.requires else None,
            "ensures": self.ensures.to_dict() if self.ensures else None,
            "body": self.body.to_dict(),
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_sexpr(self) -> str:
        params_s = "(" + " ".join(self.params) + ")"
        parts = [f"function {self.name} {params_s} (returns {self.returns})"]
        if self.requires:
            parts.append(f"(requires {self.requires.to_sexpr()})")
        if self.ensures:
            parts.append(f"(ensures {self.ensures.to_sexpr()})")
        parts.append(self.body.to_sexpr())
        return "(" + " ".join(parts) + ")"


@dataclass(frozen=True)
class Program:
    functions: List[Function]
    pos: Optional[SourcePos] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "Program",
            "functions": [f.to_dict() for f in self.functions],
            "pos": self.pos.to_dict() if self.pos else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_sexpr(self) -> str:
        if not self.functions:
            return "(program)"
        inner = " ".join(f.to_sexpr() for f in self.functions)
        return f"(program {inner})"


def format_tree(node: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(node, Program):
        lines = [f"{pad}Program"]
        for fn in node.functions:
            lines.append(format_tree(fn, indent + 1))
        return "\n".join(lines)
    if isinstance(node, Function):
        p_str = ", ".join(node.params)
        lines = [f"{pad}Function(name={node.name!r}, params=[{p_str}], returns={node.returns!r}) @{node.pos}"]
        if node.requires:
            lines.append(f"{pad}  requires:")
            lines.append(format_tree(node.requires, indent + 2))
        if node.ensures:
            lines.append(f"{pad}  ensures:")
            lines.append(format_tree(node.ensures, indent + 2))
        lines.append(format_tree(node.body, indent + 1))
        return "\n".join(lines)
    if isinstance(node, Block):
        lines = [f"{pad}Block @{node.pos}"]
        for s in node.stmts:
            lines.append(format_tree(s, indent + 1))
        return "\n".join(lines)
    if isinstance(node, Assign):
        sugar_note = " [functional array update sugar]" if node.is_array_sugar else ""
        lines = [
            f"{pad}Assign{sugar_note} @{node.pos}",
            f"{pad}  target:",
            format_tree(node.target, indent + 2),
            f"{pad}  value:",
            format_tree(node.value, indent + 2),
        ]
        return "\n".join(lines)
    if isinstance(node, If):
        lines = [
            f"{pad}If @{node.pos}",
            f"{pad}  cond:",
            format_tree(node.cond, indent + 2),
            f"{pad}  then:",
            format_tree(node.then_branch, indent + 2),
        ]
        if node.else_branch:
            lines.append(f"{pad}  else:")
            lines.append(format_tree(node.else_branch, indent + 2))
        return "\n".join(lines)
    if isinstance(node, While):
        return (
            f"{pad}While @{node.pos}\n"
            f"{pad}  cond:\n{format_tree(node.cond, indent + 2)}\n"
            f"{pad}  body:\n{format_tree(node.body, indent + 2)}"
        )
    if isinstance(node, Assert):
        return f"{pad}Assert @{node.pos}\n{format_tree(node.expr, indent + 1)}"
    if isinstance(node, Assume):
        return f"{pad}Assume @{node.pos}\n{format_tree(node.expr, indent + 1)}"
    if isinstance(node, BinaryOp):
        return (
            f"{pad}BinaryOp({node.op!r}) @{node.pos}\n"
            f"{format_tree(node.left, indent + 1)}\n"
            f"{format_tree(node.right, indent + 1)}"
        )
    if isinstance(node, UnaryOp):
        return f"{pad}UnaryOp({node.op!r}) @{node.pos}\n{format_tree(node.operand, indent + 1)}"
    if isinstance(node, ArrayIndex):
        return (
            f"{pad}ArrayIndex @{node.pos}\n"
            f"{format_tree(node.base, indent + 1)}\n"
            f"{format_tree(node.index, indent + 1)}"
        )
    if isinstance(node, ArrayUpdate):
        return (
            f"{pad}ArrayUpdate @{node.pos}\n"
            f"{format_tree(node.base, indent + 1)}\n"
            f"{format_tree(node.index, indent + 1)}\n"
            f"{format_tree(node.value, indent + 1)}"
        )
    if isinstance(node, Call):
        lines = [f"{pad}Call({node.name!r}) @{node.pos}"]
        for a in node.args:
            lines.append(format_tree(a, indent + 1))
        return "\n".join(lines)
    if isinstance(node, Ident):
        return f"{pad}Ident({node.name!r}) @{node.pos}"
    if isinstance(node, Int):
        return f"{pad}Int({node.value}) @{node.pos}"
    if isinstance(node, Bool):
        return f"{pad}Bool({node.value}) @{node.pos}"
    if isinstance(node, ErrorNode):
        return f"{pad}ErrorNode({node.message!r}) @{node.pos}"
    return f"{pad}{node!r}"
