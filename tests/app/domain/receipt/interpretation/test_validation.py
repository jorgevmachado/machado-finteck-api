from datetime import date
from decimal import Decimal

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import ReceiptData, DataField
from app.domain.receipt.interpretation.validation import (
    InterpretationValidator,
)


def build_data(
    *,
    payment_date_status: DataStatusEnum = DataStatusEnum.FOUND,
    paid_amount_status: DataStatusEnum = DataStatusEnum.FOUND,
    category_status: DataStatusEnum = DataStatusEnum.FOUND,
    beneficiary_status: DataStatusEnum = DataStatusEnum.FOUND,
    description_status: DataStatusEnum = DataStatusEnum.FOUND,
    source_institution_status: DataStatusEnum = DataStatusEnum.FOUND,
) -> ReceiptData:
    return ReceiptData(
        payment_date=DataField(
            value=date(2026, 9, 15),
            status=payment_date_status,
        ),
        document_amount=DataField(
            value=Decimal("100.00"),
            status=DataStatusEnum.FOUND,
        ),
        paid_amount=DataField(
            value=Decimal("95.00"),
            status=paid_amount_status,
        ),
        beneficiary=DataField(
            value="EMPRESA EXEMPLO",
            status=beneficiary_status,
        ),
        description=DataField(
            value="DESCRIÇÃO EXEMPLO",
            status=description_status,
        ),
        category=DataField(
            value="Categoria EXEMPLO",
            status=category_status,
        ),
        source_institution=DataField(
            value="Banco Exemplo",
            status=source_institution_status,
        ),
        destination_institution=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        due_date=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        discount=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        interest=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        fine=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        total_charges=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        payer=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        effective_payer=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        barcode=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        authentication=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
        transaction_id=DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        ),
    )


class TestInterpretationValidator:
    def test_validate_returns_no_errors_when_required_fields_are_found(self):
        data = build_data()

        result = InterpretationValidator.validate(data)

        assert result.data == data
        assert result.errors == []

    def test_validate_returns_error_when_payment_date_is_not_found(self):
        data = build_data(
            payment_date_status=DataStatusEnum.NOT_FOUND,
        )

        result = InterpretationValidator.validate(data)

        assert len(result.errors) == 1
        assert result.errors[0].field == "payment_date"
        assert result.errors[0].status == DataStatusEnum.NOT_FOUND

    def test_validate_returns_error_when_paid_amount_is_not_found(self):
        data = build_data(
            paid_amount_status=DataStatusEnum.NOT_FOUND,
        )

        result = InterpretationValidator.validate(data)

        assert len(result.errors) == 1
        assert result.errors[0].field == "paid_amount"
        assert result.errors[0].status == DataStatusEnum.NOT_FOUND

    def test_validate_returns_error_when_beneficiary_is_not_found(self):
        data = build_data(
            beneficiary_status=DataStatusEnum.NOT_FOUND,
        )

        result = InterpretationValidator.validate(data)

        assert len(result.errors) == 1
        assert result.errors[0].field == "beneficiary"
        assert result.errors[0].status == DataStatusEnum.NOT_FOUND

    def test_validate_returns_error_when_source_institution_is_not_found(self):
        data = build_data(
            source_institution_status=DataStatusEnum.NOT_FOUND,
        )

        result = InterpretationValidator.validate(data)

        assert len(result.errors) == 1
        assert result.errors[0].field == "source_institution"
        assert result.errors[0].status == DataStatusEnum.NOT_FOUND

    def test_validate_returns_error_when_required_field_is_ambiguous(self):
        data = build_data(
            paid_amount_status=DataStatusEnum.AMBIGUOUS,
        )

        result = InterpretationValidator.validate(data)

        assert len(result.errors) == 1
        assert result.errors[0].field == "paid_amount"
        assert result.errors[0].status == DataStatusEnum.AMBIGUOUS

    def test_validate_returns_all_required_field_errors(self):
        data = build_data(
            payment_date_status=DataStatusEnum.NOT_FOUND,
            paid_amount_status=DataStatusEnum.AMBIGUOUS,
            beneficiary_status=DataStatusEnum.NOT_FOUND,
            source_institution_status=DataStatusEnum.AMBIGUOUS,
        )

        result = InterpretationValidator.validate(data)

        assert len(result.errors) == 4

        assert result.errors[0].field == "payment_date"
        assert result.errors[0].status == DataStatusEnum.NOT_FOUND

        assert result.errors[1].field == "paid_amount"
        assert result.errors[1].status == DataStatusEnum.AMBIGUOUS

        assert result.errors[2].field == "beneficiary"
        assert result.errors[2].status == DataStatusEnum.NOT_FOUND

        assert result.errors[3].field == "source_institution"
        assert result.errors[3].status == DataStatusEnum.AMBIGUOUS

    def test_validate_ignores_invalid_optional_fields(self):
        data = build_data()

        data.due_date = DataField(
            value=None,
            status=DataStatusEnum.AMBIGUOUS,
        )
        data.destination_institution = DataField(
            value=None,
            status=DataStatusEnum.NOT_FOUND,
        )

        result = InterpretationValidator.validate(data)

        assert result.errors == []
