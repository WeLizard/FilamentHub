"""Internationalization stub. Returns strings as-is for now."""


def _(message: str, **kwargs) -> str:
    if kwargs:
        try:
            return message.format(**kwargs)
        except (KeyError, IndexError):
            return message
    return message
