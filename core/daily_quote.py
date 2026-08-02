import json
import random
from datetime import datetime
from core.db import get_conn
from core.memory import _use_conn
from core.user_memory import get_user_profile
from core.weakness_detector import detect_weaknesses

QUOTES = [
    # Confidence Foundation
    {"id": 1, "category": "Confidence Foundation", "text": "Confidence isn't built before speaking. It's built because you keep speaking."},
    {"id": 2, "category": "Confidence Foundation", "text": "Every fluent speaker was once the person afraid to say their first sentence."},
    {"id": 3, "category": "Confidence Foundation", "text": "Your voice deserves practice, not perfection."},
    {"id": 4, "category": "Confidence Foundation", "text": "The fear of speaking disappears only after speaking."},
    {"id": 5, "category": "Confidence Foundation", "text": "Silence feels safe today but expensive tomorrow."},
    {"id": 6, "category": "Confidence Foundation", "text": "The conversation you avoid today becomes tomorrow's regret."},
    {"id": 7, "category": "Confidence Foundation", "text": "Every sentence spoken is stronger than a hundred sentences imagined."},
    {"id": 8, "category": "Confidence Foundation", "text": "You don't need perfect English. You need the courage to begin."},
    {"id": 9, "category": "Confidence Foundation", "text": "Your accent tells your story. Your confidence tells your future."},
    {"id": 10, "category": "Confidence Foundation", "text": "Speaking isn't a talent. It's a habit repeated until it feels natural."},

    # Consistency
    {"id": 11, "category": "Consistency", "text": "Five minutes every day beats one perfect hour once a month."},
    {"id": 12, "category": "Consistency", "text": "Small conversations create big confidence."},
    {"id": 13, "category": "Consistency", "text": "Consistency whispers while excuses shout. Listen carefully."},
    {"id": 14, "category": "Consistency", "text": "Every practice session is a vote for the communicator you want to become."},
    {"id": 15, "category": "Consistency", "text": "Improvement hides inside ordinary days, not extraordinary ones."},
    {"id": 16, "category": "Consistency", "text": "Today's practice becomes tomorrow's confidence."},
    {"id": 17, "category": "Consistency", "text": "Fluency grows one conversation at a time."},
    {"id": 18, "category": "Consistency", "text": "Don't measure today's mistakes. Measure tomorrow's improvement."},

    # Growth Mindset
    {"id": 19, "category": "Growth Mindset", "text": "Growth begins where comfort ends."},
    {"id": 20, "category": "Growth Mindset", "text": "Progress isn't always visible, but practice never goes to waste."},
    {"id": 21, "category": "Growth Mindset", "text": "The person you're becoming is built by the conversations you choose to have today."},
    {"id": 22, "category": "Growth Mindset", "text": "Every uncomfortable conversation is an investment in your future self."},
    {"id": 23, "category": "Growth Mindset", "text": "Your future confidence is being built right now."},
    {"id": 24, "category": "Growth Mindset", "text": "Every challenge teaches your brain that speaking is safe."},
    {"id": 25, "category": "Growth Mindset", "text": "Comfort keeps you the same. Conversations change you."},

    # Overcoming Fear
    {"id": 26, "category": "Overcoming Fear", "text": "Fear gets quieter every time your voice gets louder."},
    {"id": 27, "category": "Overcoming Fear", "text": "The first sentence is always the hardest. Speak it anyway."},
    {"id": 28, "category": "Overcoming Fear", "text": "Your fear doesn't disappear before action. It disappears because of action."},
    {"id": 29, "category": "Overcoming Fear", "text": "Mistakes don't make you a poor speaker. Avoiding conversations does."},
    {"id": 30, "category": "Overcoming Fear", "text": "People rarely remember your mistakes. They remember your confidence."},

    # Communication Philosophy
    {"id": 31, "category": "Communication Philosophy", "text": "Great communication is about being understood, not sounding perfect."},
    {"id": 32, "category": "Communication Philosophy", "text": "People connect with honesty long before they notice grammar."},
    {"id": 33, "category": "Communication Philosophy", "text": "Speak to express, not to impress."},
    {"id": 34, "category": "Communication Philosophy", "text": "The goal isn't flawless English. It's meaningful conversations."},
    {"id": 35, "category": "Communication Philosophy", "text": "Clarity is more powerful than complexity."},
    {"id": 36, "category": "Communication Philosophy", "text": "The best speakers focus on connection, not perfection."},

    # Discipline & Self-Improvement
    {"id": 37, "category": "Discipline & Self-Improvement", "text": "Discipline creates confidence long before confidence creates discipline."},
    {"id": 38, "category": "Discipline & Self-Improvement", "text": "Your future self will thank you for today's uncomfortable practice."},
    {"id": 39, "category": "Discipline & Self-Improvement", "text": "Success belongs to those who keep showing up, even on difficult days."},
    {"id": 40, "category": "Discipline & Self-Improvement", "text": "One conversation today can change the person you become tomorrow."},
]

def _get_quote_by_id(qid: int):
    for q in QUOTES:
        if q["id"] == qid:
            return q
    return QUOTES[0]

def get_daily_quote(user_id: int, *, conn=None) -> dict:
    with _use_conn(conn) as c:
        cursor = c.cursor()

        cursor.execute(
            "SELECT last_quote_shown_date, last_quote_id, recent_quote_ids FROM user_quotes WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        today_str = datetime.now().strftime("%Y-%m-%d")

        if row:
            last_date, last_id, recent_json = row
            recent_ids = json.loads(recent_json) if recent_json else []
            if last_date == today_str:
                q = _get_quote_by_id(last_id)
                return {"quote": q, "is_new_today": False}
        else:
            recent_ids = []

        # New day or new user. Decide category.
        profile = get_user_profile(user_id, conn=c)
        weaknesses = detect_weaknesses(profile, conn=c)
        weakness_flags = [w["flag"] for w in weaknesses]

        total_sessions = profile.get("total_sessions", 0)
        last_5 = profile.get("last_5_sessions", [])

        # Check returning gap (7+ days)
        returning_gap = False
        if last_5:
            last_session_date_str = last_5[0]["date"]
            try:
                last_date_obj = datetime.strptime(last_session_date_str, "%Y-%m-%d")
                if (datetime.now() - last_date_obj).days >= 7:
                    returning_gap = True
            except Exception:
                pass

        # Check meaningful streak (3+ sessions in last 7 days)
        meaningful_streak = False
        recent_count = 0
        for s in last_5:
            try:
                d_obj = datetime.strptime(s["date"], "%Y-%m-%d")
                if (datetime.now() - d_obj).days <= 7:
                    recent_count += 1
            except Exception:
                pass
        if total_sessions >= 3 and recent_count >= 3:
            meaningful_streak = True

        wpm_trend = profile.get("wpm_trend", "flat")
        filler_trend = profile.get("filler_trend", "flat")

        # Selection Logic
        candidate_categories = []
        if total_sessions < 5:
            candidate_categories = ["Confidence Foundation", "Overcoming Fear"]
        elif returning_gap:
            candidate_categories = ["Overcoming Fear", "Growth Mindset"]
        elif "STUCK_WPM" in weakness_flags or "STUCK_FILLERS" in weakness_flags:
            candidate_categories = ["Growth Mindset", "Discipline & Self-Improvement"]
        elif wpm_trend == "improving" or filler_trend == "declining":
            candidate_categories = ["Consistency", "Communication Philosophy"]
        elif meaningful_streak:
            candidate_categories = ["Consistency", "Discipline & Self-Improvement"]
        else:
            # Fallback category
            candidate_categories = [
                "Confidence Foundation", "Consistency", "Growth Mindset", 
                "Overcoming Fear", "Communication Philosophy", "Discipline & Self-Improvement"
            ]

        chosen_category = random.choice(candidate_categories)

        # Filter quotes by category
        category_quotes = [q for q in QUOTES if q["category"] == chosen_category]

        # Filter out recent quotes
        available_quotes = [q for q in category_quotes if q["id"] not in recent_ids]

        if not available_quotes:
            # Fallback logic: fall back to the least-recently-shown quote in the category
            category_quotes.sort(key=lambda q: recent_ids.index(q["id"]) if q["id"] in recent_ids else -1)
            selected_quote = category_quotes[0]
        else:
            selected_quote = random.choice(available_quotes)

        # Update DB
        new_recent_ids = recent_ids + [selected_quote["id"]]
        # keep last 7
        if len(new_recent_ids) > 7:
            new_recent_ids = new_recent_ids[-7:]

        if row:
            cursor.execute(
                "UPDATE user_quotes SET last_quote_shown_date = %s, last_quote_id = %s, recent_quote_ids = %s WHERE user_id = %s",
                (today_str, selected_quote["id"], json.dumps(new_recent_ids), user_id)
            )
        else:
            cursor.execute(
                "INSERT INTO user_quotes (user_id, last_quote_shown_date, last_quote_id, recent_quote_ids) VALUES (%s, %s, %s, %s)",
                (user_id, today_str, selected_quote["id"], json.dumps(new_recent_ids))
            )

    return {"quote": selected_quote, "is_new_today": True}
