from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional
from core.exceptions import RuleCompilationError


class TokenType(Enum):
    # Literals & Identifiers
    NUMBER = auto()
    STRING = auto()
    IDENTIFIER = auto()
    BOOLEAN = auto()

    # Keywords
    IF = auto()
    THEN = auto()
    ELSE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    WITHIN_METERS = auto()

    # Operators
    EQUALS = auto()       # ==
    NOT_EQUALS = auto()   # !=
    LT = auto()           # <
    LTE = auto()          # <=
    GT = auto()           # >
    GTE = auto()          # >=
    PLUS = auto()         # +
    MINUS = auto()        # -
    STAR = auto()         # *
    SLASH = auto()        # /

    # Delimiters
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    COMMA = auto()        # ,
    SEMICOLON = auto()    # ;
    EOF = auto()


@dataclass
class Token:
    token_type: TokenType
    value: str
    line: int
    column: int


KEYWORDS = {
    "IF": TokenType.IF,
    "THEN": TokenType.THEN,
    "ELSE": TokenType.ELSE,
    "AND": TokenType.AND,
    "OR": TokenType.OR,
    "NOT": TokenType.NOT,
    "TRUE": TokenType.BOOLEAN,
    "FALSE": TokenType.BOOLEAN,
    "WITHIN_METERS": TokenType.WITHIN_METERS,
}


class Lexer:
    """Deterministic Finite Automaton (DFA) Lexer for NDTM-RuleLang."""

    def __init__(self, source_code: str):
        self.source = source_code
        self.length = len(source_code)
        self.pos = 0
        self.line = 1
        self.col = 1

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= self.length:
            return ""
        return self.source[idx]

    def _advance(self) -> str:
        ch = self._peek()
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []

        while self.pos < self.length:
            ch = self._peek()

            # Whitespace
            if ch.isspace():
                self._advance()
                continue

            start_line = self.line
            start_col = self.col

            # Single-line comment (# or //)
            if ch == "#" or (ch == "/" and self._peek(1) == "/"):
                while self.pos < self.length and self._peek() != "\n":
                    self._advance()
                continue

            # Delimiters
            if ch == "(":
                self._advance()
                tokens.append(Token(TokenType.LPAREN, "(", start_line, start_col))
                continue
            if ch == ")":
                self._advance()
                tokens.append(Token(TokenType.RPAREN, ")", start_line, start_col))
                continue
            if ch == ",":
                self._advance()
                tokens.append(Token(TokenType.COMMA, ",", start_line, start_col))
                continue
            if ch == ";":
                self._advance()
                tokens.append(Token(TokenType.SEMICOLON, ";", start_line, start_col))
                continue

            # Operators
            if ch == "+":
                self._advance()
                tokens.append(Token(TokenType.PLUS, "+", start_line, start_col))
                continue
            if ch == "-":
                self._advance()
                tokens.append(Token(TokenType.MINUS, "-", start_line, start_col))
                continue
            if ch == "*":
                self._advance()
                tokens.append(Token(TokenType.STAR, "*", start_line, start_col))
                continue
            if ch == "/":
                self._advance()
                tokens.append(Token(TokenType.SLASH, "/", start_line, start_col))
                continue

            if ch == "=":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.EQUALS, "==", start_line, start_col))
                else:
                    raise RuleCompilationError("Expected '==' for equality comparison", start_line, start_col)
                continue

            if ch == "!":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.NOT_EQUALS, "!=", start_line, start_col))
                else:
                    raise RuleCompilationError("Unexpected '!'. Did you mean '!=' or 'NOT'?", start_line, start_col)
                continue

            if ch == "<":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.LTE, "<=", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.LT, "<", start_line, start_col))
                continue

            if ch == ">":
                self._advance()
                if self._peek() == "=":
                    self._advance()
                    tokens.append(Token(TokenType.GTE, ">=", start_line, start_col))
                else:
                    tokens.append(Token(TokenType.GT, ">", start_line, start_col))
                continue

            # Strings: "..." or '...'
            if ch in ('"', "'"):
                quote_char = self._advance()
                str_val = []
                while self.pos < self.length and self._peek() != quote_char:
                    if self._peek() == "\\":
                        self._advance()
                    str_val.append(self._advance())
                if self.pos >= self.length:
                    raise RuleCompilationError("Unterminated string literal", start_line, start_col)
                self._advance()  # consume closing quote
                tokens.append(Token(TokenType.STRING, "".join(str_val), start_line, start_col))
                continue

            # Numbers
            if ch.isdigit():
                num_chars = []
                is_float = False
                while self.pos < self.length and (self._peek().isdigit() or self._peek() == "."):
                    if self._peek() == ".":
                        if is_float:
                            break  # double dot
                        is_float = True
                    num_chars.append(self._advance())
                tokens.append(Token(TokenType.NUMBER, "".join(num_chars), start_line, start_col))
                continue

            # Identifiers & Keywords
            if ch.isalpha() or ch == "_":
                ident_chars = []
                while self.pos < self.length and (self._peek().isalnum() or self._peek() in ("_", ".")):
                    ident_chars.append(self._advance())
                ident = "".join(ident_chars)
                upper_ident = ident.upper()
                if upper_ident in KEYWORDS:
                    tokens.append(Token(KEYWORDS[upper_ident], upper_ident, start_line, start_col))
                else:
                    tokens.append(Token(TokenType.IDENTIFIER, ident, start_line, start_col))
                continue

            raise RuleCompilationError(f"Unexpected character '{ch}'", self.line, self.col)

        tokens.append(Token(TokenType.EOF, "", self.line, self.col))
        return tokens
