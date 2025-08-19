# Allows: from searchex import searchex_native
try:
    from . import searchex_native
except Exception:
    searchex_native = None

__all__ = ["searchex_native"]
