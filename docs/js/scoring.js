// Scoring engine — ported from app/services/scoring_engine.py

const OFFICE_LNG = 121.603071;
const OFFICE_LAT = 31.206835;
const NEARBY_RADIUS_M = 250;

const SPICY_TAGS   = new Set(["spicy"]);
const WARM_TAGS    = new Set(["warm_food"]);
const MEAT_TAGS    = new Set(["meat"]);
const LIGHT_TAGS   = new Set(["light_meal"]);
const FILLING_TAGS = new Set(["filling"]);
const HEALTHY_TAGS = new Set(["healthy"]);
const FAST_TAGS    = new Set(["fast_service"]);
const NOODLE_TAGS  = new Set(["noodles"]);
const CUISINE_TAGS = new Set(["cuisine_chinese", "cuisine_japanese", "cuisine_western", "cuisine_korean"]);

const MONDAY_BUDGET_BOOST   = 0.10;
const WEEKEND_PREMIUM_BOOST = 0.15;

function haversine(lng1, lat1, lng2, lat2) {
  const R = 6_371_000;
  const toRad = d => d * Math.PI / 180;
  const phi1 = toRad(lat1), phi2 = toRad(lat2);
  const dphi = toRad(lat2 - lat1);
  const dlam = toRad(lng2 - lng1);
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dlam / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function isDrinks(r) {
  const tags = new Set(r.tags || []);
  if (tags.has("drink_n_snack")) return true;
  return tags.has("cold_food") && ![...tags].some(t => t.startsWith("cuisine_"));
}

export function aggregateWeights(allParticipantAnswers) {
  const totals = {};
  const budgetVotes = [];

  for (const participantAnswers of allParticipantAnswers) {
    for (const answer of participantAnswers) {
      for (const [dim, val] of Object.entries(answer.weights || {})) {
        if (dim === "budget_max") {
          budgetVotes.push(val);
        } else {
          totals[dim] = (totals[dim] || 0) + val;
        }
      }
    }
  }

  if (budgetVotes.length > 0) {
    totals["budget_max"] = Math.min(...budgetVotes);
  }

  return totals;
}

function filterPool(restaurants, weights) {
  let pool = restaurants.filter(r => !r.deleted);

  if ((weights.vendor_only || 0) > 0) {
    pool = pool.filter(r => r.vendor === 1);
  }

  if ((weights.meal_fast || 0) > 0) {
    pool = pool.filter(r => (r.tags || []).includes("fast_service"));
  } else if ((weights.meal_proper || 0) > 0) {
    pool = pool.filter(r => !(r.tags || []).includes("no_seat"));
  }

  if ((weights.nearby_only || 0) > 0) {
    pool = pool.filter(r =>
      r.lng && r.lat &&
      haversine(r.lng, r.lat, OFFICE_LNG, OFFICE_LAT) <= NEARBY_RADIUS_M
    );
  }

  return pool;
}

function scoreRestaurant(restaurant, weights, recentNames, yesterdayNames) {
  const budgetMax = weights.budget_max ?? 999;
  if (restaurant.avg_spend && restaurant.avg_spend > budgetMax) return null;

  let score = 0;
  const tags = new Set(restaurant.tags || []);
  const reasons = [];

  if ([...tags].some(t => SPICY_TAGS.has(t))) {
    const delta = weights.spicy || 0;
    score += delta;
    if (delta > 0) reasons.push("合口味辣度");
  }

  if ([...tags].some(t => WARM_TAGS.has(t))) {
    const delta = weights.warm_food || 0;
    score += delta;
    if (delta > 0) reasons.push("有热汤热食");
  }

  if ([...tags].some(t => MEAT_TAGS.has(t))) {
    const delta = weights.meat || 0;
    score += delta;
    if (delta > 0) reasons.push("肉食爱好者加分");
  }

  if ([...tags].some(t => LIGHT_TAGS.has(t))) {
    score += (weights.healthy || 0) * 0.5 + (weights.light_meal || 0) * 0.5;
  }

  if ([...tags].some(t => FILLING_TAGS.has(t))) {
    score += weights.filling || 0;
  }

  if ([...tags].some(t => HEALTHY_TAGS.has(t))) {
    const delta = weights.healthy || 0;
    score += delta;
    if (delta > 0) reasons.push("健康选择");
  }

  if ([...tags].some(t => FAST_TAGS.has(t))) {
    const delta = weights.fast_service || 0;
    score += delta;
    if (delta > 0) reasons.push("快速上菜");
  }

  if ([...tags].some(t => NOODLE_TAGS.has(t))) {
    score -= weights.avoid_noodles || 0;
  }

  if (!tags.has("fast_service")) {
    score += weights.sitdown_bonus || 0;
  }

  for (const cuisineTag of CUISINE_TAGS) {
    if (tags.has(cuisineTag)) {
      score += weights[cuisineTag] || 0;
    }
  }

  if (restaurant.avg_spend && restaurant.avg_spend < 25) {
    const delta = weights.budget_friendly || 0;
    score += delta;
    if (delta > 0) reasons.push("超划算");
  }

  if (restaurant.rating && restaurant.rating >= 4.5) {
    const delta = weights.premium || 0;
    score += delta;
    if (delta > 0) reasons.push("高分好评");
  }

  const name = restaurant.name;
  if (yesterdayNames.has(name)) {
    score -= 3.0;
    reasons.push("⚠️ 昨天刚去过");
  } else if (recentNames.has(name)) {
    score -= 1.5;
    reasons.push("⚠️ 前天去过");
  }

  score += (weights.random_bonus || 0) * Math.random();

  const reason = reasons.length > 0 ? reasons.join("、") : "综合评分推荐";
  return { restaurant, score: Math.round(score * 1000) / 1000, reason };
}

export function rankRestaurants(restaurants, weights, recentNames, yesterdayNames, topN = 20, blacklist = []) {
  const blacklistSet = new Set(blacklist);

  let pool = filterPool(restaurants, weights).filter(r => !blacklistSet.has(r.name));

  let scored = pool
    .map(r => scoreRestaurant(r, weights, recentNames, yesterdayNames))
    .filter(r => r !== null);

  const weekday = new Date().getDay();
  scored = scored.map(r => {
    const tags = new Set(r.restaurant.tags || []);
    const base = (r.restaurant.rating || 3.5) * 2.0;
    if (weekday === 1 && tags.has("budget_friendly")) {
      return { ...r, score: r.score + base * MONDAY_BUDGET_BOOST };
    }
    if ([5, 6, 0].includes(weekday) && tags.has("premium")) {
      return { ...r, score: r.score + base * WEEKEND_PREMIUM_BOOST };
    }
    return r;
  });

  scored.sort((a, b) => b.score - a.score);

  if (scored.length <= topN) return scored;

  // Weighted sampling: high-score restaurants are more likely but not guaranteed
  const minScore = Math.min(...scored.map(r => r.score));
  let remaining = scored.map(r => ({ ...r, w: Math.max(0.1, r.score - minScore + 1) }));
  const result = [];
  while (result.length < topN && remaining.length > 0) {
    const total = remaining.reduce((s, r) => s + r.w, 0);
    let rand = Math.random() * total;
    let idx = 0;
    while (idx < remaining.length - 1 && rand > remaining[idx].w) {
      rand -= remaining[idx].w;
      idx++;
    }
    const { w, ...item } = remaining[idx];
    result.push(item);
    remaining.splice(idx, 1);
  }

  return result;
}
