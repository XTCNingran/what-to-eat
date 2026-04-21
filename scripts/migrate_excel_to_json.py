"""将 data/restaurants/ 下最新 xlsx 转换为 data/restaurants.json。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl
from app.config import RESTAURANT_DIR, RESTAURANT_JSON
from app.services.data_loader import CATEGORY_TAG_MAP, _parse_float, _parse_tags


def migrate():
    files = list(RESTAURANT_DIR.glob("*.xlsx"))
    if not files:
        print("ERROR: data/restaurants/ 下没有找到 xlsx 文件")
        sys.exit(1)

    xlsx_path = max(files, key=lambda p: p.stat().st_mtime)
    print(f"读取: {xlsx_path}")

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    headers = [str(h) if h is not None else "" for h in rows[0]]
    col = {h: i for i, h in enumerate(headers)}

    restaurants = []
    for row in rows[1:]:
        name = row[col.get("商户名称", 0)]
        if not name:
            continue
        cat_raw = str(row[col.get("细分类别", 1)] or "")
        restaurants.append({
            "name": str(name),
            "category_raw": cat_raw,
            "address": str(row[col.get("地址", 2)] or ""),
            "rating": _parse_float(row[col.get("评分", 3)]),
            "avg_spend": _parse_float(row[col.get("人均消费(元)", 4)]),
            "lng": _parse_float(row[col.get("经度", 5)]),
            "lat": _parse_float(row[col.get("纬度", 6)]),
            "district": str(row[col.get("区域", 7)] or ""),
            "poi_id": str(row[col.get("POI ID", 8)] or ""),
            "tags": _parse_tags(cat_raw),
            "phone": "",
            "vendor": 0,
            "deleted": False,
        })

    tmp = RESTAURANT_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(restaurants, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RESTAURANT_JSON)
    print(f"完成：写入 {len(restaurants)} 家餐厅 → {RESTAURANT_JSON}")


if __name__ == "__main__":
    migrate()
