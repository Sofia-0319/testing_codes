#!/usr/bin/env python3
"""
AI News to Discord Bot
Fetches AI news from RSS feeds and sends to Discord.
"""

import argparse
import feedparser
import requests
import time
import hashlib
import json
import os
import re
from datetime import datetime
from html import unescape

# =============================================================================
# CONFIGURATION
# =============================================================================

# Discord Webhook URL (reads from environment variable, falls back to hardcoded)
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1469922466930495553/yXGIQs8Hd6g5ZaUrcafcdKuMddewDe6pMZsFxuWdOPcs5F5jFTC_ytLbba2Wr0pb_NGZ"
)

# AI News RSS Feeds (verified working)
RSS_FEEDS = {
    # Company Blogs
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Google AI": "https://blog.research.google/feeds/posts/default?alt=rss",

    # Tech News
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",

    # Community
    "Hacker News AI": "https://hnrss.org/newest?q=AI+OR+GPT+OR+LLM+OR+Claude",
}

# Keywords to highlight with special emoji
HIGHLIGHT_KEYWORDS = [
    "Claude", "GPT-5", "GPT-4", "o1", "o3", "Gemini", "breakthrough",
    "AGI", "safety", "alignment", "reasoning", "benchmark"
]

# How often to check (seconds)
CHECK_INTERVAL = 21600  # 6 hours

# File to track sent articles
SENT_ARTICLES_FILE = "sent_articles.json"

# Max total articles per check (top 10)
MAX_TOTAL_ARTICLES = 10

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_sent_articles():
    if os.path.exists(SENT_ARTICLES_FILE):
        with open(SENT_ARTICLES_FILE, 'r') as f:
            return set(json.load(f))
    return set()


def save_sent_articles(sent):
    with open(SENT_ARTICLES_FILE, 'w') as f:
        json.dump(list(sent)[-2000:], f)


def get_article_id(entry):
    unique = entry.get('id', entry.get('link', entry.get('title', '')))
    return hashlib.md5(unique.encode()).hexdigest()


def clean_html(text):
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_highlight(text):
    """Check if contains highlight keywords."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in HIGHLIGHT_KEYWORDS)


def get_source_emoji(source_name):
    """Get emoji for different sources."""
    emojis = {
        "Anthropic": "🟠",
        "OpenAI": "🟢",
        "Google AI": "🔵",
        "DeepMind": "🧠",
        "Meta AI": "📘",
        "arXiv": "📄",
        "Hacker News": "🟧",
        "Reddit": "🔴",
    }
    for key, emoji in emojis.items():
        if key in source_name:
            return emoji
    return "📰"


def send_to_discord(source, title, link, summary=None, is_important=False):
    """Send article to Discord."""
    emoji = get_source_emoji(source)
    color = 0xFF6B00 if is_important else 0x5865F2  # Orange if important, Discord blue otherwise

    description = summary[:300] + "..." if summary and len(summary) > 300 else summary

    embed = {
        "embeds": [{
            "title": f"{emoji} {title[:200]}",
            "description": description,
            "url": link,
            "color": color,
            "footer": {"text": f"Source: {source}"},
            "timestamp": datetime.utcnow().isoformat()
        }]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=embed, timeout=10)
        if response.status_code == 204:
            return True
        elif response.status_code == 429:
            retry = response.json().get('retry_after', 5)
            time.sleep(retry)
            return send_to_discord(source, title, link, summary, is_important)
    except Exception as e:
        print(f"  ❌ Error: {e}")
    return False


def fetch_feed(name, url):
    """Fetch and parse RSS feed."""
    try:
        feed = feedparser.parse(url)
        if feed.entries:
            return feed.entries
    except Exception as e:
        print(f"  ⚠️ Error fetching {name}: {e}")
    return []


# =============================================================================
# MAIN
# =============================================================================

def check_all_feeds(sent_articles):
    # Collect all new articles from all feeds
    all_articles = []

    for source, url in RSS_FEEDS.items():
        print(f"📡 {source}...")
        entries = fetch_feed(source, url)

        if not entries:
            print("  ⚠️ No entries")
            continue

        for entry in entries[:5]:  # Check top 5 per source
            article_id = get_article_id(entry)
            if article_id in sent_articles:
                continue

            title = clean_html(entry.get('title', 'No title'))
            link = entry.get('link', '')
            summary = clean_html(entry.get('summary', entry.get('description', '')))
            is_important = is_highlight(title) or is_highlight(summary)

            all_articles.append({
                'source': source,
                'title': title,
                'link': link,
                'summary': summary,
                'is_important': is_important,
                'article_id': article_id
            })

    # Sort: important articles first, then limit to top 10
    all_articles.sort(key=lambda x: x['is_important'], reverse=True)
    top_articles = all_articles[:MAX_TOTAL_ARTICLES]

    # Send top 10
    new_count = 0
    for article in top_articles:
        if send_to_discord(article['source'], article['title'], article['link'],
                          article['summary'], article['is_important']):
            prefix = "⭐" if article['is_important'] else "✅"
            print(f"  {prefix} [{article['source']}] {article['title'][:40]}...")
            sent_articles.add(article['article_id'])
            new_count += 1
            time.sleep(1.5)

    return new_count


def main():
    parser = argparse.ArgumentParser(description="AI News to Discord Bot")
    parser.add_argument("--once", action="store_true", help="Run once and exit (for cron/GitHub Actions)")
    args = parser.parse_args()

    print("=" * 60)
    print("🤖 AI News to Discord Bot")
    print("=" * 60)
    print(f"📰 Monitoring {len(RSS_FEEDS)} sources:")
    for name in RSS_FEEDS.keys():
        print(f"   • {name}")
    print("=" * 60)

    sent = load_sent_articles()
    print(f"📁 Loaded {len(sent)} previously sent articles\n")

    if args.once:
        # Single run mode for GitHub Actions / cron
        print(f"🔄 Checking feeds at {datetime.now().strftime('%H:%M:%S')}...")
        new = check_all_feeds(sent)
        save_sent_articles(sent)
        print(f"\n📤 Sent {new} new articles to Discord")
    else:
        # Continuous loop mode
        while True:
            print(f"\n🔄 Checking feeds at {datetime.now().strftime('%H:%M:%S')}...")
            new = check_all_feeds(sent)
            save_sent_articles(sent)

            print(f"\n📤 Sent {new} new articles to Discord")
            print(f"⏳ Next check in {CHECK_INTERVAL // 60} minutes...")

            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
