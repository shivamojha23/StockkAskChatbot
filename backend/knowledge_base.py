"""
knowledge_base.py — Static knowledge base for StockkAsk.

This module holds the structured FAQ and glossary data that
gets ingested into the vector DB. It is the single source of
truth for the chatbot's knowledge about the platform.

Update this file when new features are added to StockkAsk and
re-run ingest.py to refresh the vector DB.
"""

from typing import TypedDict


class KnowledgeEntry(TypedDict):
    id: str          # Unique, stable identifier for upsert idempotency
    category: str    # Grouping label used as metadata for filtered search
    title: str       # Short heading — used as chunk title in prompts
    content: str     # The body text that gets embedded


# ---------------------------------------------------------------------------
# PLATFORM OVERVIEW
# ---------------------------------------------------------------------------
PLATFORM_OVERVIEW: list[KnowledgeEntry] = [
    {
        "id": "platform-001",
        "category": "platform",
        "title": "What is StockkAsk?",
        "content": (
            "StockkAsk (also written as StockkASK) is an AI-powered stock research "
            "and market intelligence platform built for NSE and BSE. It is powered by "
            "Indira Securities Pvt. Ltd., a SEBI-registered stockbroker with over "
            "38 years of market experience. The platform provides traders, investors, "
            "and market learners with fundamentals, technicals, live news, smart screening, "
            "and trade opportunities — all in one place, completely free to use."
        ),
    },
    {
        "id": "platform-002",
        "category": "platform",
        "title": "Who built StockkAsk and is it trustworthy?",
        "content": (
            "StockkAsk is built by Indira Securities Pvt. Ltd., a SEBI-registered "
            "stockbroker with 38+ years of market legacy. The platform is not a "
            "financial advisor — it provides data-driven insights to support your own "
            "independent analysis. All investment decisions remain solely yours. "
            "Indira Securities is regulated by SEBI (Securities and Exchange Board of India)."
        ),
    },
    {
        "id": "platform-003",
        "category": "platform",
        "title": "Is StockkAsk free to use?",
        "content": (
            "Yes, StockkAsk is completely free to use. You can access live news, "
            "the Smart Screener, Trade Opportunities, and company-level research "
            "without any subscription fee. Some advanced features may require you "
            "to log in or open a demat account with Indira Securities."
        ),
    },
    {
        "id": "platform-004",
        "category": "platform",
        "title": "How do I get started with StockkAsk?",
        "content": (
            "To get started, visit https://stockk.trade/stockkask/. You can explore "
            "the platform as a Guest User without logging in. To access full features "
            "including live prices, saved screens, and personalised analysis, click "
            "'Login' or 'Open Account' in the top navigation bar. Opening a demat "
            "account with Indira Securities is done via https://isplkyc.indiratrade.com/."
        ),
    },
    {
        "id": "platform-005",
        "category": "platform",
        "title": "What exchanges does StockkAsk cover?",
        "content": (
            "StockkAsk covers stocks listed on the NSE (National Stock Exchange) "
            "and BSE (Bombay Stock Exchange) — the two primary stock exchanges "
            "in India. Both equity and derivative instruments are covered across "
            "large-cap, mid-cap, and small-cap segments."
        ),
    },
]

# ---------------------------------------------------------------------------
# FEATURE: STOCCKGPT (AI CHATBOT)
# ---------------------------------------------------------------------------
STOCKKGPT: list[KnowledgeEntry] = [
    {
        "id": "gpt-001",
        "category": "feature",
        "title": "What is StockkGPT?",
        "content": (
            "StockkGPT is the AI chatbot embedded within StockkAsk, built by "
            "Indira Securities. It helps users understand stocks, navigate platform "
            "features, and interpret financial data in plain English. StockkGPT does "
            "NOT provide buy/sell recommendations or financial advice. It is purely "
            "an educational and navigational assistant."
        ),
    },
    {
        "id": "gpt-002",
        "category": "feature",
        "title": "Can StockkGPT give me stock tips or financial advice?",
        "content": (
            "No. StockkGPT is strictly a platform guide and information assistant. "
            "It cannot and will not recommend stocks to buy or sell, predict price "
            "movements, or suggest investment strategies. This is mandated by SEBI "
            "regulations. For investment advice, consult a SEBI-registered investment "
            "advisor. StockkAsk's role is to give you the data and tools to make "
            "your own informed decisions."
        ),
    },
]

# ---------------------------------------------------------------------------
# FEATURE: SMART SCREENER
# ---------------------------------------------------------------------------
SMART_SCREENER: list[KnowledgeEntry] = [
    {
        "id": "screener-001",
        "category": "feature",
        "title": "What is the Smart Screener?",
        "content": (
            "The Smart Screener is an AI-driven stock discovery tool on StockkAsk "
            "that scans the NSE and BSE markets based on technical and fundamental "
            "criteria. It helps traders and investors effortlessly filter, sort, and "
            "identify potential investment opportunities based on advanced analytics "
            "and personalised criteria. You can access it at "
            "https://stockk.trade/stockkask/smart-screener."
        ),
    },
    {
        "id": "screener-002",
        "category": "feature",
        "title": "How does the Smart Screener work?",
        "content": (
            "The Smart Screener uses AI to apply pre-built or custom filters across "
            "thousands of NSE/BSE stocks simultaneously. You can screen by technical "
            "signals (such as RSI, moving averages, breakout patterns) and fundamental "
            "metrics (such as P/E ratio, revenue growth, debt levels). The screener "
            "returns a ranked list of stocks matching your criteria, helping you "
            "narrow down your watchlist quickly."
        ),
    },
    {
        "id": "screener-003",
        "category": "feature",
        "title": "What filters are available in the Smart Screener?",
        "content": (
            "The Smart Screener offers filters across technical indicators "
            "(RSI, MACD, Bollinger Bands, moving averages), fundamental metrics "
            "(earnings growth, P/E, P/B ratios, debt-to-equity), volume and price "
            "action, sector/industry classification, and market cap segments "
            "(large-cap, mid-cap, small-cap). Filters can be combined to create "
            "highly specific screens."
        ),
    },
]

# ---------------------------------------------------------------------------
# FEATURE: LIVE NEWS & NEWS TIMELINE
# ---------------------------------------------------------------------------
LIVE_NEWS: list[KnowledgeEntry] = [
    {
        "id": "news-001",
        "category": "feature",
        "title": "What is the News Timeline / Live News feature?",
        "content": (
            "The News Timeline (Live News) is a real-time news feed on StockkAsk "
            "that aggregates market-moving news for NSE and BSE stocks. Each news "
            "item is enriched with real-time price impact context — meaning you can "
            "see how a news story has affected (or is affecting) a stock's price "
            "movement. Access it at https://stockk.trade/stockkask/live-news."
        ),
    },
    {
        "id": "news-002",
        "category": "feature",
        "title": "How is Live News different from regular financial news?",
        "content": (
            "Unlike generic financial news aggregators, StockkAsk's Live News is "
            "stock-specific. Each news event is mapped to the relevant company and "
            "presented alongside the stock's live price data, so you can instantly "
            "see the market's reaction. This contextual overlay saves time and helps "
            "you understand news impact without switching between multiple platforms."
        ),
    },
]

# ---------------------------------------------------------------------------
# FEATURE: TRADE OPPORTUNITIES
# ---------------------------------------------------------------------------
TRADE_OPPORTUNITIES: list[KnowledgeEntry] = [
    {
        "id": "trade-001",
        "category": "feature",
        "title": "What are Trade Opportunities?",
        "content": (
            "Trade Opportunities is a curated section on StockkAsk that surfaces "
            "stocks exhibiting specific technical setups or fundamental triggers — "
            "such as breakouts, high-volume moves, or earnings surprises. It is "
            "designed to give traders a starting point for their own analysis. "
            "Available at https://stockk.trade/stockkask/trade-opportunities. "
            "Note: these are NOT buy/sell recommendations — they are data-driven "
            "observations for your own evaluation."
        ),
    },
]

# ---------------------------------------------------------------------------
# GLOSSARY: FUNDAMENTAL ANALYSIS TERMS
# ---------------------------------------------------------------------------
FUNDAMENTALS_GLOSSARY: list[KnowledgeEntry] = [
    {
        "id": "gloss-moat-001",
        "category": "glossary",
        "title": "What does 'Moat' mean in StockkAsk?",
        "content": (
            "In StockkAsk's Fundamental Analysis section, 'Moat' refers to a company's "
            "economic moat — its competitive advantage that protects its long-term profits "
            "from competitors. The term was popularised by Warren Buffett. A wide moat "
            "means the company has strong, durable advantages (e.g., brand, patents, "
            "network effects, cost leadership, switching costs). A narrow or no moat "
            "means competition can erode the company's profits more easily."
        ),
    },
    {
        "id": "gloss-001",
        "category": "glossary",
        "title": "What is Fundamental Analysis on StockkAsk?",
        "content": (
            "The Fundamental Analysis section on a stock's page in StockkAsk gives you "
            "a complete picture of the company's financial health. It covers revenue, "
            "profit, margins, debt, return ratios (ROE, ROCE), earnings growth, valuation "
            "multiples (P/E, P/B, EV/EBITDA), and qualitative factors like competitive "
            "positioning (Moat). The goal is to help you assess whether a company is "
            "fundamentally strong independent of short-term price movements."
        ),
    },
    {
        "id": "gloss-002",
        "category": "glossary",
        "title": "What does P/E Ratio mean?",
        "content": (
            "P/E (Price-to-Earnings) Ratio is the stock's current price divided by its "
            "earnings per share (EPS). It tells you how much the market is willing to pay "
            "for each rupee of earnings. A high P/E may indicate growth expectations; "
            "a low P/E may signal undervaluation or a value trap. Always compare P/E "
            "within the same sector."
        ),
    },
    {
        "id": "gloss-003",
        "category": "glossary",
        "title": "What is ROE (Return on Equity)?",
        "content": (
            "ROE (Return on Equity) measures how efficiently a company uses shareholders' "
            "equity to generate profit. It is calculated as Net Profit / Shareholders' "
            "Equity × 100. A consistently high ROE (above 15-20%) generally indicates "
            "a well-managed, profitable business. StockkAsk displays ROE in the "
            "Fundamental Analysis section of each stock's profile."
        ),
    },
    {
        "id": "gloss-004",
        "category": "glossary",
        "title": "What is ROCE (Return on Capital Employed)?",
        "content": (
            "ROCE measures profitability relative to total capital employed (equity + debt). "
            "It is a better metric than ROE for capital-intensive businesses. ROCE = EBIT / "
            "Capital Employed × 100. A ROCE higher than the company's cost of capital "
            "indicates value creation. StockkAsk shows ROCE alongside other return "
            "ratios in the Fundamentals section."
        ),
    },
    {
        "id": "gloss-005",
        "category": "glossary",
        "title": "What is Debt-to-Equity (D/E) ratio?",
        "content": (
            "Debt-to-Equity ratio compares a company's total debt to its shareholders' "
            "equity. D/E = Total Debt / Shareholders' Equity. A D/E above 1 means the "
            "company uses more debt than equity financing. Very high D/E can be a risk "
            "signal, especially in a rising interest rate environment. In StockkAsk, "
            "D/E is shown in the Fundamental Analysis section."
        ),
    },
    {
        "id": "gloss-006",
        "category": "glossary",
        "title": "What is EPS (Earnings Per Share)?",
        "content": (
            "EPS is a company's net profit divided by the total number of outstanding shares. "
            "It represents the portion of a company's profit allocated to each share. Growing "
            "EPS over time is a positive indicator. Diluted EPS accounts for stock options "
            "and convertible securities. StockkAsk tracks EPS trends in the financials view."
        ),
    },
    {
        "id": "gloss-007",
        "category": "glossary",
        "title": "What does 'Market Cap' mean?",
        "content": (
            "Market Capitalisation (Market Cap) is the total market value of a company's "
            "outstanding shares. Market Cap = Current Share Price × Total Shares Outstanding. "
            "In India, large-cap stocks are typically the top 100 by market cap, mid-caps are "
            "101–250, and small-caps are below that. StockkAsk displays market cap and "
            "classifies stocks accordingly."
        ),
    },
]

# ---------------------------------------------------------------------------
# GLOSSARY: TECHNICAL ANALYSIS TERMS
# ---------------------------------------------------------------------------
TECHNICALS_GLOSSARY: list[KnowledgeEntry] = [
    {
        "id": "tech-001",
        "category": "glossary",
        "title": "What is RSI (Relative Strength Index)?",
        "content": (
            "RSI is a momentum oscillator ranging from 0 to 100, measuring the speed "
            "and magnitude of price movements. RSI above 70 is typically considered "
            "overbought (potential reversal down), while below 30 is oversold (potential "
            "reversal up). StockkAsk's Smart Screener uses RSI as one of its technical "
            "filters. It is a 14-day RSI by default."
        ),
    },
    {
        "id": "tech-002",
        "category": "glossary",
        "title": "What is MACD?",
        "content": (
            "MACD (Moving Average Convergence Divergence) is a trend-following momentum "
            "indicator. It is calculated by subtracting the 26-period EMA from the 12-period "
            "EMA. The 'signal line' is a 9-period EMA of MACD. A bullish crossover (MACD "
            "crossing above signal) is a potential buy signal; a bearish crossover is a "
            "potential sell signal. Used extensively in StockkAsk's technical screens."
        ),
    },
    {
        "id": "tech-003",
        "category": "glossary",
        "title": "What are Moving Averages (MA, EMA, SMA)?",
        "content": (
            "A Moving Average smooths out price data over a specific period. SMA (Simple "
            "Moving Average) gives equal weight to all periods. EMA (Exponential Moving "
            "Average) gives more weight to recent prices. Common periods are 20-day, 50-day, "
            "and 200-day. A stock trading above its 200-day MA is considered in a long-term "
            "uptrend. StockkAsk's screener lets you filter by MA conditions."
        ),
    },
    {
        "id": "tech-004",
        "category": "glossary",
        "title": "What are Bollinger Bands?",
        "content": (
            "Bollinger Bands consist of a middle band (20-day SMA) and two outer bands "
            "set 2 standard deviations above and below the middle. When price touches "
            "the upper band, the stock may be overbought; lower band suggests oversold. "
            "A 'Bollinger Band squeeze' (bands narrowing) often precedes a significant "
            "price breakout. Available as a filter in StockkAsk's Smart Screener."
        ),
    },
]

# ---------------------------------------------------------------------------
# FAQs: ACCOUNT & PLATFORM USAGE
# ---------------------------------------------------------------------------
ACCOUNT_FAQS: list[KnowledgeEntry] = [
    {
        "id": "faq-acc-001",
        "category": "faq",
        "title": "How do I create an account on StockkAsk?",
        "content": (
            "To create a full account with live prices and personalised features, you need "
            "to open a demat account with Indira Securities at https://isplkyc.indiratrade.com/. "
            "Once your demat account is active, use those credentials to log into StockkAsk. "
            "As a guest user, you can still access most features without logging in."
        ),
    },
    {
        "id": "faq-acc-002",
        "category": "faq",
        "title": "Why can't I see live prices?",
        "content": (
            "Live prices on StockkAsk require you to be logged in. If you see a message "
            "saying 'To see live prices kindly Login', please click the Login button in "
            "the top navigation and enter your Indira Securities credentials. If you do "
            "not have an account, open one at https://isplkyc.indiratrade.com/."
        ),
    },
    {
        "id": "faq-acc-003",
        "category": "faq",
        "title": "Is my data safe on StockkAsk?",
        "content": (
            "Yes. StockkAsk is governed by the Privacy Policy of Indira Securities Pvt. Ltd., "
            "which commits to protecting your personal and financial information. The platform "
            "only collects the minimum data necessary to provide its services. Personal data "
            "is not sold to third parties. The platform uses TradingView for charting "
            "technology. Full privacy policy: https://stockk.trade/stockkask/privacy-policy."
        ),
    },
    {
        "id": "faq-acc-004",
        "category": "faq",
        "title": "What charting technology does StockkAsk use?",
        "content": (
            "StockkAsk uses TradingView's charting technology — a globally trusted trading "
            "platform offering advanced market data, strategy testers, heatmaps, and a "
            "real-time economic calendar. The integration brings institutional-grade charts "
            "directly into the StockkAsk interface."
        ),
    },
    {
        "id": "faq-acc-005",
        "category": "faq",
        "title": "What is Indira Securities?",
        "content": (
            "Indira Securities Pvt. Ltd. is a SEBI-registered stockbroker headquartered "
            "in India with over 38 years of market experience. The company offers broking, "
            "research, and now AI-powered market intelligence through StockkAsk. Indira "
            "Securities is the parent company and compliance entity behind the StockkAsk "
            "and StockkGPT platforms."
        ),
    },
    {
        "id": "faq-acc-006",
        "category": "faq",
        "title": "What is the Terms of Use for StockkAsk?",
        "content": (
            "The full Terms of Use for StockkAsk can be found at "
            "https://stockk.trade/stockkask/terms-and-conditions. Key points: "
            "StockkAsk provides data and AI insights for informational purposes only, "
            "not investment advice. Users are responsible for their own investment decisions. "
            "The platform is provided by Indira Securities Pvt. Ltd. and is subject to "
            "SEBI regulations."
        ),
    },
    {
        "id": "faq-acc-007",
        "category": "faq",
        "title": "How do I navigate to a specific stock on StockkAsk?",
        "content": (
            "Use the search bar at the top of the StockkAsk platform. Type the stock name "
            "or symbol (e.g., 'RELIANCE', 'ICICIBANK', 'TCS', 'HDFCBANK'). The search "
            "supports NSE and BSE symbols. Select the stock from the dropdown to open its "
            "detailed analysis page featuring fundamentals, technicals, news, and AI insights."
        ),
    },
    {
        "id": "faq-acc-008",
        "category": "faq",
        "title": "What popular stocks are available on StockkAsk?",
        "content": (
            "StockkAsk covers all NSE and BSE listed stocks. Popular stocks include "
            "RELIANCE (Reliance Industries), ICICIBANK (ICICI Bank), HDFCBANK (HDFC Bank), "
            "TCS (Tata Consultancy Services), INFY (Infosys), BSE (BSE Ltd), and thousands "
            "more across all market cap segments and sectors."
        ),
    },
]

# ---------------------------------------------------------------------------
# DISCLAIMER
# ---------------------------------------------------------------------------
DISCLAIMER: list[KnowledgeEntry] = [
    {
        "id": "disc-001",
        "category": "compliance",
        "title": "SEBI disclaimer and investment responsibility",
        "content": (
            "StockkAsk provides smart, data-driven insights to support your own independent "
            "analysis. Review all information independently and invest responsibly. "
            "StockkAsk does NOT provide investment advice, stock tips, or trading recommendations. "
            "All investment decisions are solely the user's responsibility. "
            "Indira Securities Pvt. Ltd. is a SEBI-registered stockbroker, not a SEBI-registered "
            "investment advisor. Past performance of any stock is not indicative of future returns. "
            "Equity investments are subject to market risk."
        ),
    },
]


def get_all_knowledge() -> list[KnowledgeEntry]:
    """Return the complete, flat knowledge base list."""
    return (
        PLATFORM_OVERVIEW
        + STOCKKGPT
        + SMART_SCREENER
        + LIVE_NEWS
        + TRADE_OPPORTUNITIES
        + FUNDAMENTALS_GLOSSARY
        + TECHNICALS_GLOSSARY
        + ACCOUNT_FAQS
        + DISCLAIMER
    )
