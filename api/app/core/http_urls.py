from urllib.parse import urlsplit, urlunsplit


def normalize_loopback_endpoint_url(url: str) -> str:
    """Prefer IPv4 loopback over localhost for local model services."""

    parsed = urlsplit(url)
    if parsed.hostname != "localhost":
        return url
    netloc = parsed.netloc.replace("localhost", "127.0.0.1", 1)
    return urlunsplit(parsed._replace(netloc=netloc))