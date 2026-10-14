POKEMON_EXTERNAL_IMAGE_URL = "https://www.pokemon.com/static-assets/content-assets/cms2/img/pokedex/detail/{order}.png"


def ensure_external_image(
    order: int | str | None, url: str = POKEMON_EXTERNAL_IMAGE_URL
) -> str:
    if not order:
        return ""
    formatted_order = str(int(order)).zfill(3)
    return url.format(order=formatted_order)
