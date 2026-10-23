import pytest
from compiler.lexer import Lexer, TokenType
from compiler.parser import PrattParser
from compiler.type_checker import TypeChecker
from compiler.codegen_z3 import Z3CodeGen
from compiler.codegen_sql import SQLCodeGen
from compiler.bytecode_vm import BytecodeCompiler, VirtualMachine
from compiler.ast_nodes import BinaryOpNode, LiteralNode, VariableNode


def test_lexer_tokenization():
    code = 'IF urgency == "CRITICAL" AND hawkes_intensity > 0.85 THEN 100 ELSE 10;'
    lexer = Lexer(code)
    tokens = lexer.tokenize()

    token_types = [t.token_type for t in tokens]
    assert TokenType.IF in token_types
    assert TokenType.EQUALS in token_types
    assert TokenType.AND in token_types
    assert TokenType.GT in token_types
    assert TokenType.THEN in token_types
    assert TokenType.ELSE in token_types
    assert TokenType.EOF in token_types


def test_pratt_parser_precedence():
    code = "2 + 3 * 4 == 14 AND NOT False"
    lexer = Lexer(code)
    parser = PrattParser(lexer.tokenize())
    ast = parser.parse()

    assert isinstance(ast, BinaryOpNode)
    assert ast.op == "AND"


def test_type_checker_validation():
    checker = TypeChecker()

    # Valid expression
    code_valid = 'urgency == "CRITICAL" AND hawkes_intensity > 0.5'
    parser = PrattParser(Lexer(code_valid).tokenize())
    inferred = checker.check(parser.parse())
    assert inferred == "BOOL"


def test_codegen_z3_smtlib():
    code = 'hawkes_intensity > 0.5 AND criticality > 1.0'
    parser = PrattParser(Lexer(code).tokenize())
    ast = parser.parse()

    codegen = Z3CodeGen()
    smt2 = codegen.compile_to_smtlib(ast)
    assert "(assert" in smt2
    assert "hawkes_intensity" in smt2


def test_codegen_sql_where():
    code = 'urgency == "CRITICAL" AND hawkes_intensity > 0.8'
    parser = PrattParser(Lexer(code).tokenize())
    ast = parser.parse()

    codegen = SQLCodeGen()
    sql, params = codegen.compile(ast)

    assert "incidents.urgency = :p_1" in sql
    assert "incidents.hawkes_intensity > :p_2" in sql
    assert params["p_1"] == "CRITICAL"
    assert params["p_2"] == 0.8


def test_bytecode_vm_execution():
    code = 'IF 5 > 2 THEN "PASS" ELSE "FAIL"'
    parser = PrattParser(Lexer(code).tokenize())
    ast = parser.parse()

    compiler = BytecodeCompiler()
    instructions = compiler.compile(ast)

    vm = VirtualMachine()
    result = vm.execute(instructions, {})
    assert result == "PASS"
