import ast

import pytest

from app.shared.utils.number import (
    calculate_by_formula,
    convert_latex_to_python,
    ensure_order_number,
)
from app.shared.utils.number import (
    eval as eval_expression,
)


class TestNumberEnsureOrderNumber:
    @staticmethod
    def test_ensure_order_number():
        test_cases = [
            ("https://pokeapi.co/api/v2/pokemon/1/", 1),
            ("https://pokeapi.co/api/v2/pokemon/2/", 2),
            ("https://pokeapi.co/api/v2/pokemon/3/", 3),
            ("https://pokeapi.co/api/v2/pokemon/4/", 4),
            ("https://pokeapi.co/api/v2/pokemon/5/", 5),
        ]

        for url, expected_order in test_cases:
            assert ensure_order_number(url) == expected_order

    @staticmethod
    def test_ensure_order_number_not_has_url():
        url = None
        assert ensure_order_number(url) == 0


class TestNumberConvertLatexToPython:
    """Test scope for convert latex to python method"""

    @staticmethod
    def test_convert_latex_frac_simple():
        """Should convert simple latex fraction"""
        formula = r"\frac{6x^3}{5}"
        result = convert_latex_to_python(formula)
        expected = "(6 * x**3) / (5)"
        assert result == expected

    @staticmethod
    def test_convert_latex_complex_formula():
        """Should convert complex latex formula"""
        formula = r"\frac{6x^3}{5} - 15x^2 + 100x - 140"
        result = convert_latex_to_python(formula)
        # Deve conter os elementos convertidos
        assert "x**3" in result
        assert "x**2" in result
        assert "15 * x**2" in result or "15*x**2" in result
        assert "100 * x" in result or "100*x" in result

    @staticmethod
    def test_convert_simple_power():
        """Should convert simple power notation"""
        formula = "x^3"
        result = convert_latex_to_python(formula)
        assert result == "x**3"

    @staticmethod
    def test_convert_medium_slow_formula():
        """Should convert medium-slow formula: x^3 - 6x^2 + 12x - 8"""
        formula = "x^3 - 6x^2 + 12x - 8"
        result = convert_latex_to_python(formula)
        expected = "x**3 - 6 * x**2 + 12 * x - 8"
        assert result == expected

    @staticmethod
    def test_convert_slow_formula():
        """Should convert slow formula: (5x^3) / 4"""
        formula = "(5x^3) / 4"
        result = convert_latex_to_python(formula)
        assert "x**3" in result
        assert "5 * x" in result

    @staticmethod
    def test_convert_fast_formula():
        """Should convert fast formula: x^3 / 5"""
        formula = "x^3 / 5"
        result = convert_latex_to_python(formula)
        assert result == "x**3 / 5"


class TestNumberCalculateByFormula:
    """Test scope for calculate_by_formula function"""

    @staticmethod
    def test_calculate_simple_power():
        """Should calculate x^3"""
        result_value = 125
        formula = "x^3"
        result = calculate_by_formula(formula, 5)
        assert result == result_value

    @staticmethod
    def test_calculate_simple_power_level_1():
        """Should calculate x^3 for level 1"""
        result_value = 1
        formula = "x^3"
        result = calculate_by_formula(formula, 1)
        assert result == result_value

    @staticmethod
    def test_calculate_simple_power_level_2():
        """Should calculate x^3 for level 2"""
        result_value = 8
        formula = "x^3"
        result = calculate_by_formula(formula, 2)
        assert result == result_value

    @staticmethod
    def test_calculate_simple_power_level_10():
        """Should calculate x^3 for level 10"""
        result_value = 1000
        formula = "x^3"
        result = calculate_by_formula(formula, 10)
        assert result == result_value

    @staticmethod
    def test_calculate_fraction_formula():
        """Should calculate fraction formula: x^3 / 5"""
        result_value = 25
        formula = "x^3 / 5"
        result = calculate_by_formula(formula, 5)
        assert result == result_value

    @staticmethod
    def test_calculate_latex_fraction():
        """Should calculate latex fraction: \\frac{6x^3}{5}"""
        formula = r"\frac{6x^3}{5}"
        result = calculate_by_formula(formula, 5)
        expected = (6 * 5**3) / 5
        assert result == expected

    @staticmethod
    def test_calculate_medium_slow_formula():
        """Should calculate medium-slow formula: x^3 - 6x^2 + 12x - 8"""
        formula = "x^3 - 6x^2 + 12x - 8"
        result = calculate_by_formula(formula, 5)
        expected = 5**3 - 6 * 5**2 + 12 * 5 - 8
        assert result == expected

    @staticmethod
    def test_calculate_slow_formula():
        """Should calculate slow formula: (5x^3) / 4"""
        formula = "(5x^3) / 4"
        result = calculate_by_formula(formula, 4)
        expected = (5 * 4**3) / 4
        assert result == expected

    @staticmethod
    def test_calculate_complex_formula_level_1():
        """Should calculate complex formula for level 1"""
        formula = r"\frac{6x^3}{5} - 15x^2 + 100x - 140"
        result = calculate_by_formula(formula, 1)
        expected = (6 * 1**3) / 5 - 15 * 1**2 + 100 * 1 - 140
        assert result == expected

    @staticmethod
    def test_calculate_addition():
        """Should calculate simple addition"""
        result_value = 15
        formula = "x + 5"
        result = calculate_by_formula(formula, 10)
        assert result == result_value

    @staticmethod
    def test_calculate_subtraction():
        """Should calculate simple subtraction"""
        result_value = 7
        formula = "x - 3"
        result = calculate_by_formula(formula, 10)
        assert result == result_value

    @staticmethod
    def test_calculate_multiplication():
        """Should calculate simple multiplication"""
        result_value = 10
        formula = "x * 2"
        result = calculate_by_formula(formula, 5)
        assert result == result_value

    @staticmethod
    def test_calculate_division():
        """Should calculate simple division"""
        result_value = 5
        formula = "x / 2"
        result = calculate_by_formula(formula, 10)
        assert result == result_value

    @staticmethod
    def test_calculate_float_result():
        """Should return float result"""
        formula = "x / 3"
        result = calculate_by_formula(formula, 10)
        assert isinstance(result, float)
        assert result == 10 / 3

    @staticmethod
    def test_calculate_zero_x():
        """Should calculate with x = 0"""
        result_value = 5
        formula = "x^3 + 5"
        result = calculate_by_formula(formula, 0)
        assert result == result_value

    @staticmethod
    def test_calculate_negative_x():
        """Should calculate with negative x"""
        result_value = 25
        formula = "x^2"
        result = calculate_by_formula(formula, -5)
        assert result == result_value

    @staticmethod
    def test_calculate_unary_negation():
        """Should handle unary negation"""
        result_value = -5
        formula = "-x"
        result = calculate_by_formula(formula, 5)
        assert result == result_value

    @staticmethod
    def test_calculate_with_parentheses():
        """Should calculate with parentheses"""
        result_value = 18
        formula = "(x + 2) * 3"
        result = calculate_by_formula(formula, 4)
        assert result == result_value

    @staticmethod
    def test_calculate_order_of_operations():
        """Should respect order of operations"""
        result_value = 17
        formula = "2 + 3 * x"
        result = calculate_by_formula(formula, 5)
        assert result == result_value

    @staticmethod
    def test_calculate_multiple_operations():
        """Should handle multiple operations"""
        formula = "2 * x + 3 * x - 1"
        result = calculate_by_formula(formula, 4)
        expected = 2 * 4 + 3 * 4 - 1
        assert result == expected


class TestNumberEval:
    """Test scope for eval function"""

    @staticmethod
    def test_eval_number_node():
        """Should evaluate numeric literals"""
        result_value = 5
        # Parse "5" and evaluate
        node = ast.parse("5", mode="eval")
        result = eval_expression(node.body, 0)
        assert result == result_value

    @staticmethod
    def test_eval_variable_x():
        """Should evaluate variable x"""
        result_value = 10
        node = ast.parse("x", mode="eval")
        result = eval_expression(node.body, result_value)
        assert result == result_value

    @staticmethod
    def test_eval_variable_x_different_values():
        """Should return different values for different x"""
        result_value_5 = 5
        result_value_20 = 20
        node = ast.parse("x", mode="eval")
        assert eval_expression(node.body, result_value_5) == result_value_5
        assert eval_expression(node.body, result_value_20) == result_value_20
        assert eval_expression(node.body, 0) == 0

    @staticmethod
    def test_eval_addition():
        """Should evaluate addition"""
        result_value = 15
        node = ast.parse("x + 5", mode="eval")
        result = eval_expression(node.body, 10)
        assert result == result_value

    @staticmethod
    def test_eval_subtraction():
        """Should evaluate subtraction"""
        result_value = 7
        node = ast.parse("x - 3", mode="eval")
        result = eval_expression(node.body, 10)
        assert result == result_value

    @staticmethod
    def test_eval_multiplication():
        """Should evaluate multiplication"""
        result_value = 10
        node = ast.parse("x * 2", mode="eval")
        result = eval_expression(node.body, 5)
        assert result == result_value

    @staticmethod
    def test_eval_division():
        """Should evaluate division"""
        result_value = 5
        node = ast.parse("x / 2", mode="eval")
        result = eval_expression(node.body, 10)
        assert result == result_value

    @staticmethod
    def test_eval_power():
        """Should evaluate power operation"""
        result_value = 8
        node = ast.parse("x ** 3", mode="eval")
        result = eval_expression(node.body, 2)
        assert result == result_value

    @staticmethod
    def test_eval_power_with_zero():
        """Should evaluate x ** 0"""
        result_value = 1
        node = ast.parse("x ** 0", mode="eval")
        result = eval_expression(node.body, 100)
        assert result == result_value

    @staticmethod
    def test_eval_complex_binary_operation():
        """Should evaluate complex binary operations"""
        result_value = 13
        node = ast.parse("2 * x + 3", mode="eval")
        result = eval_expression(node.body, 5)
        assert result == result_value  # 2 * 5 + 3

    @staticmethod
    def test_eval_nested_operations():
        """Should evaluate nested operations"""
        result_value = 18
        node = ast.parse("(x + 2) * 3", mode="eval")
        result = eval_expression(node.body, 4)
        assert result == result_value  # (4 + 2) * 3

    @staticmethod
    def test_eval_multiple_additions():
        """Should evaluate multiple additions"""
        result_value = 15
        node = ast.parse("x + x + x", mode="eval")
        result = eval_expression(node.body, 5)
        assert result == result_value

    @staticmethod
    def test_eval_unary_negation():
        """Should evaluate unary negation"""
        result_value = 5
        node = ast.parse("-x", mode="eval")
        result = eval_expression(node.body, result_value)
        assert result == -result_value

    @staticmethod
    def test_eval_unary_negation_with_zero():
        """Should evaluate unary negation with zero"""

        node = ast.parse("-x", mode="eval")
        result = eval_expression(node.body, 0)
        assert result == 0

    @staticmethod
    def test_eval_double_negation():
        """Should evaluate double negation"""
        result_value = 5
        node = ast.parse("--x", mode="eval")
        result = eval_expression(node.body, result_value)
        assert result == result_value

    @staticmethod
    def test_eval_negation_in_expression():
        """Should evaluate negation in expression"""
        result_value = 5
        node = ast.parse("-x + 10", mode="eval")
        result = eval_expression(node.body, result_value)
        assert result == result_value  # -5 + 10

    @staticmethod
    def test_eval_order_of_operations():
        """Should respect order of operations"""
        result_value = 17
        node = ast.parse("2 + 3 * x", mode="eval")
        result = eval_expression(node.body, 5)
        assert result == result_value  # 2 + (3 * 5)

    @staticmethod
    def test_eval_division_with_integers():
        """Should return float for division"""
        result_value = 0.0001
        node = ast.parse("x / 3", mode="eval")
        result = eval_expression(node.body, 10)
        assert isinstance(result, float)
        assert abs(result - 10 / 3) < result_value

    @staticmethod
    def test_eval_power_with_large_number():
        """Should evaluate power with large numbers"""
        result_value = 10000
        node = ast.parse("x ** 2", mode="eval")
        result = eval_expression(node.body, 100)
        assert result == result_value

    @staticmethod
    def test_eval_with_float_x():
        """Should evaluate with float x value"""
        result_value = 5
        node = ast.parse("x * 2", mode="eval")
        result = eval_expression(node.body, 2.5)
        assert result == result_value


class TestNumberEvalPt2:
    @staticmethod
    def test_eval_complex_formula_with_multiple_operators():
        """Should evaluate complex formula"""

        node = ast.parse("x ** 3 - 6 * x ** 2 + 12 * x - 8", mode="eval")
        result = eval_expression(node.body, 5)
        expected = 5**3 - 6 * 5**2 + 12 * 5 - 8
        assert result == expected

    @staticmethod
    def test_eval_expression_with_parentheses():
        """Should evaluate expression with parentheses"""

        node = ast.parse("(x + 2) * (x - 1)", mode="eval")
        result = eval_expression(node.body, 5)
        expected = (5 + 2) * (5 - 1)
        assert result == expected

    @staticmethod
    def test_eval_division_zero_numerator():
        """Should evaluate 0 / x"""

        node = ast.parse("0 / x", mode="eval")
        result = eval_expression(node.body, 5)
        assert result == 0

    @staticmethod
    def test_eval_power_zero_base():
        """Should evaluate 0 ** x"""

        node = ast.parse("0 ** x", mode="eval")
        result = eval_expression(node.body, 5)
        assert result == 0

    @staticmethod
    def test_eval_subtraction_resulting_in_negative():
        """Should evaluate subtraction resulting in negative"""
        result_value = -90
        node = ast.parse("x - 100", mode="eval")
        result = eval_expression(node.body, 10)
        assert result == result_value


class TestNumberEvalErrors:
    """Test scope for eval function error handling"""

    @staticmethod
    def test_eval_invalid_variable_raises_error():
        """Should raise ValueError for invalid variable names"""
        node = ast.parse("y + 5", mode="eval")
        with pytest.raises(ValueError, match="Invalid variable"):
            eval_expression(node.body, 10)

    @staticmethod
    def test_eval_invalid_variable_z_raises_error():
        """Should raise ValueError for undefined variable z"""
        node = ast.parse("z * 2", mode="eval")
        with pytest.raises(ValueError, match="Invalid variable"):
            eval_expression(node.body, 5)

    @staticmethod
    def test_eval_invalid_variable_in_expression():
        """Should raise ValueError when invalid variable appears in expression"""
        node = ast.parse("x + y", mode="eval")
        with pytest.raises(ValueError, match="Invalid variable"):
            eval_expression(node.body, 10)

    @staticmethod
    def test_eval_invalid_variable_in_complex_expression():
        """Should raise ValueError for invalid variable in complex formula"""
        node = ast.parse("(x ** 2) + (a * 3)", mode="eval")
        with pytest.raises(ValueError, match="Invalid variable"):
            eval_expression(node.body, 5)

    @staticmethod
    def test_eval_unsupported_expression_raises_error():
        """Should raise TypeError for unsupported expression types"""
        # ast.List is not supported in eval
        node = ast.parse("[1, 2, 3]", mode="eval")
        with pytest.raises(TypeError, match="Unsupported expression"):
            eval_expression(node.body, 0)

    @staticmethod
    def test_eval_unsupported_dict_expression_raises_error():
        """Should raise TypeError for dict expressions"""
        node = ast.parse('{"key": 1}', mode="eval")
        with pytest.raises(TypeError, match="Unsupported expression"):
            eval_expression(node.body, 0)
