from app.domain.receipt.interpretation.institution.institution import find_institution
from app.domain.receipt.interpretation.interpreter.interpreter import Interpreter
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.interpretation.validation import InterpretationValidator
from app.domain.receipt.rules.schema import ReceiptRulesSchema


class Interpretation:
    def __init__(self, rules: list[ReceiptRulesSchema], text: str) -> None:
        self.text = text
        self.institution = find_institution(text, rules)
        self.interpreter = Interpreter(rules, self.institution)
        self.interpretation_validator = InterpretationValidator()

    def result(self) -> InterpretationResult:
        data = self.interpreter.interpret(self.text)
        return self.interpretation_validator.validate(data)
