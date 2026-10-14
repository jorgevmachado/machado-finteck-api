from app.shared.utils.string import is_valid_uuid, text_strip, to_snake_case


class TestStringIsValidUuid:
    @staticmethod
    def test_is_valid_uuid_valid():
        assert is_valid_uuid("123e4567-e89b-12d3-a456-426614174000")

    @staticmethod
    def test_is_valid_uuid_invalid():
        assert not is_valid_uuid("invalid-uuid")

    @staticmethod
    def test_is_valid_uuid_none():
        assert not is_valid_uuid(None)


class TestTextStrip:
    @staticmethod
    def test_text_strip():
        text = "  Hello, World!  "
        expected_text = "Hello, World!"
        result = text_strip(text)
        assert result == expected_text


class TestToSnakeCase:
    @staticmethod
    def test_to_snake_case():
        text = "Residencial Ingrid Águas claras"
        expected_text = "residencial_ingrid_aguas_claras"
        result = to_snake_case(text)
        assert result == expected_text
