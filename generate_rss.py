#!/usr/bin/env python3
"""
Telegram RSS Feed Generator
Scrapes Telegram public channel page and generates RSS XML with clickable links.
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import re
import time
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
    req = urllib.request.Request(TELEGRAM_URL, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def sanitize_html(raw_html):
    """
    Convert Telegram HTML to clean RSS-safe HTML.
    - Keep <a href="..."> links (strip onclick, target, rel)
    - Keep <br> and <br/>
    - Keep <b>, <i>, <strong>, <em> for formatting
    - Keep <span>, <code> but strip their attributes
    - Strip everything else
    """
    # Strip unwanted attributes from <a> tags — keep only href
    raw_html = re.sub(
        r'<a\s+([^>]*?)href="([^"]*)"([^>]*)>',
        lambda m: f'<a href="{m.group(2)}">',
        raw_html
    )
    # Strip onclick from remaining <a> tags
    raw_html = re.sub(r'\son\w+="[^"]*"', '', raw_html)
    # Remove style attributes from all tags
    raw_html = re.sub(r'\sstyle="[^"]*"', '', raw_html)
    # Remove class attributes from all tags
    raw_html = re.sub(r'\sclass="[^"]*"', '', raw_html)
    # Remove dir attributes
    raw_html = re.sub(r'\sdir="[^"]*"', '', raw_html)

    # Allowed tags (keep them as-is)
    allowed = {'a', 'b', 'i', 'strong', 'em', 'br', 'code', 'span', 'pre'}
    # Strip all other tags but keep their content
    def strip_tag(m):
        tag = m.group(1).lower().split()[0] if m.group(1) else ''
        if tag in allowed:
            return m.group(0)  # keep the tag
        # Closing tag for non-allowed
        if m.group(0).startswith('</'):
            return ''
        return ''  # strip opening tag

    # Process opening tags
    raw_html = re.sub(r'<(/)?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>', 
                      lambda m: '' if m.group(1) else (m.group(0) if m.group(2).lower() in allowed else ''),
                      raw_html)

    # Decode entities
    raw_html = unescape(raw_html)
    return raw_html.strip()


def to_plain_text(html_text):
    """Convert HTML to plain text (for title extraction)."""
    text = re.sub(r'<br\s*/?>', '\n', html_text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_messages(html):
    """Extract messages from Telegram page HTML."""
    messages = []
    wrap_pattern = r'<div class="tgme_widget_message_wrap[^"]*">(.*?)</div>\s*</div>\s*</div>\s*</div>'
    blocks = re.findall(wrap_pattern, html, re.DOTALL)

    for block in blocks:
        msg = {}

        # Message link and ID
        link_match = re.search(r'data-post="([^"]+)"', block)
        if link_match:
            post_id = link_match.group(1)
            msg["id"] = post_id
            msg["link"] = f"https://t.me/{post_id}"

        # Datetime
        dt_match = re.search(r'<time datetime="([^"]+)"', block)
        if dt_match:
            msg["datetime"] = dt_match.group(1)

        # Text content — preserve raw HTML for description
        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*(?:</div>\s*)?<div class="tgme_widget_message_footer',
            block, re.DOTALL
        )
        if text_match:
            raw_html = text_match.group(1)
            msg["html"] = sanitize_html(raw_html)
            plain = to_plain_text(raw_html)
            if plain:
                msg["text"] = plain
                lines = [l.strip() for l in plain.split('\n') if l.strip()]
                msg["title"] = lines[0] if lines else f"Post {post_id}"

        # Images
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

    for msg in reversed(messages):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = msg.get("title", f"Post {msg.get('id', '')}")

        link = msg.get("link", "")
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "guid", isPermaLink="true").text = link

        # Description: use preserved HTML with images + clickable links
        desc_parts = []
        for img in msg.get("images", []):
            desc_parts.append(f'<img src="{img}" /><br/>')

        html_content = msg.get("html", "")
        # Convert plain newlines to <br/> for the HTML description
        html_content = html_content.replace('\n', '<br/>')
        desc_parts.append(html_content)

        # Use CDATA to safely embed HTML in XML
        desc_html = "".join(desc_parts)
        # Create description as CDATA section
        desc_elem = ET.SubElement(item, "description")
        desc_elem.text = None  # clear text
        desc_elem.append(ET.Comment("]]>"))  # hack to insert CDATA
        # Actually, ET doesn't support CDATA natively. Use _children trick.
        # Better approach: just XML-escape, but since XML doesn't handle raw HTML
        # well in text nodes, we'll wrap in CDATA manually when serializing.

        # Store raw HTML in a custom attribute and handle serialization
        item.set("_cdata_description", desc_html)

        # Also set as plain text fallback
        ET.SubElement(item, "description").text = msg.get("text", "")

        # Remove the duplicate description we just added, we'll handle it via CDATA
        item.remove(list(item)[-1])

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


def serialize_rss(rss_elem):
    """Custom serialization that handles CDATA for descriptions."""
    rough = ET.tostring(rss_elem, encoding="unicode", xml_declaration=True)
    
    # Replace placeholder description elements with CDATA-wrapped versions
    for item in rss_elem.findall('.//item'):
        cdata_html = item.get("_cdata_description", "")
        if cdata_html:
            # In the rough string, find this item's empty description
            # and replace it with CDATA
            pass  # We'll do a simpler approach below
    
    # Simpler approach: serialize normally, then replace placeholders
    # Actually, let's just build XML string manually for descriptions
    return rough


def write_output(msg_list, messages_count):
    """Write RSS feed and index files with proper CDATA sections."""
    # Build the XML string with CDATA for descriptions
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">')
    lines.append('<channel>')
    
    from datetime import datetime, timezone
    now = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

    for item_data in msg_list:
        lines.append('<item>')
        lines.append(f'  <title>{xml_escape(item_data.get("title", ""))}</title>')
        lines.append(f'  <link>{xml_escape(item_data.get("link", ""))}</link>')
        lines.append(f'  <guid isPermaLink="true">{xml_escape(item_data.get("link", ""))}</guid>')
        
        # Description with CDATA (preserves HTML links)
        desc_parts = []
        for img in item_data.get("images", []):
            desc_parts.append(f'<img src="{xml_escape(img)}" /><br/>')
        html_content = item_data.get("html", "").replace('\n', '<br/>')
        desc_parts.append(html_content)
        lines.append(f'  <description><![CDATA[{"".join(desc_parts)}]]></description>')
        
        # Date
        dt = item_data.get("datetime", "")
        if dt:
            try:
                dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                lines.append(f'  <pubDate>{dt_obj.strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate>')
            except (ValueError, AttributeError):
                pass
        
        lines.append('</item>')
    
    lines.append('</channel>')
    lines.append('</rss>')

    rss_str = "\n".join(lines)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss_str)
    print(f"✅ RSS 已生成: {OUTPUT_FILE} ({messages_count} 条消息，含可点击链接)")

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
    <p class="info">自动生成的 RSS 订阅源，每 30 分钟更新一次。链接可直接点击跳转。</p>
    <p><a class="rss-link" href="feed.xml">📡 订阅 RSS Feed</a></p>
    <p class="info">最后更新: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}</p>
    <p>订阅地址: <code>https://birdplus.github.io/rss-telegram-feed/feed.xml</code></p>
</body>
</html>"""
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 页面已生成: {INDEX_FILE}")


def xml_escape(text):
    """Escape text for XML."""
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
        rss_str = '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>Telegram: Githubrebang</title><link>https://t.me/Githubrebang</link><description>RSS feed</description></channel></rss>'
        with open(OUTPUT_FILE, "w") as f:
            f.write(rss_str)
        sys.exit(1)

    print(f"✅ 解析到 {len(messages)} 条消息")
    write_output(messages, len(messages))


if __name__ == "__main__":
    main()
