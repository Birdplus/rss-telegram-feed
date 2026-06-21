#!/usr/bin/env python3
"""
Telegram RSS Feed Generator - Clean version
- Only repo names are clickable links
- Clean formatting for comfortable reading
"""

import urllib.request
import urllib.error
import re
import time
import sys
import ssl
from html import unescape

CHANNEL = "Githubrebang"
TELEGRAM_URL = f"https://t.me/s/{CHANNEL}"
OUTPUT_FILE = "feed.xml"
INDEX_FILE = "index.html"
FEED_TITLE = "GitHub Trending 每日热榜"
FEED_DESC = f"RSS feed for Telegram channel @{CHANNEL}"
FEED_LINK = f"https://t.me/{CHANNEL}"
USER_AGENT = "Mozilla/5.0 (compatible; RSSBot/1.0)"


def fetch_telegram_page():
    """Fetch Telegram channel page."""
    req = urllib.request.Request(TELEGRAM_URL, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_emoji_wrappers(text):
    """Remove Telegram's emoji HTML wrappers but keep the emoji characters."""
    # Handle <i class="emoji" style="..."><b>EMOJI</b></i> → EMOJI
    text = re.sub(r'<i[^>]*class="emoji"[^>]*>', '', text)
    text = text.replace('</i>', '')
    # Handle <span class="emoji" style="..."><b>EMOJI</b></span> → EMOJI  
    text = re.sub(r'<span[^>]*class="emoji"[^>]*>', '', text)
    text = text.replace('</span>', '')
    return text


def extract_meta_info(raw_html):
    """
    Extract structured data from a message.
    Returns {title, date, link, repos: [{rank, repo_name, repo_url, desc, stats}]}
    """
    msg = {}
    
    # Message link
    link_match = re.search(r'data-post="([^"]+)"', raw_html)
    if link_match:
        msg["link"] = f"https://t.me/{link_match.group(1)}"
    
    # Datetime
    dt_match = re.search(r'<time datetime="([^"]+)"', raw_html)
    if dt_match:
        msg["datetime"] = dt_match.group(1)
    
    # Extract text content
    text_match = re.search(
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*(?:</div>\s*)?<div class="tgme_widget_message_footer',
        raw_html, re.DOTALL
    )
    if not text_match:
        return None
    
    raw_text = text_match.group(1)
    
    # ---- Extract section title (first line, before first numbered item) ----
    # Remove emoji wrappers
    clean_for_title = strip_emoji_wrappers(raw_text)
    # Strip all tags for title
    title_text = re.sub(r'<[^>]+>', '', clean_for_title)
    title_text = unescape(title_text)
    title_text = re.sub(r'\s+', ' ', title_text).strip()
    # Take just the first meaningful segment before any numbered item
    title_match = re.match(r'^([^\d]+?)(?:\s*\d+\.|\s*$)', title_text)
    msg["title"] = title_match.group(1).strip() if title_match else title_text[:60]
    if len(msg["title"]) > 80:
        msg["title"] = msg["title"][:80] + "…"
    
    # ---- Clean HTML for display ----
    # Step 1: Remove emoji wrappers
    display_html = strip_emoji_wrappers(raw_text)
    
    # Step 2: Extract all <a> links and their text, then rebuild
    # Find all links: <a href="URL">TEXT</a>
    links = []
    for m in re.finditer(r'<a\s+href="([^"]*)"[^>]*>([^<]*)</a>', display_html):
        links.append((m.group(1), m.group(2)))
    
    # Step 3: Remove all remaining HTML tags except <br>
    display_html = re.sub(r'<br\s*/?>', '\n', display_html)
    display_html = re.sub(r'<[^>]+>', '', display_html)
    display_html = unescape(display_html)
    
    # Step 4: Now rebuild HTML with only repo names as clickable links
    for url, text in links:
        # Replace plain text occurrences with linked versions
        # Only link the repo name (first occurrence)
        display_html = display_html.replace(text, f'<a href="{url}">{text}</a>', 1)
    
    # Step 5: Clean up whitespace
    display_html = re.sub(r'\n{3,}', '\n\n', display_html)
    display_html = display_html.strip()
    
    # Convert newlines back to <br/> for HTML display
    display_html = display_html.replace('\n', '<br/>')
    
    msg["html"] = display_html
    
    # Also store plain text for fallback
    msg["text"] = re.sub(r'<[^>]+>', '', display_html)
    
    return msg


def parse_messages(html):
    """Extract messages from Telegram page HTML."""
    messages = []
    wrap_pattern = r'<div class="tgme_widget_message_wrap[^"]*">(.*?)</div>\s*</div>\s*</div>\s*</div>'
    blocks = re.findall(wrap_pattern, html, re.DOTALL)

    for block in blocks:
        msg = extract_meta_info(block)
        if msg and msg.get("text"):
            messages.append(msg)
    
    return messages


def write_output(messages, count):
    """Write RSS feed and index files."""
    from datetime import datetime, timezone
    now = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">')
    lines.append('<channel>')
    lines.append(f'  <title>{xml_escape(FEED_TITLE)}</title>')
    lines.append(f'  <link>{xml_escape(FEED_LINK)}</link>')
    lines.append(f'  <description>{xml_escape(FEED_DESC)}</description>')
    lines.append('  <language>zh-cn</language>')
    lines.append(f'  <lastBuildDate>{now}</lastBuildDate>')

    for msg in reversed(messages):
        lines.append('  <item>')
        lines.append(f'    <title>{xml_escape(msg.get("title", ""))}</title>')
        lines.append(f'    <link>{xml_escape(msg.get("link", ""))}</link>')
        lines.append(f'    <guid isPermaLink="true">{xml_escape(msg.get("link", ""))}</guid>')
        
        # Description with CDATA — only repo names are clickable links
        lines.append(f'    <description><![CDATA[{msg.get("html", "")}]]></description>')
        
        dt = msg.get("datetime", "")
        if dt:
            try:
                dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                lines.append(f'    <pubDate>{dt_obj.strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate>')
            except (ValueError, AttributeError):
                pass
        lines.append('  </item>')

    lines.append('</channel>')
    lines.append('</rss>')

    rss_str = '\n'.join(lines)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss_str)
    print(f"✅ RSS 已生成: {OUTPUT_FILE} ({count} 条消息)")

    # Write index.html
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


def xml_escape(text):
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text


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
        sys.exit(1)

    print(f"✅ 解析到 {len(messages)} 条消息")
    
    # Show preview
    for m in messages[:2]:
        title = m.get("title", "")
        print(f"  📰 {title[:50]}")
    
    write_output(messages, len(messages))


if __name__ == "__main__":
    main()
