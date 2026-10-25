"""题面使用矢量清晰图；提交批改仍使用原有 PNG 字段。"""
from pathlib import Path

from ..database import DATA_DIR


def chart_assets(image: str):
    if not image or not image.startswith("charts/") or ".." in image:
        return {}
    relative = Path(image)
    vector = relative.with_suffix(".svg").as_posix()
    original = (relative.parent / "originals" / relative.name).as_posix()
    result = {}
    if (Path(DATA_DIR) / vector).is_file():
        result["chart_display_image"] = vector
    if (Path(DATA_DIR) / original).is_file():
        result["chart_original_image"] = original
    return result
