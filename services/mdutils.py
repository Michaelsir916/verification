def escape_md(text):
    """
    Escapes legacy-Markdown special characters in dynamic/user-controlled
    text (group titles, usernames, etc.) before it's interpolated into a
    message sent with parse_mode="Markdown". Prevents Telegram's
    "Can't parse entities" crash when a title/username contains _, *, `, or [.
    """
    if not text:
        return text
    text = str(text)
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text
