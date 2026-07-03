import os
import re
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser
import yfinance as yf
from google import genai
from google.genai import types


DATA_DIR = "data"
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
RESULTS_PATH = os.path.join(DATA_DIR, "results.json")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
MAX_NEWS = int(os.getenv("MAX_NEWS", "8"))


def now_text() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: str, fallback: Any) -> Any:
    if not os.path.exists(path):
        return fallback

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_current_price(yf_symbol: str) -> Optional[float]:
    if not yf_symbol:
        return None

    try:
        ticker = yf.Ticker(yf_symbol)

        try:
            fast_price = ticker.fast_info.get("last_price")
            if fast_price:
                return round(float(fast_price), 2)
        except Exception:
            pass

        history = ticker.history(period="5d")
        if history.empty:
            return None

        return round(float(history["Close"].dropna().iloc[-1]), 2)

    except Exception:
        return None


def update_portfolio_prices(portfolio: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    updated = []

    for asset in portfolio:
        item = dict(asset)
        yf_symbol = str(item.get("yf_symbol") or item.get("symbol") or "").strip()
        price = fetch_current_price(yf_symbol)

        if price is not None:
            item["current_price"] = price

        updated.append(item)

    return updated


def build_google_news_rss_url(query: str, lang: str = "en-US", country: str = "US") -> str:
    encoded_query = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded_query}&hl={lang}&gl={country}&ceid={country}:en"


def get_news_queries(portfolio: List[Dict[str, Any]]) -> List[str]:
    symbols = [str(item.get("symbol", "")).strip() for item in portfolio if item.get("symbol")]
    symbol_query = " OR ".join(symbols[:14])

    return [
        f"({symbol_query}) stock market earnings analyst rating",
        "NVDA OR AMD OR TSM OR INTC semiconductor AI chip news",
        "GOOGL OR Alphabet AI cloud antitrust earnings news",
        "VOO OR S&P 500 ETF Federal Reserve inflation interest rates",
        "BND OR bond yields Treasury interest rates inflation",
        "CPALL Thailand stock SET retail earnings"
    ]


def fetch_news(portfolio: List[Dict[str, Any]], limit: int = MAX_NEWS) -> List[Dict[str, Any]]:
    seen = set()
    news_items = []

    for query in get_news_queries(portfolio):
        feed = feedparser.parse(build_google_news_rss_url(query))

        for entry in feed.entries[:8]:
            url = entry.get("link", "")
            title = entry.get("title", "")

            key = url or title
            if not key or key in seen:
                continue

            seen.add(key)

            source = "Google News RSS"
            try:
                source = entry.get("source", {}).get("title") or source
            except Exception:
                pass

            news_items.append({
                "title": title,
                "source": source,
                "description": entry.get("summary", ""),
                "content": entry.get("summary", ""),
                "url": url,
                "published_at": entry.get("published", "")
            })

            if len(news_items) >= limit:
                return news_items

    return news_items


def clean_json_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "", 1).strip()

    if text.startswith("```"):
        text = text.replace("```", "", 1).strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return match.group(0)

    return text


def assets_at_buy_target(portfolio: List[Dict[str, Any]]) -> List[str]:
    triggered = []

    for asset in portfolio:
        current = asset.get("current_price")
        target = asset.get("buy_target_price")

        if current is None or target is None:
            continue

        try:
            if float(current) <= float(target):
                triggered.append(str(asset.get("symbol", "")))
        except Exception:
            continue

    return [item for item in triggered if item]


def normalize_result(
    ai_result: Dict[str, Any],
    news_item: Dict[str, Any],
    portfolio: List[Dict[str, Any]]
) -> Dict[str, Any]:
    impact_level = str(ai_result.get("impact_level", "Low")).strip()
    if impact_level not in ["High", "Medium", "Low"]:
        impact_level = "Low"

    affected_assets = ai_result.get("affected_assets", [])
    if not isinstance(affected_assets, list):
        affected_assets = [str(affected_assets)]

    analysis_summary = str(ai_result.get("analysis_summary", "ไม่มีสรุป"))
    action_recommendation = str(ai_result.get("action_recommendation", "รอดูสถานการณ์"))
    trigger_alert = bool(ai_result.get("trigger_alert", False))

    target_assets = assets_at_buy_target(portfolio)

    if impact_level == "High":
        trigger_alert = True

    if target_assets:
        trigger_alert = True
        action_recommendation += f" | ราคาแตะหรือต่ำกว่าเป้าซื้อ: {', '.join(target_assets)}"

    return {
        "time": now_text(),
        "news_title": news_item.get("title", ""),
        "source": news_item.get("source", ""),
        "impact_level": impact_level,
        "affected_assets": affected_assets,
        "analysis_summary": analysis_summary,
        "action_recommendation": action_recommendation,
        "trigger_alert": trigger_alert,
        "url": news_item.get("url", "")
    }


def build_prompt(portfolio: List[Dict[str, Any]], news_item: Dict[str, Any]) -> str:
    return f"""
บทบาท: คุณคือ AI ผู้ช่วยวิเคราะห์การลงทุนส่วนตัวและประเมินความเสี่ยงระดับโลก

งาน:
วิเคราะห์ข่าวล่าสุดต่อพอร์ตการลงทุน โดยตอบเป็น JSON เท่านั้น

เกณฑ์:
- impact_level ต้องเป็น High, Medium หรือ Low
- trigger_alert เป็น true เฉพาะเมื่อข่าวกระทบแรงระดับ High หรือมีสัญญาณควรสนใจทันที
- ถ้าข่าวไม่เกี่ยวกับหุ้น/ETF ในพอร์ต ให้ impact_level เป็น Low
- คำแนะนำต้องระบุว่า รอดูสถานการณ์ / พิจารณาซื้อเพิ่ม / ลดความเสี่ยง / ถือ ต่อให้เหมาะสม
- สรุปไม่เกิน 3 บรรทัด
- ห้ามใส่ markdown ห้ามใส่คำอธิบายนอก JSON

JSON schema:
{{
  "impact_level": "High",
  "affected_assets": ["NVDA"],
  "analysis_summary": "สรุปผลกระทบสั้นๆ",
  "action_recommendation": "คำแนะนำสั้นๆ",
  "trigger_alert": true
}}

PORTFOLIO:
{json.dumps(portfolio, ensure_ascii=False, indent=2)}

NEWS:
Title: {news_item.get("title", "")}
Source: {news_item.get("source", "")}
Published: {news_item.get("published_at", "")}
Summary: {news_item.get("description", "")}
Content: {news_item.get("content", "")}
URL: {news_item.get("url", "")}
"""


def analyze_with_gemini(news_item: Dict[str, Any], portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        return normalize_result(
            {
                "impact_level": "Low",
                "affected_assets": [],
                "analysis_summary": "ยังไม่ได้ตั้งค่า GEMINI_API_KEY ใน GitHub Secrets",
                "action_recommendation": "เพิ่ม Secret ชื่อ GEMINI_API_KEY ก่อน แล้วกด Run workflow อีกครั้ง",
                "trigger_alert": False
            },
            news_item,
            portfolio
        )

    client = genai.Client(api_key=GEMINI_API_KEY)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_prompt(portfolio, news_item),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )

    parsed = json.loads(clean_json_text(response.text))

    return normalize_result(parsed, news_item, portfolio)


def main() -> None:
    portfolio = load_json(PORTFOLIO_PATH, [])
    portfolio = update_portfolio_prices(portfolio)
    save_json(PORTFOLIO_PATH, portfolio)

    news_items = fetch_news(portfolio, limit=MAX_NEWS)

    if not news_items:
        save_json(RESULTS_PATH, [{
            "time": now_text(),
            "news_title": "ไม่พบข่าวจาก RSS",
            "source": "System",
            "impact_level": "Low",
            "affected_assets": [],
            "analysis_summary": "ระบบดึงข่าวจาก Google News RSS ไม่สำเร็จหรือไม่มีข่าวใหม่",
            "action_recommendation": "รอดูสถานการณ์",
            "trigger_alert": False,
            "url": ""
        }])
        return

    results = []

    for news_item in news_items:
        try:
            results.append(analyze_with_gemini(news_item, portfolio))
        except Exception as exc:
            results.append(normalize_result(
                {
                    "impact_level": "Low",
                    "affected_assets": [],
                    "analysis_summary": f"วิเคราะห์ข่าวนี้ไม่สำเร็จ: {exc}",
                    "action_recommendation": "รอดูสถานการณ์",
                    "trigger_alert": False
                },
                news_item,
                portfolio
            ))

    save_json(RESULTS_PATH, results)


if __name__ == "__main__":
    main()
