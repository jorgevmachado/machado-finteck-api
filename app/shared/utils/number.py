import ast
import operator as op
import re

ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}


def ensure_order_number(url: str | None) -> int:
    if not url:
        return 0
    return int(url.split("/")[-2])


def convert_latex_to_python(formula: str) -> str:
    """
    Converte fórmulas matemáticas
    (LaTeX ou notação matemática comum) para sintaxe Python válida.

    Exemplos:
    - \\frac{6x^3}{5} -> (6 * x**3) / 5
    - x^3 / 5 -> x**3 / 5
    - 5x^3 / 4 -> 5 * x**3 / 4
    - x^3 - 6x^2 + 12x - 8 -> x**3 - 6 * x**2 + 12 * x - 8
    - (5x^3) / 4 -> (5 * x**3) / 4
    """
    # 1. Converter \frac{numerador}{denominador} para (numerador) / (denominador)
    while r"\frac" in formula:
        formula = re.sub(
            r"\\frac\{([^}]+)\}\{([^}]+)\}", r"(\1) / (\2)", formula, count=1
        )

    # 2. Converter nx^m (número seguido de x com potência) para n * x^m
    # Deve ser feito ANTES de converter x^n para x**n
    formula = re.sub(r"(?<![*\w])(\d+)x\^", r"\1 * x^", formula)

    # 3. Converter x^n para x**n (potências)
    formula = re.sub(r"x\^(\d+)", r"x**\1", formula)

    # 4. Converter nx (número seguido de x SEM potência) para n * x
    # Isso pega casos como "12x" mas não "12x**2" (que já foi convertido)
    formula = re.sub(r"(?<![*\w])(\d+)x(?![*\w])", r"\1 * x", formula)

    # 5. Converter expressões com parênteses tipo (5x -> (5 * x
    formula = re.sub(r"\((\d+)x", r"(\1 * x", formula)

    # 6. Converter )x para ) * x (parêntese fechando seguido de x)
    formula = re.sub(r"\)(\d*x)", r") * \1", formula)

    return formula


def calculate_by_formula(formula: str, x: float) -> float:
    python_formula = convert_latex_to_python(formula)
    node = ast.parse(python_formula, mode="eval")
    return eval(node.body, x)


def eval(node: ast.expr, x: float) -> float:
    if isinstance(node, ast.Num):  # number
        return node.n

    if isinstance(node, ast.Name):  # variable (x)
        if node.id == "x":
            return x
        raise ValueError("Invalid variable")

    if isinstance(node, ast.BinOp):
        operator = ALLOWED_OPERATORS[type(node.op)]
        return operator(eval(node.left, x), eval(node.right, x))

    if isinstance(node, ast.UnaryOp):
        operator = ALLOWED_OPERATORS[type(node.op)]
        return operator(eval(node.operand, x))

    raise TypeError("Unsupported expression")
