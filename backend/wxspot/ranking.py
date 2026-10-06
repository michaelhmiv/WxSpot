from sqlalchemy import func

from wxspot.models import Post


def top_score(likes, comments, clock):
    """Replaceable, transparent engagement/time-decay strategy."""
    age_hours = func.greatest(func.extract("epoch", clock - Post.created_at) / 3600, 0)
    return (likes + comments * 0.5 + 1) / func.power(age_hours + 2, 1.5)
