from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import asyncio
from datetime import datetime, timedelta
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FINNHUB_KEY = os.getenv("FINNHUB_KEY", "d8gqq09r01qhjpmp8fe0d8gqq09r01qhjpmp8feg")

# 캐시 (서버 메모리)
cache = {}
CACHE_TTL = 60  # 1분 캐시

async def get_quote(symbol: str) -> dict:
    """Finnhub에서 주가 가져오기"""
    cache_key = f"quote_{symbol}"
    now = datetime.now()
    
    # 캐시 확인
    if cache_key in cache:
        data, ts = cache[cache_key]
        if (now - ts).seconds < CACHE_TTL:
            return data
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"https://finnhub.io/api/v1/quote",
                params={"symbol": symbol, "token": FINNHUB_KEY}
            )
            data = r.json()
            if data.get("c", 0) > 0:
                result = {
                    "price": data["c"],
                    "change": data["dp"],
                    "prev": data["pc"],
                    "high": data["h"],
                    "low": data["l"],
                }
                cache[cache_key] = (result, now)
                return result
    except Exception as e:
        print(f"Finnhub error {symbol}: {e}")
    
    return None

async def get_yahoo(symbol: str) -> dict:
    """Yahoo Finance 백업"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            res = data["chart"]["result"][0]
            closes = [c for c in res["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 2:
                prev, curr = closes[-2], closes[-1]
                return {
                    "price": curr,
                    "change": ((curr - prev) / prev) * 100,
                    "prev": prev,
                }
    except:
        pass
    return None

@app.get("/api/quote/{symbol}")
async def quote(symbol: str):
    """단일 종목 시세"""
    # 한국주식은 Yahoo로
    if ".KS" in symbol or "^" in symbol or "=" in symbol:
        data = await get_yahoo(symbol)
    else:
        data = await get_quote(symbol)
        if not data:
            data = await get_yahoo(symbol)
    
    return data or {"error": "no data"}

@app.get("/api/quotes")
async def quotes(symbols: str):
    """여러 종목 한번에 (쉼표 구분)"""
    sym_list = symbols.split(",")
    
    # 병렬로 모두 요청
    tasks = [quote(s.strip()) for s in sym_list]
    results = await asyncio.gather(*tasks)
    
    return {
        sym.strip(): result 
        for sym, result in zip(sym_list, results)
        if result and "error" not in result
    }

@app.get("/api/forex")
async def forex():
    """환율"""
    data = await get_yahoo("USDKRW=X")
    return data or {"error": "no data"}

@app.get("/api/crypto")
async def crypto():
    """코인 시세"""
    coins = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple", "dogecoin"]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": ",".join(coins),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true"
                }
            )
            return r.json()
    except:
        return {}

@app.get("/api/fg")
async def fear_greed():
    """공포탐욕지수"""
    cache_key = "fg"
    now = datetime.now()
    if cache_key in cache:
        data, ts = cache[cache_key]
        if (now - ts).seconds < 3600:  # 1시간 캐시
            return data
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("https://api.alternative.me/fng/?limit=1")
            data = r.json()["data"][0]
            cache[cache_key] = (data, now)
            return data
    except:
        return {"value": 50, "value_classification": "Neutral"}

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# 정적 파일 (HTML 대시보드)
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

