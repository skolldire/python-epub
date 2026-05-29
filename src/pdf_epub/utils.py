def escape_html(text: str) -> str:
    """Escapes the five XML/HTML special characters to their entity equivalents."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
