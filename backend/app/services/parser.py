from __future__ import annotations

import json
import re
from html import unescape
from io import BytesIO
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


REQUEST_TIMEOUT = 20
CONTENT_API_BASE_URLS = [
    "https://np-cnotice-stock-test.eastmoney.com/api/content/ann",
    "https://np-cnotice-stock.eastmoney.com/api/content/ann",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://data.eastmoney.com/",
}


def extract_announcement_text(url: str) -> str:
    eastmoney_text = _extract_eastmoney_text(url)
    if eastmoney_text:
        return eastmoney_text

    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return _extract_pdf_text(response.content)

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = _clean_text(soup.get_text("\n"))

    pdf_href = _find_pdf_href(soup, url)
    if len(text) < 500 and pdf_href:
        pdf_response = requests.get(pdf_href, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        pdf_response.raise_for_status()
        pdf_text = _extract_pdf_text(pdf_response.content)
        if pdf_text:
            return pdf_text
    return text


def should_reextract_content(content: str | None) -> bool:
    if not content:
        return True
    text = content.strip()
    if len(text) < 300:
        return True
    shell_markers = [
        "东方财富网",
        "数据中心",
        "查看PDF原文",
        "郑重声明：本网不保证其真实性",
        "公告正文 _ 数据中心",
    ]
    marker_count = sum(1 for marker in shell_markers if marker in text)
    return marker_count >= 2


def _extract_eastmoney_text(url: str) -> str | None:
    art_code = _extract_art_code(url)
    if not art_code:
        return None

    first = _fetch_eastmoney_content_page(art_code, 1)
    if not first:
        return None

    page_size = int(first.get("page_size") or 1)
    parts = [_clean_notice_content(first.get("notice_content") or "")]
    for page_index in range(2, page_size + 1):
        page = _fetch_eastmoney_content_page(art_code, page_index)
        if page:
            parts.append(_clean_notice_content(page.get("notice_content") or ""))

    text = _clean_text("\n".join(part for part in parts if part))
    if text:
        return text

    attach_url = first.get("attach_url_web") or first.get("attach_url")
    if attach_url:
        pdf_response = requests.get(attach_url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        pdf_response.raise_for_status()
        return _extract_pdf_text(pdf_response.content)
    return None


def _fetch_eastmoney_content_page(art_code: str, page_index: int) -> dict | None:
    last_error: Exception | None = None
    for api_url in CONTENT_API_BASE_URLS:
        try:
            response = requests.get(
                api_url,
                params={"art_code": art_code, "client_source": "web", "page_index": page_index},
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = _loads_json_or_jsonp(response.text)
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict):
                return data
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return None


def _extract_art_code(url: str) -> str | None:
    match = re.search(r"(AN\d+)", url)
    return match.group(1) if match else None


def _loads_json_or_jsonp(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    match = re.search(r"^[^(]+\((.*)\)\s*;?$", stripped, re.S)
    if not match:
        raise ValueError("Unsupported Eastmoney response format")
    return json.loads(match.group(1))


def _find_pdf_href(soup: BeautifulSoup, base_url: str) -> str | None:
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if ".pdf" in href.lower():
            return urljoin(base_url, href)
    return None


def _clean_notice_content(content: str) -> str:
    unescaped = unescape(content)
    if "<" in unescaped and ">" in unescaped:
        soup = BeautifulSoup(unescaped, "html.parser")
        return _clean_text(soup.get_text("\n"))
    return _clean_text(unescaped)


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return _clean_text("\n".join(pages))


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
