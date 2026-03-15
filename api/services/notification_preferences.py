from django.utils import timezone

from api.models import Notification


DEFAULT_NOTIFICATION_PREFERENCES = {
    "general": True,
    "content": True,
    "social": True,
    "chat": True,
    "donation": True,
}


def normalize_notification_preferences(raw_preferences):
    normalized = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    if not isinstance(raw_preferences, dict):
        return normalized

    for key in DEFAULT_NOTIFICATION_PREFERENCES:
        if key not in raw_preferences:
            continue
        value = raw_preferences.get(key)
        if isinstance(value, bool):
            normalized[key] = value
        elif isinstance(value, (int, float)):
            normalized[key] = bool(value)
        elif isinstance(value, str):
            normalized[key] = value.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
    return normalized


def user_allows_notification(user, *, category="general", channel="IN_APP"):
    if channel != "IN_APP":
        return True

    preferences = normalize_notification_preferences(
        getattr(user, "notification_preferences", {}),
    )
    key = category if category in DEFAULT_NOTIFICATION_PREFERENCES else "general"
    return preferences.get(key, True)


def build_in_app_notification(
    user,
    *,
    title,
    message,
    notif_type="INFO",
    meta=None,
    category="general",
):
    if not user_allows_notification(user, category=category, channel="IN_APP"):
        return None

    return Notification(
        user=user,
        title=title,
        eng_title=title,
        message=message,
        eng_message=message,
        type=notif_type,
        channel="IN_APP",
        sent=True,
        sent_at=timezone.now(),
        meta=meta or {},
    )


def create_in_app_notification(
    user,
    *,
    title,
    message,
    notif_type="INFO",
    meta=None,
    category="general",
):
    notification = build_in_app_notification(
        user,
        title=title,
        message=message,
        notif_type=notif_type,
        meta=meta,
        category=category,
    )
    if notification is None:
        return None
    notification.save()
    return notification


def build_in_app_notifications(
    users,
    *,
    title,
    message,
    notif_type="INFO",
    meta=None,
    category="general",
    exclude_user_id=None,
):
    notifications = []
    for user in users:
        if exclude_user_id is not None and str(user.id) == str(exclude_user_id):
            continue
        notification = build_in_app_notification(
            user,
            title=title,
            message=message,
            notif_type=notif_type,
            meta=meta,
            category=category,
        )
        if notification is not None:
            notifications.append(notification)
    return notifications

