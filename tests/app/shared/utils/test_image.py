from app.shared.utils.image import ensure_external_image


class TestImageEnsureExternalImage:
    @staticmethod
    def test_ensure_external_image_should_pad_single_digit_order():
        image = "https://www.pokemon.com/static-assets/content-assets/cms2/img/pokedex/detail/001.png"
        assert ensure_external_image(1) == image

    @staticmethod
    def test_ensure_external_image_should_pad_three_as_four_digits():
        image = "https://www.pokemon.com/static-assets/content-assets/cms2/img/pokedex/detail/003.png"
        assert ensure_external_image(3) == image

    @staticmethod
    def test_ensure_external_image_should_pad_two_digit_order():
        image = "https://www.pokemon.com/static-assets/content-assets/cms2/img/pokedex/detail/085.png"
        assert ensure_external_image(85) == image

    @staticmethod
    def test_ensure_external_image_should_pad_three_digit_order():
        image = "https://www.pokemon.com/static-assets/content-assets/cms2/img/pokedex/detail/101.png"
        assert ensure_external_image(101) == image

    @staticmethod
    def test_ensure_external_image_should_keep_four_digit_order():
        image = "https://www.pokemon.com/static-assets/content-assets/cms2/img/pokedex/detail/1011.png"
        assert ensure_external_image(1011) == image

    @staticmethod
    def test_ensure_external_image_not_has_order():
        assert not ensure_external_image(None)
