from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx
import asyncio
from datetime import datetime
import os
import glob

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FINNHUB_KEY = os.getenv("FINNHUB_KEY", "d8gqq09r01qhjpmp8fe0d8gqq09r01qhjpmp8feg")
cache = {}
CACHE_TTL = 60


def cached(key, data):
    cache[key] = (data, datetime.now())
    return data


def get_cache(key):
    if key not in cache:
        return None
    data, ts = cache[key]
    if (datetime.now() - ts).seconds < CACHE_TTL:
        return data
    return None


async def finnhub_quote(client, symbol):
    try:
        r = await client.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=4.0
        )
        d = r.json()
        if d.get("c", 0) > 0:
            return {"price": d["c"], "change": d["dp"], "prev": d["pc"]}
    except Exception:
        pass
    return None


async def yahoo_quote(client, symbol):
    try:
        r = await client.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "5d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=4.0
        )
        d = r.json()
        res = d["chart"]["result"][0]
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c]
        if len(closes) >= 2:
            prev, curr = closes[-2], closes[-1]
            return {"price": curr, "change": ((curr - prev) / prev) * 100, "prev": prev}
    except Exception:
        pass
    return None


US_SECTORS = ["XLK", "XLC", "XLY", "XLF", "XLV", "XLI", "XLE", "XLP", "XLU", "XLB", "XLRE"]
KR_SECTORS = ["005930.KS", "373220.KS", "207940.KS", "005380.KS", "035420.KS",
              "105560.KS", "005490.KS", "051910.KS", "041510.KS", "012450.KS", "000720.KS"]


@app.get("/api/sectors/us")
async def us_sectors():
    data = get_cache("us_sectors")
    if data:
        return data
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[finnhub_quote(client, s) for s in US_SECTORS])
    return cached("us_sectors", {sym: res for sym, res in zip(US_SECTORS, results)})


@app.get("/api/sectors/kr")
async def kr_sectors():
    data = get_cache("kr_sectors")
    if data:
        return data
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[yahoo_quote(client, s) for s in KR_SECTORS])
    return cached("kr_sectors", {sym: res for sym, res in zip(KR_SECTORS, results)})


@app.get("/api/indices")
async def indices():
    data = get_cache("indices")
    if data:
        return data
    async with httpx.AsyncClient() as client:
        finn_res, yahoo_res = await asyncio.gather(
            asyncio.gather(*[finnhub_quote(client, s) for s in ["SPY", "QQQ", "DIA"]]),
            asyncio.gather(*[yahoo_quote(client, s) for s in ["^VIX", "USDKRW=X"]])
        )
    result = {}
    for sym, res in zip(["SPY", "QQQ", "DIA"], finn_res):
        result[sym] = res
    for sym, res in zip(["^VIX", "USDKRW=X"], yahoo_res):
        result[sym] = res
    return cached("indices", result)


@app.get("/api/quotes")
async def quotes(symbols: str):
    sym_list = [s.strip() for s in symbols.split(",")]
    async with httpx.AsyncClient() as client:
        tasks = []
        for s in sym_list:
            if ".KS" in s or "^" in s or "=" in s:
                tasks.append(yahoo_quote(client, s))
            else:
                tasks.append(finnhub_quote(client, s))
        results = await asyncio.gather(*tasks)
    return {sym: res for sym, res in zip(sym_list, results) if res}


@app.get("/api/quote/{symbol}")
async def quote(symbol: str):
    data = get_cache(f"q_{symbol}")
    if data:
        return data
    async with httpx.AsyncClient() as client:
        if ".KS" in symbol or "^" in symbol or "=" in symbol:
            res = await yahoo_quote(client, symbol)
        else:
            res = await finnhub_quote(client, symbol)
            if not res:
                res = await yahoo_quote(client, symbol)
    if res:
        cache[f"q_{symbol}"] = (res, datetime.now())
    return res or {"error": "no data"}


@app.get("/api/crypto")
async def crypto():
    data = get_cache("crypto")
    if data:
        return data
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin,ethereum,solana,binancecoin,ripple,dogecoin",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true"
                },
                timeout=5.0
            )
            return cached("crypto", r.json())
    except Exception:
        return {}


@app.get("/api/fg")
async def fear_greed():
    data = get_cache("fg")
    if data:
        return data
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.alternative.me/fng/?limit=1", timeout=5.0)
            result = r.json()["data"][0]
            cache["fg"] = (result, datetime.now())
            return result
    except Exception:
        return {"value": 50, "value_classification": "Neutral"}


@app.get("/health")
async def health():
    return {"status": "ok"}


def find_html():
    patterns = ["*.html", "static/*.html"]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


@app.get("/")
async def root():
    html_file = find_html()
    if html_file and os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>index.html not found</h1>")
