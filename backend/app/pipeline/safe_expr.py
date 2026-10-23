"""Whitelisted expression evaluator for rule packs.

Rule expressions are data written by administrators, so they are parsed with ``ast`` and walked
node-by-node. Only arithmetic, comparisons, boolean logic, names supplied by the engine and a few
pure functions are allowed. No attribute access, subscripts, lambdas, comprehensions or ``eval``.
"""
from __future__ import annotations

import ast
import math
import operator
from datetime import date
from typing import Any, Callable

_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}
_CMPOPS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_UNARY: dict[type, Callable[[Any], Any]] = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}


def _days_between(a: date, b: date) -> int:
    return (b - a).days


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs, "min": min, "max": max, "round": round, "ceil": math.ceil, "floor": math.floor,
    "days_between": _days_between,
}

MAX_EXPR_LEN = 300


class ExpressionError(ValueError):
    pass


def validate(expr: str, allowed_names: set[str]) -> ast.Expression:
    if len(expr) > MAX_EXPR_LEN:
        raise ExpressionError("expression too long")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"syntax error: {exc.msg}") from None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.BinOp, ast.UnaryOp, ast.Compare,
                             ast.Constant, ast.Load, ast.IfExp)):
            continue
        if type(node) in _BINOPS or type(node) in _CMPOPS or type(node) in _UNARY:
            continue
        if isinstance(node, ast.Name):
            if node.id not in allowed_names and node.id not in FUNCTIONS:
                raise ExpressionError(f"unknown name '{node.id}'")
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise ExpressionError("only whitelisted function calls are allowed")
            continue
        raise ExpressionError(f"disallowed syntax: {type(node).__name__}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str, bool)):
            raise ExpressionError("disallowed constant")
    return tree


def evaluate(expr: str, variables: dict[str, Any]) -> Any:
    tree = validate(expr, set(variables))
    return _eval(tree.body, variables)


def _eval(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env[node.id] if node.id in env else FUNCTIONS[node.id]
    if isinstance(node, ast.BinOp):
        return _BINOPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for v in node.values:
                result = _eval(v, env)
                if not result:
                    return result
            return result
        result = False
        for v in node.values:
            result = _eval(v, env)
            if result:
                return result
        return result
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, env)
            if not _CMPOPS[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval(node.body, env) if _eval(node.test, env) else _eval(node.orelse, env)
    if isinstance(node, ast.Call):
        fn = FUNCTIONS[node.func.id]  # type: ignore[attr-defined]
        return fn(*[_eval(a, env) for a in node.args])
    raise ExpressionError(f"cannot evaluate {type(node).__name__}")
