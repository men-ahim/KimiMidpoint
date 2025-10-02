#!/usr/bin/env python3
"""
Midpoint-Reversal + VWAP-bounce + ATR-TP/SL
50 high-vol alts, 5-min, Binance public API
Optimized for Render (keep-alive loop inside)
"""
import os, time, datetime, requests, json, asyncio
import pandas as pd
import numpy as np
from telegram import Bot
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# ----------  Health check server for Render  ----------
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running")
    
    def log_message(self, format, *args):
        pass  # Отключаем логи HTTP запросов

def run_health_server():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheck)
    print(f"Health check server running on port {port}")
    server.serve_forever()

# ----------  user constants  ----------
BOT_TOKEN   = os.getenv("BOT_TOKEN")
CHAT_ID     = int(os.getenv("CHAT_ID"))
INTERVAL    = "5m"
LIMIT       = 200
SYMBOLS     = [
    "DOGEUSDT","SHIBUSDT","APTUSDT","OPUSDT","ARBUSDT","SOLUSDT","POLUSDT","AVAXUSDT","ATOMUSDT","FTMUSDT",
    "NEARUSDT","ALGOUSDT","EGLDUSDT","AXSUSDT","SANDUSDT","MANAUSDT","GALAUSDT","APEUSDT","CHZUSDT","ENJUSDT",
    "LRCUSDT","GMTUSDT","ZILUSDT","BATUSDT","COMPUSDT","1INCHUSDT","CRVUSDT","KNCUSDT","REEFUSDT","RVNUSDT",
    "ICPUSDT","LUNAUSDT","SKLUSDT","MASKUSDT","CVCUSDT","STORJUSDT","BLZUSDT","DATAUSDT","ANKRUSDT",
    "OCEANUSDT","CTSIUSDT","AGLDUSDT","GTCUSDT","PERPUSDT","ALPHAUSDT","BANDUSDT","RAREUSDT","UMAUSDT","REQUSDT"
]
ATR_LEN     = 14
TP_MULT     = 2.0
SL_MULT     = 1.0
# --------------------------------------

bot = Bot(BOT_TOKEN)
session = requests.Session()

def get_klines(symbol):
    url = "https://api.binance.com/api/v3/klines"
    params = dict(symbol=symbol, interval=INTERVAL, limit=LIMIT)
    try:
        r = session.get(url, params=params, timeout=10)
        if r.status_code != 200:   
            return None
        data = r.json()
        df = pd.DataFrame(data, columns=["t","o","h","l","c","v","ct","qv","n","tb","tq","ig"])
        df = df[["o","h","l","c","v"]].astype(float)
        return df
    except Exception as e:
        print(f"Error getting klines for {symbol}: {e}")
        return None

def atr(df, n=ATR_LEN):
    h,l,c = df["h"], df["l"], df["c"]
    tr = np.maximum(h-l, np.maximum(np.abs(h-c.shift()), np.abs(l-c.shift())))
    return tr.rolling(n).mean()

def vwap(df):
    h, l, c, v = df["h"], df["l"], df["c"], df["v"]
    tp = (h + l + c) / 3
    return (tp * v).cumsum() / v.cumsum()

def signal(df):
    if len(df) < ATR_LEN+2:   
        return None
    prev,last = df.iloc[-2], df.iloc[-1]
    mid   = (prev["h"] + prev["l"]) / 2
    vwap_p = vwap(df).iloc[-2]
    touch_vwap = (prev["l"] <= vwap_p <= prev["h"])
    if touch_vwap:
        if prev["c"] < mid and last["c"] > mid:   
            return "BUY"
        if prev["c"] > mid and last["c"] < mid:   
            return "SELL"
    return None

async def send(sym, dir, entry, tp, sl):
    msg = (f"🔔 MIDPOINT-REV 5m\nSymbol: {sym}\nSignal: {dir}\nEntry: {entry:.4f}\n"
           f"TP: {tp:.4f}  (25× ≈ +{TP_MULT*100:.0f}%)\nSL: {sl:.4f}  (25× ≈ -{SL_MULT*100:.0f}%)")
    try:
        await bot.send_message(chat_id=CHAT_ID, text=msg)
        print(datetime.datetime.utcnow(), msg)
    except Exception as e:
        print(f"Error sending message: {e}")

async def main():
    sent = set()
    print(f"Bot started at {datetime.datetime.utcnow()}")
    
    while True:
        for sym in SYMBOLS:
            try:
                df = get_klines(sym)
                if df is None or len(df) < ATR_LEN+2:  
                    continue
                
                dir = signal(df)
                
                if dir:
                    atr_v = atr(df).iloc[-2]
                    entry = df["c"].iloc[-1]
                    
                    if dir == "BUY":
                        tp = entry + TP_MULT * atr_v
                        sl = entry - SL_MULT * atr_v
                    else:
                        tp = entry - TP_MULT * atr_v
                        sl = entry + SL_MULT * atr_v
                    
                    if (sym, dir) not in sent:
                        await send(sym, dir, entry, tp, sl)
                        sent.add((sym, dir))
                else:
                    sent.discard((sym, "BUY"))
                    sent.discard((sym, "SELL"))
                    
            except Exception as e:
                print(f"Error processing {sym}: {e}")
                continue
        
        await asyncio.sleep(5*60)

# ------- entry point for Render -------
if __name__ == "__main__":
    # Запускаем health check сервер в фоне
    Thread(target=run_health_server, daemon=True).start()
    
    # Запускаем основной бот
    asyncio.run(main())
