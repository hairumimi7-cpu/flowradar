# FLOW RADAR Server

## 배포 방법 (Railway)

1. GitHub에 이 폴더 업로드
2. railway.app에서 GitHub 연동
3. 환경변수 설정: FINNHUB_KEY

## 환경변수
- FINNHUB_KEY: Finnhub API 키

## API 엔드포인트
- GET /api/quote/{symbol} - 단일 종목
- GET /api/quotes?symbols=NVDA,AAPL - 다중 종목
- GET /api/crypto - 코인 시세
- GET /api/fg - 공포탐욕지수
- GET /health - 서버 상태
