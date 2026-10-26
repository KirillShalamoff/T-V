from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

TRAP_KIND = "TRAP"
EOF_KIND = "EOF"


@dataclass(frozen=True)
class Token:
    kind: str
    lexeme: str
    error: Optional[str] = None
    line: int = 1
    col: int = 1
    offset: int = 0

    @property
    def column(self) -> int:
        return self.col

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def pos_str(self) -> str:
        return f"{self.line}:{self.col}"


class Lexer:
    """
    Табличный лексер на основе минимального ДКА из HW1, дополненный:
    - отслеживанием координат (line, col);
    - потоковым интерфейсом next_token() и peek() для интеграции с парсером (P02/HW2).
    """

    def __init__(self, tables: dict, text: str = ""):
        self.char_class: List[int] = tables["char_class"]
        self.other_class: int = tables["other_class"]
        self.trans: List[List[int]] = tables["transitions"]
        self.start: int = tables["start"]
        self.trap: int = tables["trap"]
        self.accept: List[Optional[str]] = tables["accept"]
        self.kind = {t["name"]: t["kind"] for t in tables["tokens"]}

        self._stream: List[Token] = []
        self._cursor: int = 0
        if text:
            self.reset(text)

    @classmethod
    def from_json(cls, path, text: str = "") -> "Lexer":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")), text=text)

    def _class(self, ch: str) -> int:
        c = ord(ch)
        return self.char_class[c] if c < len(self.char_class) else self.other_class

    def longest_match(self, text: str, pos: int) -> Tuple[Optional[str], int]:
        state, best, end = self.start, None, pos
        for i in range(pos, len(text)):
            state = self.trans[state][self._class(text[i])]
            if state == self.trap:
                break
            if self.accept[state] is not None:
                best, end = self.accept[state], i + 1
        return best, end

    @staticmethod
    def _advance_pos(text: str, start: int, end: int, line: int, col: int) -> Tuple[int, int]:
        for i in range(start, end):
            if text[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
        return line, col

    def tokenize(self, text: str, keep_skipped: bool = False) -> List[Token]:
        tokens: List[Token] = []
        pos = 0
        line, col = 1, 1
        while pos < len(text):
            name, end = self.longest_match(text, pos)
            if name is None:
                ch = text[pos]
                if ord(ch) >= 128:
                    msg = f"символ U+{ord(ch):04X} вне алфавита ASCII → ловушка"
                else:
                    msg = f"нет перехода по символу {ch!r} → ловушка"
                tokens.append(Token(TRAP_KIND, ch, msg, line=line, col=col, offset=pos))
                line, col = self._advance_pos(text, pos, pos + 1, line, col)
                pos += 1
                continue
            lexeme = text[pos:end]
            kind = self.kind[name]
            if kind == "error":
                tokens.append(
                    Token(
                        name,
                        lexeme,
                        f"недопустимая лексема {lexeme!r} ({name})",
                        line=line,
                        col=col,
                        offset=pos,
                    )
                )
            elif kind == "token" or keep_skipped:
                tokens.append(Token(name, lexeme, line=line, col=col, offset=pos))
            line, col = self._advance_pos(text, pos, end, line, col)
            pos = end
        return tokens

    # --- Потоковый интерфейс из презентации HW2 (next_token / peek) ---

    def reset(self, text: str) -> "Lexer":
        raw_tokens = self.tokenize(text)
        last_line, last_col, last_off = 1, 1, len(text)
        if text:
            last_line, last_col = self._advance_pos(text, 0, len(text), 1, 1)
        self._stream = raw_tokens + [Token(EOF_KIND, "", line=last_line, col=last_col, offset=last_off)]
        self._cursor = 0
        return self

    def peek(self, k: int = 0) -> Token:
        """Смотрит токен без продвижения указателя."""
        if not self._stream:
            return Token(EOF_KIND, "", line=1, col=1, offset=0)
        idx = min(self._cursor + k, len(self._stream) - 1)
        return self._stream[idx]

    def next_token(self) -> Token:
        """Возвращает текущий токен {kind, lexeme, line, col} и сдвигает указатель."""
        tok = self.peek()
        if self._cursor < len(self._stream) - 1:
            self._cursor += 1
        return tok
