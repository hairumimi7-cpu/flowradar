from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
import asyncio
from datetime import datetime
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FINNHUB_KEY = os.getenv("FINNHUB_KEY", "d8gqq09r01qhjpmp8fe0d8gqq09r01qhjpmp8feg")

# 서버 캐시 (1분)
cache = {}
CACHE_TTL = 60

def cached(key, data):
    cache[key] = (data, datetime.now())
    return data

def get_cache(key):
    if key in cache:
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
    except:
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
            return {"price": curr, "change": ((curr-prev)/prev)*100, "prev": prev}
    except:
        pass
    return None

# ══ 핵심: 섹터 전체 한번에 ══
US_SECTORS = ["XLK","XLC","XLY","XLF","XLV","XLI","XLE","XLP","XLU","XLB","XLRE"]
KR_SECTORS = ["005930.KS","373220.KS","207940.KS","005380.KS","035420.KS","105560.KS","005490.KS","051910.KS","041510.KS","012450.KS","000720.KS"]
INDICES = ["SPY","QQQ","DIA","^VIX","USDKRW=X"]

@app.get("/api/sectors/us")
async def us_sectors():
    cached_data = get_cache("us_sectors")
    if cached_data: return cached_data
    
    async with httpx.AsyncClient() as client:
        # Finnhub로 US ETF 병렬 요청
        tasks = [finnhub_quote(client, s) for s in US_SECTORS]
        results = await asyncio.gather(*tasks)
    
    data = {sym: res for sym, res in zip(US_SECTORS, results)}
    return cached("us_sectors", data)

@app.get("/api/sectors/kr")
async def kr_sectors():
    cached_data = get_cache("kr_sectors")
    if cached_data: return cached_data
    
    async with httpx.AsyncClient() as client:
        tasks = [yahoo_quote(client, s) for s in KR_SECTORS]
        results = await asyncio.gather(*tasks)
    
    data = {sym: res for sym, res in zip(KR_SECTORS, results)}
    return cached("kr_sectors", data)

@app.get("/api/indices")
async def indices():
    cached_data = get_cache("indices")
    if cached_data: return cached_data
    
    async with httpx.AsyncClient() as client:
        finn_task = [finnhub_quote(client, s) for s in ["SPY","QQQ","DIA"]]
        yahoo_task = [yahoo_quote(client, s) for s in ["^VIX","USDKRW=X"]]
        finn_res, yahoo_res = await asyncio.gather(
            asyncio.gather(*finn_task),
            asyncio.gather(*yahoo_task)
        )
    
    data = {}
    for sym, res in zip(["SPY","QQQ","DIA"], finn_res):
        data[sym] = res
    for sym, res in zip(["^VIX","USDKRW=X"], yahoo_res):
        data[sym] = res
    return cached("indices", data)

@app.get("/api/quotes")
async def quotes(symbols: str):
    sym_list = [s.strip() for s in symbols.split(",")]
    cached_data = get_cache("quotes_" + symbols[:50])
    if cached_data: return cached_data
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for s in sym_list:
            if ".KS" in s or "^" in s or "=" in s:
                tasks.append(yahoo_quote(client, s))
            else:
                tasks.append(finnhub_quote(client, s))
        results = await asyncio.gather(*tasks)
    
    data = {sym: res for sym, res in zip(sym_list, results) if res}
    return cached("quotes_" + symbols[:50], data)

@app.get("/api/quote/{symbol}")
async def quote(symbol: str):
    cached_data = get_cache(f"q_{symbol}")
    if cached_data: return cached_data
    
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
    cached_data = get_cache("crypto")
    if cached_data: return cached_data
    
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
            data = r.json()
            return cached("crypto", data)
    except:
        return {}

@app.get("/api/fg")
async def fear_greed():
    cached_data = get_cache("fg")
    if cached_data: return cached_data
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.alternative.me/fng/?limit=1", timeout=5.0)
            data = r.json()["data"][0]
            cache["fg"] = (data, datetime.now())
            return data
    except:
        return {"value": 50, "value_classification": "Neutral"}

@app.get("/health")
async def health():
    return {"status": "ok", "cached_keys": len(cache)}

if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
