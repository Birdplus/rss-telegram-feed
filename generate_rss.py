#!/usr/bin/env python3
"""
Telegram RSS Feed Generator
Scrapes Telegram public channel page and generates RSS XML.
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import html.parser
import re
import time
import os
import sys
import ssl
from html import unescape

CHANNEL = "Githubrebang"
TELEGRAM_URL = f"https://t.me/s/{CHANNEL}"
OUTPUT_FILE = "feed.xml"
INDEX_FILE = "index.html"
FEED_TITLE = f"Telegram: {CHANNEL}"
FEED_DESC = f"RSS feed for Telegram channel @{CHANNEL}"
FEED_LINK = f"https://t.me/{CHANNEL}"
USER_AGENT = "Mozilla/5.0 (compatible; RSSBot/1.0)"


def fetch_telegram_page():
    """Fetch Telegram channel page."""
    req = urllib.request.Request(
        TELEGRAM_URL,
        headers={"User-Agent": USER_AGENT},
    )
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return html


def clean_html(html_text):
    """Convert HTML to plain text, preserving line breaks."""
    # Replace <br> with newline
    text = re.sub(r'<br\s*/?>', '\n', html_text)
    # Remove any other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode entities
    text = unescape(text)
    # Clean up multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_messages(html):
    """Extract messages from Telegram page HTML using regex."""
    messages = []

    # Find all message wrap blocks
    wrap_pattern = r'<div class="tgme_widget_message_wrap[^"]*">(.*?)</div>\s*</div>\s*</div>\s*</div>'
    blocks = re.findall(wrap_pattern, html, re.DOTALL)

    for block in blocks:
        msg = {}

        # Extract message link and ID
        link_match = re.search(r'data-post="([^"]+)"', block)
        if link_match:
            post_id = link_match.group(1)  # e.g. "Githubrebang/97"
            msg["id"] = post_id
            msg["link"] = f"https://t.me/{post_id}"

        # Extract datetime from <time> tag
        dt_match = re.search(r'<time datetime="([^"]+)"', block)
        if dt_match:
            msg["datetime"] = dt_match.group(1)

        # Extract text content
        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*(?:</div>\s*)?<div class="tgme_widget_message_footer',
            block, re.DOTALL
        )
        if text_match:
            raw_text = text_match.group(1)
            text = clean_html(raw_text)
            if text:
                msg["text"] = text
                # Title = first line
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                msg["title"] = lines[0] if lines else f"Post {post_id}"

        # Extract images
        imgs = re.findall(
            r'<img[^>]+class="tgme_widget_message_photo[^"]*"[^>]+src="([^"]+)"',
            block
        )
        if imgs:
            msg["images"] = imgs

        if msg.get("link") and msg.get("text"):
            messages.append(msg)

    return messages


def build_rss(messages):
    """Build RSS XML from messages."""
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")

    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = FEED_LINK
    ET.SubElement(channel, "description").text = FEED_DESC
    ET.SubElement(channel, "language").text = "zh-cn"
    ET.SubElement(channel, "generator").text = "telegram-rss-actions"
    ET.SubElement(channel, "lastBuildDate").text = time.strftime(
        "%a, %d %b %Y %H:%M:%S +0000", time.gmtime()
    )

    from datetime import datetime, timezone

    # Add items (newest first - messages appear oldest first on the page)
    for msg in reversed(messages):
        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = msg.get("title", f"Post {msg.get('id', '')}")

        link = msg.get("link", "")
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "guid", isPermaLink="true").text = link

        # Description with images
        desc_parts = []
        for img in msg.get("images", []):
            desc_parts.append(f'<img src="{html.escape(img)}" /><br/>')
        desc_text = msg.get("text", "")
        desc_parts.append(html.escape(desc_text).replace('\n', '<br/>'))
        ET.SubElement(item, "description").text = "".join(desc_parts)

        # Date
        dt = msg.get("datetime", "")
        if dt:
            try:
                dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                rfc2822 = dt_obj.strftime("%a, %d %b %Y %H:%M:%S %z")
                ET.SubElement(item, "pubDate").text = rfc2822
            except (ValueError, AttributeError):
                pass

    return rss


def write_output(rss_elem, messages_count):
    """Write RSS feed and index files."""
    rss_str = ET.tostring(rss_elem, encoding="unicode", xml_declaration=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss_str)
    print(f"✅ RSS 已生成: {OUTPUT_FILE} ({messages_count} 条消息)")

    # Write index.html for GitHub Pages
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{FEED_TITLE} - RSS Feed</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }}
        h1 {{ font-size: 1.5em; }}
        .rss-link {{ display: inline-block; padding: 12px 24px; background: #ff6600; color: #fff; text-decoration: none; border-radius: 6px; font-weight: bold; }}
        .rss-link:hover {{ background: #e55d00; }}
        .info {{ color: #666; }}
    </style>
</head>
<body>
    <h1>{FEED_TITLE}</h1>
    <p class="info">自动生成的 RSS 订阅源，每 30 分钟更新一次。</p>
    <p><a class="rss-link" href="feed.xml">📡 订阅 RSS Feed</a></p>
    <p class="info">最后更新: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}</p>
    <p>订阅地址: <code>https://birdplus.github.io/rss-telegram-feed/feed.xml</code></p>
</body>
</html>"""
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 页面已生成: {INDEX_FILE}")


def main():
    print(f"🔍 正在获取 Telegram 频道 @{CHANNEL}...")
    try:
        html = fetch_telegram_page()
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP 错误: {e.code} {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"❌ 网络错误: {e.reason}")
        sys.exit(1)

    messages = parse_messages(html)
    if not messages:
        print("❌ 未能解析到消息")
        print("   (Telegram 页面结构可能已变更)")
        # Write a minimal valid RSS anyway so the feed doesn't break
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = FEED_TITLE
        ET.SubElement(channel, "link").text = FEED_LINK
        ET.SubElement(channel, "description").text = FEED_DESC
        ET.SubElement(channel, "lastBuildDate").text = time.strftime(
            "%a, %d %b %Y %H:%M:%S +0000", time.gmtime()
        )
        write_output(rss, 0)
        sys.exit(1)

    print(f"✅ 解析到 {len(messages)} 条消息")

    rss_elem = build_rss(messages)
    write_output(rss_elem, len(messages))


if __name__ == "__main__":
    main()
