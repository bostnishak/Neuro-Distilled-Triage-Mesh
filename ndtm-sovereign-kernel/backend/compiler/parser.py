from typing import Dict, List, Optional
from compiler.lexer import Token, TokenType
from compiler.ast_nodes import (
    ASTNode,
    LiteralNode,
    VariableNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
    IfThenElseNode,
)
from core.exceptions import RuleCompilationError

# Operator Precedence Hierarchy
PREC_LOWEST = 0
PREC_OR = 1
PREC_AND = 2
PREC_EQUALS = 3       # ==, !=
PREC_COMPARE = 4      # <, <=, >, >=
PREC_SUM = 5          # +, -
PREC_PRODUCT = 6      # *, /
PREC_PREFIX = 7       # NOT, -
PREC_CALL = 8         # (

INFIX_PRECEDENCE: Dict[TokenType, int] = {
    TokenType.OR: PREC_OR,
    TokenType.AND: PREC_AND,
    TokenType.EQUALS: PREC_EQUALS,
    TokenType.NOT_EQUALS: PREC_EQUALS,
    TokenType.LT: PREC_COMPARE,
    TokenType.LTE: PREC_COMPARE,
    TokenType.GT: PREC_COMPARE,
    TokenType.GTE: PREC_COMPARE,
    TokenType.PLUS: PREC_SUM,
    TokenType.MINUS: PREC_SUM,
    TokenType.STAR: PREC_PRODUCT,
    TokenType.SLASH: PREC_PRODUCT,
    TokenType.LPAREN: PREC_CALL,
}


class PrattParser:
    """Pratt Top-Down Operator Precedence Parser for NDTM-RuleLang."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _current_token(self) -> Token:
        if self.pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.pos]

    def _peek_token(self) -> Token:
        if self.pos + 1 >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.pos + 1]

    def _advance(self) -> Token:
        tok = self._current_token()
        self.pos += 1
        return tok

    def _expect(self, expected_type: TokenType) -> Token:
        tok = self._current_token()
        if tok.token_type != expected_type:
            raise RuleCompilationError(
                f"Expected token {expected_type.name}, got {tok.token_type.name} ('{tok.value}')",
                tok.line,
                tok.column,
            )
        return self._advance()

    def _current_precedence(self) -> int:
        tok = self._current_token()
        return INFIX_PRECEDENCE.get(tok.token_type, PREC_LOWEST)

    def parse_expression(self, precedence: int = PREC_LOWEST) -> ASTNode:
        token = self._current_token()

        # Prefix rule
        left: ASTNode
        if token.token_type == TokenType.NUMBER:
            self._advance()
            val = float(token.value) if "." in token.value else int(token.value)
            type_name = "FLOAT" if "." in token.value else "INT"
            left = LiteralNode(value=val, type_name=type_name)

        elif token.token_type == TokenType.STRING:
            self._advance()
            left = LiteralNode(value=token.value, type_name="STRING")

        elif token.token_type == TokenType.BOOLEAN:
            self._advance()
            left = LiteralNode(value=(token.value.upper() == "TRUE"), type_name="BOOL")

        elif token.token_type == TokenType.IDENTIFIER:
            ident_name = token.value
            self._advance()
            if self._current_token().token_type == TokenType.LPAREN:
                # Function call
                self._advance()  # consume (
                args: List[ASTNode] = []
                if self._current_token().token_type != TokenType.RPAREN:
                    args.append(self.parse_expression(PREC_LOWEST))
                    while self._current_token().token_type == TokenType.COMMA:
                        self._advance()
                        args.append(self.parse_expression(PREC_LOWEST))
                self._expect(TokenType.RPAREN)
                left = FunctionCallNode(func_name=ident_name, args=args)
            else:
                left = VariableNode(name=ident_name)

        elif token.token_type == TokenType.WITHIN_METERS:
            self._advance()
            self._expect(TokenType.LPAREN)
            args = [self.parse_expression(PREC_LOWEST)]
            self._expect(TokenType.COMMA)
            args.append(self.parse_expression(PREC_LOWEST))
            self._expect(TokenType.COMMA)
            args.append(self.parse_expression(PREC_LOWEST))
            self._expect(TokenType.RPAREN)
            left = FunctionCallNode(func_name="WITHIN_METERS", args=args)

        elif token.token_type == TokenType.NOT:
            self._advance()
            operand = self.parse_expression(PREC_PREFIX)
            left = UnaryOpNode(op="NOT", operand=operand)

        elif token.token_type == TokenType.MINUS:
            self._advance()
            operand = self.parse_expression(PREC_PREFIX)
            left = UnaryOpNode(op="-", operand=operand)

        elif token.token_type == TokenType.LPAREN:
            self._advance()
            left = self.parse_expression(PREC_LOWEST)
            self._expect(TokenType.RPAREN)

        elif token.token_type == TokenType.IF:
            self._advance()
            cond = self.parse_expression(PREC_LOWEST)
            self._expect(TokenType.THEN)
            then_branch = self.parse_expression(PREC_LOWEST)
            else_branch: Optional[ASTNode] = None
            if self._current_token().token_type == TokenType.ELSE:
                self._advance()
                else_branch = self.parse_expression(PREC_LOWEST)
            left = IfThenElseNode(condition=cond, then_branch=then_branch, else_branch=else_branch)

        else:
            raise RuleCompilationError(
                f"Unexpected token in expression: {token.token_type.name} ('{token.value}')",
                token.line,
                token.column,
            )

        # Infix rule loop
        while precedence < self._current_precedence():
            op_token = self._current_token()
            if op_token.token_type == TokenType.SEMICOLON or op_token.token_type == TokenType.EOF:
                break

            op_prec = INFIX_PRECEDENCE.get(op_token.token_type, PREC_LOWEST)
            self._advance()
            right = self.parse_expression(op_prec)
            left = BinaryOpNode(left=left, op=op_token.value, right=right)

        return left

    def parse(self) -> ASTNode:
        """Parses the entire token stream into an AST root node."""
        expr = self.parse_expression(PREC_LOWEST)
        if self._current_token().token_type == TokenType.SEMICOLON:
            self._advance()
        return expr
