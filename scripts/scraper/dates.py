"""Date helpers for arXiv listing schedules."""

from datetime import datetime, timedelta

from .config import NY_TZ


def prev_business_day(d):
    """Return the most recent weekday on or before date d."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_business_day(d):
    """Return the next weekday on or after date d."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def get_target_date(date_str=None, _et_now=None):
    """Return the arXiv listing date to scrape as YYYY-MM-DD."""
    if date_str:
        return date_str

    if _et_now is None:
        _et_now = datetime.now(NY_TZ)

    if _et_now.weekday() == 5 or (_et_now.weekday() == 6 and _et_now.hour < 14):
        target = prev_business_day(_et_now.date())
    elif _et_now.hour >= 14:
        target = next_business_day(_et_now.date() + timedelta(days=1))
    else:
        target = _et_now.date()

    return target.strftime("%Y-%m-%d")


def listing_date_for_published(published):
    """Return the arXiv listing date for an Atom published timestamp."""
    published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    et_dt = published_dt.astimezone(NY_TZ)
    target = et_dt.date() + timedelta(days=1) if et_dt.hour >= 14 else et_dt.date()
    return next_business_day(target).strftime("%Y-%m-%d")
