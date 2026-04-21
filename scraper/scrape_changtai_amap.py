"""
上海长泰广场 500m 内餐饮商户爬取
数据来源：高德地图 POI 搜索 API
输出：Excel 文件

使用前：
  1. 前往 https://lbs.amap.com 注册并创建应用（Web服务类型）
  2. 将 API_KEY 替换为你的 Key
  3. pip install requests openpyxl
  4. python scrape_changtai_amap.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime
import time

# ===================== 配置 =====================
API_KEY = "3f085e5449b935abc83ced96fc63a4d3"   # ← 替换这里
ADDRESS = "上海长泰广场"       # 搜索的地点名称
RADIUS_M = 500                 # 搜索半径（米）
# ================================================

GEOCODE_URL  = "https://restapi.amap.com/v3/geocode/geo"
AROUND_URL   = "https://restapi.amap.com/v3/place/around"
POI_TYPE     = "050000"        # 高德 POI 分类：餐饮服务
PAGE_SIZE    = 25              # 每页最大 25 条


def geocode(address):
    """将地址转换为坐标"""
    resp = requests.get(GEOCODE_URL, params={
        "key": API_KEY, "address": address, "city": "上海"
    }, timeout=10)
    data = resp.json()
    if data.get("status") != "1" or not data.get("geocodes"):
        raise RuntimeError(f"地址解析失败: {data.get('info')}")
    location = data["geocodes"][0]["location"]
    print(f"地址解析成功：{address} → {location}")
    return location  # "lng,lat"


def search_around(location, page=1):
    """搜索指定坐标周边的餐饮 POI"""
    resp = requests.get(AROUND_URL, params={
        "key":        API_KEY,
        "location":   location,
        "types":      POI_TYPE,
        "radius":     RADIUS_M,
        "offset":     PAGE_SIZE,
        "page":       page,
        "extensions": "all",
        "output":     "json",
    }, timeout=10)
    return resp.json()


def get_all_pois(location):
    all_pois = []
    page = 1
    while True:
        data = search_around(location, page)
        if data.get("status") != "1":
            print(f"API 错误: {data.get('info')}")
            break
        pois = data.get("pois", [])
        if not pois:
            break
        all_pois.extend(pois)
        total = int(data.get("count", 0))
        print(f"  已获取 {len(all_pois)} / {total} 条...")
        if len(all_pois) >= total:
            break
        page += 1
        time.sleep(0.3)
    return all_pois


def parse_poi(poi):
    biz = poi.get("biz_ext") or {}
    photos = poi.get("photos") or []
    photo_url = photos[0].get("url", "") if photos else ""
    loc = poi.get("location", ",").split(",")
    return {
        "商户名称":    poi.get("name", ""),
        "细分类别":    poi.get("type", ""),
        "地址":        poi.get("address", ""),
        "评分":        biz.get("rating", ""),
        "人均消费(元)": biz.get("cost", ""),
        "经度":        loc[0] if len(loc) > 1 else "",
        "纬度":        loc[1] if len(loc) > 1 else "",
        "区域":        poi.get("adname", ""),
        "POI ID":      poi.get("id", ""),
        "图片":        photo_url,
    }


def save_excel(rows, filename):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "长泰广场餐饮商户"

    # 样式
    hdr_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    hdr_font = Font(color="FFFFFF", bold=True, size=11)
    thin     = Side(style="thin", color="BFBFBF")
    border   = Border(left=thin, right=thin, top=thin, bottom=thin)
    even_fill = PatternFill(start_color="EBF3FB", end_color="EBF3FB", fill_type="solid")
    center   = Alignment(horizontal="center", vertical="center")

    headers = list(rows[0].keys())
    ws.row_dimensions[1].height = 28

    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = center
        cell.border = border

    for r, row in enumerate(rows, 2):
        ws.row_dimensions[r].height = 18
        for c, key in enumerate(headers, 1):
            val = row.get(key, "")
            if isinstance(val, list):
                val = "、".join(str(v) for v in val)
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = Font(size=10)
            cell.border = border
            cell.alignment = Alignment(vertical="center")
            if r % 2 == 0:
                cell.fill = even_fill

    col_widths = {
        "商户名称": 28, "细分类别": 20, "地址": 38,
        "评分": 8, "人均消费(元)": 12,
        "经度": 12, "纬度": 12, "区域": 14, "POI ID": 22, "图片": 40,
    }
    for c, h in enumerate(headers, 1):
        ws.column_dimensions[ws.cell(1, c).column_letter].width = col_widths.get(h, 14)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # 说明页
    ws2 = wb.create_sheet("说明")
    for r, (text, bold) in enumerate([
        ("数据说明", True), ("", False),
        (f"搜索地点：{ADDRESS}", False),
        (f"搜索半径：{RADIUS_M} 米", False),
        (f"数据来源：高德地图 POI 搜索 API", False),
        (f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", False),
        (f"商户总数：{len(rows)} 条", False),
        ("", False),
        ("关于 SAP Vendor Code 核对", True),
        ("本表仅为餐饮商户信息汇总，是否可使用 Vendor Code", False),
        ("需结合公司内部 SAP 采购系统另行核对。", False),
    ], 1):
        cell = ws2.cell(row=r, column=1, value=text)
        cell.font = Font(bold=bold, size=11 if bold else 10)
    ws2.column_dimensions["A"].width = 55

    wb.save(filename)


def main():
    print(f"=== 高德地图餐饮爬取：{ADDRESS} 半径 {RADIUS_M}m ===\n")

    try:
        location = geocode(ADDRESS)
    except RuntimeError as e:
        print(e)
        return

    print(f"\n开始搜索周边餐饮...")
    pois = get_all_pois(location)
    print(f"\n共获取 {len(pois)} 条原始数据")

    rows = [parse_poi(p) for p in pois]
    # 按距离排序
    rows.sort(key=lambda x: x["商户名称"])

    if not rows:
        print("未获取到数据，请检查 API Key 是否正确。")
        return

    filename = f"长泰广场餐饮商户_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    save_excel(rows, filename)
    print(f"\n已保存：{filename}（共 {len(rows)} 条）")


if __name__ == "__main__":
    main()
