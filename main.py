   if cached_data: return cached_data
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin,ethereum,solana,binancecoin,ripple,dogecoin", "vs_currencies": "usd", "include_24hr_change": "true"},
                timeout=5.0
            )
            return cached("crypto", r.json())
    except: return {}

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
    except: return {"value": 50, "value_classification": "Neutral"}

@app.get("/health")
async def health():
    return {"status": "ok"}

def find_html():
    """가장 최신 HTML 파일 찾기"""
    patterns = ["*.html", "static/*.html"]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))
    if not files:
        return None
    # 수정 시간 기준으로 가장 최신 파일
    latest = max(files, key=os.path.getmtime)
    print(f"서빙할 파일: {latest}")
    return latest

@app.get("/")
async def root():
    html_file = find_html()
    if html_file and os.path.exists(html_file):
        with open(html_file, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>파일을 찾을 수 없습니다</h1>")

