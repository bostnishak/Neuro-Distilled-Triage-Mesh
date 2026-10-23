from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from compiler.ast_nodes import (
    ASTNode,
    LiteralNode,
    VariableNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
    IfThenElseNode,
)


class OpCode(Enum):
    LOAD_CONST = auto()
    LOAD_VAR = auto()
    STORE_VAR = auto()
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    CMP_EQ = auto()
    CMP_NEQ = auto()
    CMP_LT = auto()
    CMP_LTE = auto()
    CMP_GT = auto()
    CMP_GTE = auto()
    LOGIC_AND = auto()
    LOGIC_OR = auto()
    LOGIC_NOT = auto()
    JUMP = auto()
    JUMP_IF_FALSE = auto()
    CALL_BUILTIN = auto()
    HALT = auto()


@dataclass
class Instruction:
    opcode: OpCode
    arg: Any = None


class BytecodeCompiler:
    """Compiles AST into linear stack bytecode instructions."""

    def __init__(self):
        self.instructions: List[Instruction] = []

    def compile(self, root: ASTNode) -> List[Instruction]:
        self.instructions.clear()
        self._emit_node(root)
        self.instructions.append(Instruction(OpCode.HALT))
        return list(self.instructions)

    def _emit(self, opcode: OpCode, arg: Any = None) -> int:
        idx = len(self.instructions)
        self.instructions.append(Instruction(opcode, arg))
        return idx

    def _emit_node(self, node: ASTNode) -> None:
        if isinstance(node, LiteralNode):
            self._emit(OpCode.LOAD_CONST, node.value)

        elif isinstance(node, VariableNode):
            self._emit(OpCode.LOAD_VAR, node.name)

        elif isinstance(node, UnaryOpNode):
            self._emit_node(node.operand)
            if node.op == "NOT":
                self._emit(OpCode.LOGIC_NOT)
            elif node.op == "-":
                self._emit(OpCode.LOAD_CONST, -1)
                self._emit(OpCode.MUL)

        elif isinstance(node, BinaryOpNode):
            self._emit_node(node.left)
            self._emit_node(node.right)

            op_map = {
                "+": OpCode.ADD,
                "-": OpCode.SUB,
                "*": OpCode.MUL,
                "/": OpCode.DIV,
                "==": OpCode.CMP_EQ,
                "!=": OpCode.CMP_NEQ,
                "<": OpCode.CMP_LT,
                "<=": OpCode.CMP_LTE,
                ">": OpCode.CMP_GT,
                ">=": OpCode.CMP_GTE,
                "AND": OpCode.LOGIC_AND,
                "OR": OpCode.LOGIC_OR,
            }
            if node.op in op_map:
                self._emit(op_map[node.op])
            else:
                raise ValueError(f"Unknown binary op: {node.op}")

        elif isinstance(node, IfThenElseNode):
            self._emit_node(node.condition)
            jump_false_idx = self._emit(OpCode.JUMP_IF_FALSE, 0)
            self._emit_node(node.then_branch)

            if node.else_branch:
                jump_end_idx = self._emit(OpCode.JUMP, 0)
                # Patch jump_false_idx to current pos (start of else)
                self.instructions[jump_false_idx].arg = len(self.instructions)
                self._emit_node(node.else_branch)
                # Patch jump_end_idx to end
                self.instructions[jump_end_idx].arg = len(self.instructions)
            else:
                self.instructions[jump_false_idx].arg = len(self.instructions)

        elif isinstance(node, FunctionCallNode):
            for arg in node.args:
                self._emit_node(arg)
            self._emit(OpCode.CALL_BUILTIN, (node.func_name, len(node.args)))


class VirtualMachine:
    """High-speed stack-based virtual machine evaluating NDTM bytecode."""

    def __init__(self):
        self.stack: List[Any] = []
        self.env: Dict[str, Any] = {}

    def execute(self, instructions: List[Instruction], environment: Dict[str, Any]) -> Any:
        self.stack.clear()
        self.env = dict(environment)
        ip = 0
        limit = len(instructions)

        while ip < limit:
            inst = instructions[ip]

            if inst.opcode == OpCode.HALT:
                break

            elif inst.opcode == OpCode.LOAD_CONST:
                self.stack.append(inst.arg)

            elif inst.opcode == OpCode.LOAD_VAR:
                val = self.env.get(inst.arg, None)
                self.stack.append(val)

            elif inst.opcode == OpCode.STORE_VAR:
                val = self.stack.pop()
                self.env[inst.arg] = val

            elif inst.opcode == OpCode.ADD:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a + b)

            elif inst.opcode == OpCode.SUB:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a - b)

            elif inst.opcode == OpCode.MUL:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a * b)

            elif inst.opcode == OpCode.DIV:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a / b if b != 0 else 0.0)

            elif inst.opcode == OpCode.CMP_EQ:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a == b)

            elif inst.opcode == OpCode.CMP_NEQ:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a != b)

            elif inst.opcode == OpCode.CMP_LT:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a < b)

            elif inst.opcode == OpCode.CMP_LTE:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a <= b)

            elif inst.opcode == OpCode.CMP_GT:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a > b)

            elif inst.opcode == OpCode.CMP_GTE:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(a >= b)

            elif inst.opcode == OpCode.LOGIC_AND:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(bool(a and b))

            elif inst.opcode == OpCode.LOGIC_OR:
                b = self.stack.pop()
                a = self.stack.pop()
                self.stack.append(bool(a or b))

            elif inst.opcode == OpCode.LOGIC_NOT:
                a = self.stack.pop()
                self.stack.append(not bool(a))

            elif inst.opcode == OpCode.JUMP:
                ip = inst.arg
                continue

            elif inst.opcode == OpCode.JUMP_IF_FALSE:
                cond = self.stack.pop()
                if not bool(cond):
                    ip = inst.arg
                    continue

            elif inst.opcode == OpCode.CALL_BUILTIN:
                func_name, arity = inst.arg
                args = [self.stack.pop() for _ in range(arity)][::-1]
                res = self._execute_builtin(func_name, args)
                self.stack.append(res)

            ip += 1

        return self.stack[-1] if self.stack else None

    def _execute_builtin(self, name: str, args: List[Any]) -> Any:
        if name == "WITHIN_METERS":
            # (loc1, loc2, max_dist) -> bool
            # locs can be tuple (lat, lon)
            p1, p2, max_dist = args
            if isinstance(p1, (tuple, list)) and isinstance(p2, (tuple, list)):
                import math
                R = 6371000.0
                phi1, phi2 = math.radians(p1[0]), math.radians(p2[0])
                dphi = math.radians(p2[0] - p1[0])
                dlam = math.radians(p2[1] - p1[1])
                a = math.sin(dphi / 2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam / 2)**2
                dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                return dist <= max_dist
            return False
        return True
