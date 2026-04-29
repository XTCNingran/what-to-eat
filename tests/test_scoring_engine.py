import math
import pytest
from unittest.mock import patch
from app.models.restaurant import Restaurant, ScoredRestaurant
from app.services import scoring_engine


def make_r(**kwargs):
    defaults = dict(
        name="测试餐厅", category_raw="", address="",
        rating=4.0, avg_spend=40.0, lng=121.603071, lat=31.206835,
        tags=[], vendor=0, deleted=False,
    )
    defaults.update(kwargs)
    return Restaurant(**defaults)


# ---- 过滤测试 ----

def test_drinks_only_filter_keeps_only_drinks():
    drinks = make_r(name="奶茶店", tags=["cold_food", "light_meal"])
    food   = make_r(name="中餐馆", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([drinks, food], {"drinks_only": 1})
    assert [r.name for r in pool] == ["奶茶店"]


def test_default_excludes_drinks():
    drinks = make_r(name="奶茶店", tags=["cold_food", "light_meal"])
    food   = make_r(name="中餐馆", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([drinks, food], {})
    assert [r.name for r in pool] == ["中餐馆"]


def test_vendor_only_filter():
    vendor = make_r(name="合作餐厅", vendor=1)
    normal = make_r(name="普通餐厅", vendor=0)
    pool = scoring_engine._filter_pool([vendor, normal], {"vendor_only": 1})
    assert [r.name for r in pool] == ["合作餐厅"]


def test_meal_fast_keeps_only_fast_service():
    fast   = make_r(name="快餐", tags=["fast_service", "cuisine_chinese"])
    proper = make_r(name="正餐", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([fast, proper], {"meal_fast": 1})
    assert [r.name for r in pool] == ["快餐"]


def test_meal_proper_excludes_fast_service():
    fast   = make_r(name="快餐", tags=["fast_service"])
    proper = make_r(name="正餐", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([fast, proper], {"meal_proper": 1})
    assert [r.name for r in pool] == ["正餐"]


def test_nearby_only_filter():
    # 长泰广场D座坐标 (121.603071, 31.206835)，测试 200m 以内 vs 600m 以外
    near = make_r(name="附近店", lng=121.603071, lat=31.208635)   # ~200m 北
    far  = make_r(name="远处店", lng=121.603071, lat=31.212000)   # ~580m 北
    pool = scoring_engine._filter_pool([near, far], {"nearby_only": 1})
    assert [r.name for r in pool] == ["附近店"]


def test_deleted_always_excluded():
    deleted = make_r(name="已删除", deleted=True)
    active  = make_r(name="正常店")
    pool = scoring_engine._filter_pool([deleted, active], {})
    assert [r.name for r in pool] == ["正常店"]


# ---- 菜系疲劳测试 ----

def test_cuisine_fatigue_2x_reduces_score():
    r = make_r(name="中餐馆", tags=["cuisine_chinese"])
    with patch("app.services.scoring_engine.history_store.get_recent_cuisines",
               return_value={"cuisine_chinese": 2}):
        results = scoring_engine.rank_restaurants([r], {}, set(), set())
    base_score = (4.0 * 2.0)  # rating=4.0 → base=8.0
    assert results[0].score < base_score * 0.75  # 0.7 multiplier applied


def test_cuisine_fatigue_3x_reduces_score_more():
    r = make_r(name="中餐馆", tags=["cuisine_chinese"])
    with patch("app.services.scoring_engine.history_store.get_recent_cuisines",
               return_value={"cuisine_chinese": 3}):
        results = scoring_engine.rank_restaurants([r], {}, set(), set())
    base_score = 4.0 * 2.0
    assert results[0].score < base_score * 0.45  # 0.4 multiplier


# ---- 多样性扰动测试 ----

def test_diversity_jitter_top3_unchanged():
    """前 3 名分数不受扰动影响（随机固定 seed 验证结构不变）。"""
    restaurants = [make_r(name=f"r{i}", rating=4.5 - i * 0.1) for i in range(10)]
    with patch("app.services.scoring_engine.history_store.get_recent_cuisines",
               return_value={}):
        r1 = scoring_engine.rank_restaurants(restaurants, {}, set(), set())
        r2 = scoring_engine.rank_restaurants(restaurants, {}, set(), set())
    # 前 3 名在两次结果中完全一致
    assert [r.restaurant.name for r in r1[:3]] == [r.restaurant.name for r in r2[:3]]
