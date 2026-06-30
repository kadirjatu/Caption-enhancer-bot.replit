"""
Referral, Rewards & Leaderboard System
--------------------------------------
Beta Mode: referral system fully active, credits system disabled.
All data stored in referral_data.json (separate from users.json).
"""

import json
import threading
import time
import logging
import calendar

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
# BETA_MODE and CREDITS_ENABLED live in credits.py (single source of truth)
from credits import BETA_MODE, CREDITS_ENABLED

REFERRAL_FUTURE_CREDITS = 5   # Future credits per referral (usable after launch)
WEEKLY_RESET_DAYS       = 7
TOP_WEEKLY_WINNERS      = 10

WEEKLY_REWARD = {
    "unlimited_video":   True,
    "priority_queue":    True,
    "faster_processing": True,
    "premium_badge":     True,
    "duration_days":     7,
}

MONTHLY_REWARD = {
    "premium_30_days":      True,
    "highest_priority":     True,
    "exclusive_badge":      True,
    "early_access":         True,
    "feature_testing":      True,
    "special_recognition":  True,
    "duration_days":        30,
}

RANK_BADGES = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
}

DATA_FILE = "referral_data.json"
_lock = threading.Lock()

# ── I/O ───────────────────────────────────────────────────────────────────────
def _load():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default_data()

def _save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _default_data():
    now = time.time()
    return {
        "users": {},
        "meta": {
            "weekly_start":       now,
            "monthly_start":      now,
            "last_weekly_winners": [],
            "last_monthly_champion": None,
        }
    }

def _ensure_user(data, uid, name=""):
    uid = str(uid)
    if uid not in data["users"]:
        data["users"][uid] = {
            "name":               name or uid,
            "join_date":          time.time(),
            "referrer_id":        None,
            "referred_users":     [],
            "lifetime_referrals": 0,
            "weekly_referrals":   0,
            "monthly_referrals":  0,
            "future_credits":     0,
            "rewards":            {},
            "banned":             False,
        }
    elif name and data["users"][uid].get("name") == uid:
        data["users"][uid]["name"] = name
    return data["users"][uid]

# ── Referral recording ────────────────────────────────────────────────────────
def record_referral(referrer_id, new_user_id, referrer_name="", new_user_name=""):
    """
    Record a referral. Returns (success: bool, reason: str).
    Anti-abuse: no self-referrals, no duplicates, no banned users.
    """
    referrer_id  = str(referrer_id)
    new_user_id  = str(new_user_id)

    if referrer_id == new_user_id:
        return False, "self_referral"

    with _lock:
        data = _load()
        _ensure_user(data, new_user_id, new_user_name)
        _ensure_user(data, referrer_id, referrer_name)

        new_user = data["users"][new_user_id]
        referrer = data["users"][referrer_id]

        if referrer.get("banned"):
            return False, "referrer_banned"
        if new_user.get("referrer_id"):
            return False, "already_referred"
        if new_user_id in referrer.get("referred_users", []):
            return False, "duplicate"

        # Record the referral
        new_user["referrer_id"] = referrer_id
        referrer.setdefault("referred_users", []).append(new_user_id)
        referrer["lifetime_referrals"] = referrer.get("lifetime_referrals", 0) + 1
        referrer["weekly_referrals"]   = referrer.get("weekly_referrals",   0) + 1
        referrer["monthly_referrals"]  = referrer.get("monthly_referrals",  0) + 1
        referrer["future_credits"]     = referrer.get("future_credits",     0) + REFERRAL_FUTURE_CREDITS

        _save(data)

    return True, "ok"

def register_user(user_id, name=""):
    """Ensure user exists in referral system."""
    uid = str(user_id)
    with _lock:
        data = _load()
        _ensure_user(data, uid, name)
        _save(data)

# ── Profile & stats ───────────────────────────────────────────────────────────
def get_user_stats(user_id):
    """Return full stats dict for a user."""
    uid = str(user_id)
    with _lock:
        data = _load()
        u = _ensure_user(data, uid)
        _save(data)
    board_w = _get_board(data, "weekly")
    board_m = _get_board(data, "monthly")
    rank_w = _find_rank(board_w, uid)
    rank_m = _find_rank(board_m, uid)
    return {
        "name":               u.get("name", uid),
        "user_id":            uid,
        "join_date":          u.get("join_date", 0),
        "lifetime_referrals": u.get("lifetime_referrals", 0),
        "weekly_referrals":   u.get("weekly_referrals",   0),
        "monthly_referrals":  u.get("monthly_referrals",  0),
        "future_credits":     u.get("future_credits",     0),
        "weekly_rank":        rank_w,
        "monthly_rank":       rank_m,
        "rewards":            u.get("rewards", {}),
        "banned":             u.get("banned", False),
        "beta_mode":          BETA_MODE,
        "credits_enabled":    CREDITS_ENABLED,
    }

def _get_board(data, period):
    """Sort users by period referrals, return list of (uid, count)."""
    key = f"{period}_referrals"
    board = [
        (uid, u.get(key, 0))
        for uid, u in data["users"].items()
        if not u.get("banned") and u.get(key, 0) > 0
    ]
    board.sort(key=lambda x: x[1], reverse=True)
    return board

def _find_rank(board, uid):
    for i, (u, _) in enumerate(board, 1):
        if u == uid:
            return i
    return None

# ── Leaderboard ───────────────────────────────────────────────────────────────
def get_leaderboard(period="weekly", limit=10):
    """
    Returns list of dicts for top `limit` users in given period.
    period: 'weekly' | 'monthly' | 'lifetime'
    """
    with _lock:
        data = _load()
    board = _get_board(data, period)[:limit]
    result = []
    for rank, (uid, count) in enumerate(board, 1):
        u = data["users"].get(uid, {})
        badge = RANK_BADGES.get(rank, f"#{rank}")
        reward_active = _has_active_reward(u, "weekly_reward")
        result.append({
            "rank":    rank,
            "badge":   badge,
            "uid":     uid,
            "name":    u.get("name", uid),
            "count":   count,
            "premium": reward_active,
        })
    return result

def get_user_rank(user_id, period="weekly"):
    uid = str(user_id)
    with _lock:
        data = _load()
    board = _get_board(data, period)
    return _find_rank(board, uid)

def get_days_until_reset(period="weekly"):
    with _lock:
        data = _load()
    meta = data.get("meta", {})
    if period == "weekly":
        elapsed = time.time() - meta.get("weekly_start", time.time())
        remaining = max(0, WEEKLY_RESET_DAYS * 86400 - elapsed)
        return int(remaining // 86400), int((remaining % 86400) // 3600)
    else:
        now = time.localtime()
        days_in_month = calendar.monthrange(now.tm_year, now.tm_mon)[1]
        remaining_days = days_in_month - now.tm_mday
        return remaining_days, 0

# ── Rewards ───────────────────────────────────────────────────────────────────
def _has_active_reward(user_dict, reward_key):
    r = user_dict.get("rewards", {}).get(reward_key, {})
    if not r.get("active"):
        return False
    expires = r.get("expires_at", 0)
    return expires == 0 or time.time() < expires

def has_premium(user_id):
    uid = str(user_id)
    with _lock:
        data = _load()
    u = data["users"].get(uid, {})
    return (
        _has_active_reward(u, "weekly_reward") or
        _has_active_reward(u, "monthly_reward")
    )

def get_user_rewards(user_id):
    uid = str(user_id)
    with _lock:
        data = _load()
    u = data["users"].get(uid, {})
    active = {}
    for key, r in u.get("rewards", {}).items():
        if _has_active_reward(u, key):
            active[key] = r
    return active

def _assign_weekly_rewards(data, bot=None):
    """Assign rewards to top 10 weekly referrers. Notify them."""
    board = _get_board(data, "weekly")[:TOP_WEEKLY_WINNERS]
    expires_at = time.time() + WEEKLY_REWARD["duration_days"] * 86400
    winners = []

    for rank, (uid, count) in enumerate(board, 1):
        u = data["users"][uid]
        badge = RANK_BADGES.get(rank, f"#{rank}")
        u.setdefault("rewards", {})["weekly_reward"] = {
            "active":     True,
            "expires_at": expires_at,
            "rank":       rank,
            "badge":      badge,
            "assigned_at": time.time(),
        }
        winners.append((uid, rank, badge, count))
        logger.info(f"Weekly reward assigned: uid={uid} rank={rank}")

    data["meta"]["last_weekly_winners"] = [w[0] for w in winners]

    # Notify winners via bot if provided
    if bot:
        for uid, rank, badge, count in winners:
            try:
                badge_txt = RANK_BADGES.get(rank, f"#{rank}")
                msg = (
                    f"🏆 <b>Weekly Leaderboard Results!</b>\n\n"
                    f"{badge_txt} <b>Aap Rank #{rank} pe hain!</b>\n\n"
                    f"🎁 <b>Premium Rewards Activated:</b>\n"
                    f"✅ Unlimited Video Upscaling\n"
                    f"✅ Priority Processing Queue\n"
                    f"✅ Faster AI Processing\n"
                    f"✅ Premium Badge {badge_txt}\n\n"
                    f"⏳ Reward duration: <b>7 Days</b>\n"
                    f"📊 Your weekly referrals: <b>{count}</b>"
                )
                bot.send_message(int(uid), msg, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not notify winner {uid}: {e}")

    return winners

def _assign_monthly_champion(data, bot=None):
    """Assign monthly champion reward to #1 monthly referrer."""
    board = _get_board(data, "monthly")
    if not board:
        return None
    uid, count = board[0]
    u = data["users"][uid]
    expires_at = time.time() + MONTHLY_REWARD["duration_days"] * 86400
    u.setdefault("rewards", {})["monthly_reward"] = {
        "active":      True,
        "expires_at":  expires_at,
        "badge":       "👑",
        "assigned_at": time.time(),
    }
    data["meta"]["last_monthly_champion"] = uid
    logger.info(f"Monthly champion: uid={uid} referrals={count}")

    if bot:
        try:
            bot.send_message(
                int(uid),
                f"👑 <b>Monthly Champion!</b>\n\n"
                f"🎉 Aap is mahine ke <b>Top Referrer</b> hain!\n"
                f"📊 Monthly referrals: <b>{count}</b>\n\n"
                f"🎁 <b>30-Day Premium Unlocked:</b>\n"
                f"✅ Highest Queue Priority\n"
                f"✅ Exclusive Champion Badge 👑\n"
                f"✅ Early Access to New Features\n"
                f"✅ Feature Testing Access\n"
                f"✅ Special Recognition in Bot\n\n"
                f"⏳ Duration: <b>30 Days</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not notify monthly champion {uid}: {e}")

    return uid, count

def _expire_rewards(data, bot=None):
    """Expire rewards that have passed their expiry time. Notify users."""
    now = time.time()
    for uid, u in data["users"].items():
        for key, r in u.get("rewards", {}).items():
            if r.get("active") and r.get("expires_at", 0) > 0 and now >= r["expires_at"]:
                r["active"] = False
                logger.info(f"Reward expired: uid={uid} reward={key}")
                if bot:
                    try:
                        bot.send_message(
                            int(uid),
                            f"⌛ <b>Premium Reward Expire Ho Gaya</b>\n\n"
                            f"Aapka <b>{'Weekly' if 'weekly' in key else 'Monthly'} Premium</b> "
                            f"expire ho gaya hai.\n\n"
                            f"🏆 Leaderboard pe aao aur dobara jeeto!\n"
                            f"Use /leaderboard to check rankings.",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"Could not notify expiry {uid}: {e}")

def _reset_weekly(data, bot=None):
    """Reset weekly leaderboard, assign rewards, start new week."""
    logger.info("Resetting weekly leaderboard...")
    _expire_rewards(data, bot)
    _assign_weekly_rewards(data, bot)
    for u in data["users"].values():
        u["weekly_referrals"] = 0
    data["meta"]["weekly_start"] = time.time()

def _reset_monthly(data, bot=None):
    """Reset monthly leaderboard, assign champion reward, start new month."""
    logger.info("Resetting monthly leaderboard...")
    _assign_monthly_champion(data, bot)
    for u in data["users"].values():
        u["monthly_referrals"] = 0
    data["meta"]["monthly_start"] = time.time()

# ── Scheduler ─────────────────────────────────────────────────────────────────
_bot_ref = None

def start_scheduler(bot=None):
    """Start background thread for auto-reset and reward expiry."""
    global _bot_ref
    _bot_ref = bot
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    logger.info("Referral scheduler started.")

def _scheduler_loop():
    while True:
        try:
            _tick(_bot_ref)
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        time.sleep(60)   # check every minute

def _tick(bot=None):
    with _lock:
        data = _load()
        meta = data.get("meta", {})
        now  = time.time()
        changed = False

        # Expire rewards
        _expire_rewards(data, bot)

        # Weekly reset
        weekly_elapsed = now - meta.get("weekly_start", now)
        if weekly_elapsed >= WEEKLY_RESET_DAYS * 86400:
            _reset_weekly(data, bot)
            changed = True

        # Monthly reset — check if month changed
        monthly_start = meta.get("monthly_start", now)
        start_lt = time.localtime(monthly_start)
        now_lt   = time.localtime(now)
        if now_lt.tm_mon != start_lt.tm_mon or now_lt.tm_year != start_lt.tm_year:
            _reset_monthly(data, bot)
            changed = True

        if changed:
            pass  # already modified data in-place

        _save(data)

# ── Admin helpers ─────────────────────────────────────────────────────────────
def admin_reset_weekly(bot=None):
    with _lock:
        data = _load()
        _reset_weekly(data, bot)
        _save(data)
    return True

def admin_reset_monthly(bot=None):
    with _lock:
        data = _load()
        _reset_monthly(data, bot)
        _save(data)
    return True

def admin_ban_user(user_id):
    uid = str(user_id)
    with _lock:
        data = _load()
        _ensure_user(data, uid)
        data["users"][uid]["banned"] = True
        _save(data)
    return True

def admin_unban_user(user_id):
    uid = str(user_id)
    with _lock:
        data = _load()
        if uid in data["users"]:
            data["users"][uid]["banned"] = False
            _save(data)
    return True

def admin_add_reward(user_id, reward_key, days):
    uid = str(user_id)
    with _lock:
        data = _load()
        _ensure_user(data, uid)
        data["users"][uid].setdefault("rewards", {})[reward_key] = {
            "active":      True,
            "expires_at":  time.time() + days * 86400,
            "badge":       "⭐",
            "assigned_at": time.time(),
        }
        _save(data)
    return True

def admin_remove_reward(user_id, reward_key):
    uid = str(user_id)
    with _lock:
        data = _load()
        if uid in data["users"]:
            data["users"][uid].get("rewards", {}).pop(reward_key, None)
            _save(data)
    return True

def admin_set_beta(enabled: bool):
    global BETA_MODE, CREDITS_ENABLED
    BETA_MODE       = enabled
    CREDITS_ENABLED = not enabled
    return True

def admin_get_stats():
    with _lock:
        data = _load()
    total_users    = len(data["users"])
    total_referrals = sum(u.get("lifetime_referrals", 0) for u in data["users"].values())
    board_w = _get_board(data, "weekly")
    board_m = _get_board(data, "monthly")
    return {
        "total_users":     total_users,
        "total_referrals": total_referrals,
        "weekly_board":    board_w[:5],
        "monthly_board":   board_m[:5],
        "beta_mode":       BETA_MODE,
        "credits_enabled": CREDITS_ENABLED,
    }

# ── Notify helpers (called from bot.py) ──────────────────────────────────────
def notify_new_referral(bot, referrer_id, new_user_name, referrer_future_credits):
    try:
        rank = get_user_rank(referrer_id, "weekly")
        rank_txt = f"\n🏆 Aap ab Weekly Rank <b>#{rank}</b> pe hain!" if rank else ""
        top10 = get_leaderboard("weekly", TOP_WEEKLY_WINNERS)
        in_top10 = any(str(e["uid"]) == str(referrer_id) for e in top10)
        top10_txt = "\n🔥 Aap <b>Weekly Top 10</b> mein hain!" if in_top10 else ""
        bot.send_message(
            int(referrer_id),
            f"🎉 <b>Referral Mila!</b>\n\n"
            f"<b>{new_user_name}</b> ne join kiya aapke link se!\n"
            f"🎁 <b>+{REFERRAL_FUTURE_CREDITS} Future Credits</b> earn kiye!\n\n"
            f"<i>Ye credits launch ke baad automatically usable ho jayenge.</i>"
            f"{rank_txt}{top10_txt}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Could not send referral notification to {referrer_id}: {e}")
