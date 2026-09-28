from __future__ import annotations

import html.parser
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


MAX_GUIDE_BYTES = 2 * 1024 * 1024
MAX_GUIDE_CHARACTERS = 120_000
USER_AGENT = "YGOComboNavigator/0.2 (+deck-pack-authoring)"
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "text/markdown",
    "application/xhtml+xml",
}


@dataclass(frozen=True, slots=True)
class GuideSource:
    label: str
    text: str
    source_url: str | None = None


class _HTMLTextExtractor(html.parser.HTMLParser):
    _BLOCK_TAGS = {
        "article", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "main", "p", "section", "table", "td", "th", "tr",
    }
    _IGNORED_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in self._IGNORED_TAGS:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and lowered in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in self._IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
        elif self._ignored_depth == 0 and lowered in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\r", "\n").split("\n")]
    compact: list[str] = []
    for line in lines:
        if line:
            compact.append(line)
        elif compact and compact[-1] != "":
            compact.append("")
    result = "\n".join(compact).strip()
    if not result:
        raise ValueError("The guide source contains no readable text")
    if len(result) > MAX_GUIDE_CHARACTERS:
        result = result[:MAX_GUIDE_CHARACTERS].rstrip()
    return result


def html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    return _normalize_text(parser.text())


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Guide URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Guide URL has an invalid host or embedded credentials")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve guide URL host: {parsed.hostname}") from exc
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ValueError("Guide URL resolves to a private or unsafe network address")
    return urllib.parse.urlunsplit(parsed)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url = validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def load_guide_url(url: str, *, timeout: float = 30.0) -> GuideSource:
    safe_url = validate_public_url(url)
    request = urllib.request.Request(safe_url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = validate_public_url(response.geturl())
            content_type = response.headers.get_content_type().casefold()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise ValueError(f"Unsupported guide content type: {content_type}")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_GUIDE_BYTES:
                raise ValueError("Guide page is larger than the allowed 2 MiB")
            raw = response.read(MAX_GUIDE_BYTES + 1)
            if len(raw) > MAX_GUIDE_BYTES:
                raise ValueError("Guide page is larger than the allowed 2 MiB")
            charset = response.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
        raise ValueError(f"Unable to download guide URL: {exc}") from exc
    decoded = raw.decode(charset, errors="replace")
    text = html_to_text(decoded) if "html" in content_type else _normalize_text(decoded)
    return GuideSource(label=final_url, text=text, source_url=final_url)


def load_guide_file(path: Path) -> GuideSource:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"Guide file does not exist: {path}")
    if path.stat().st_size > MAX_GUIDE_BYTES:
        raise ValueError("Guide file is larger than the allowed 2 MiB")
    try:
        value = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Guide file must be UTF-8 text, Markdown, or HTML") from exc
    text = html_to_text(value) if path.suffix.casefold() in {".html", ".htm"} else _normalize_text(value)
    return GuideSource(label=path.name, text=text)


def load_guide_text(text: str, *, label: str = "pasted guide text") -> GuideSource:
    return GuideSource(label=label, text=_normalize_text(text))
