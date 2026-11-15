"""商品图片背景移除、纯白画布合成与抠图降级测试。"""

import io

from PIL import Image, ImageDraw

from app.services.image_processing import create_white_background_image


def test_white_background_uses_removed_subject_on_pure_white_canvas():
    """背景移除后应把主体合成到纯白画布，而不是保留原摄影棚背景。"""

    source = Image.new("RGB", (100, 100), (210, 212, 214))
    source_bytes = io.BytesIO()
    source.save(source_bytes, format="PNG")
    calls: list[bytes] = []

    def remove_background(raw: bytes) -> bytes:
        calls.append(raw)
        cutout = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cutout)
        draw.rectangle((25, 25, 75, 75), fill=(196, 32, 45, 255))
        output = io.BytesIO()
        cutout.save(output, format="PNG")
        return output.getvalue()

    result = create_white_background_image(
        source_bytes.getvalue(),
        200,
        200,
        margin_ratio=0.05,
        background_remover=remove_background,
    )

    image = Image.open(io.BytesIO(result)).convert("RGB")
    assert calls == [source_bytes.getvalue()]
    assert image.size == (200, 200)
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((199, 199)) == (255, 255, 255)
    assert image.getpixel((100, 100))[0] > 150
    assert image.getpixel((100, 100))[1] < 100


def _plain_product_bytes() -> bytes:
    image = Image.new("RGB", (240, 180), (245, 242, 236))
    for x in range(70, 170):
        for y in range(45, 135):
            image.putpixel((x, y), (190, 55, 42))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_white_background_uses_local_fallback_when_rembg_is_unavailable(
    monkeypatch,
):
    import app.services.image_processing as image_processing

    def unavailable(_source: bytes) -> bytes:
        raise ValueError("rembg unavailable")

    monkeypatch.setattr(
        image_processing,
        "_remove_background_with_u2net",
        unavailable,
    )

    result = create_white_background_image(
        _plain_product_bytes(),
        400,
        400,
    )

    with Image.open(io.BytesIO(result)) as output:
        rgba = output.convert("RGBA")
        assert rgba.getpixel((5, 5))[:3] == (255, 255, 255)
        # 商品主体仍应保留在画布中心。
        center = rgba.getpixel((200, 200))
        assert center[0] > center[1]
        assert center[0] > center[2]
