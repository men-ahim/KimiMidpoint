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
    r = session.get(url, params=params, timeout=10)
    if r.status_code != 200:   return None
    df = pd.DataFrame(r.json(), columns="t o h l c v ct qv n tb tq ig".split())
    df = df[["o","h","l","c"]].astype(float)
    return df

def atr(df, n=ATR_LEN):
    h,l,c = df["h"], df["l"], df["c"]
    tr = np.maximum(h-l, np.maximum(np.abs(h-c.shift()), np.abs(l-c.shift())))
    return tr.rolling(n).mean()

def vwap(df):
    h, l, c = df["h"], df["l"], df["c"]
    tp = (h + l + c) / 3
    v = df["v"] if "v" in df.columns else 1
    if isinstance(v, int):
        return tp.expanding().mean()
    return (tp * v).cumsum() / v.cumsum()

def signal(df):
    if len(df) < ATR_LEN+2:   return None
    prev,last = df.iloc[-2], df.iloc[-1]
    mid   = (prev["h"] + prev["l"]) / 2
    atr_v = atr(df).iloc[-2]
    vwap_p = vwap(df).iloc[-2]
    touch_vwap = (prev["l"] <= vwap_p <= prev["h"])
    if touch_vwap:
        if prev["c"] < mid and last["c"] > mid:   return "BUY"
        if prev["c"] > mid and last["c"] < mid:   return "SELL"
    return None

async def send(sym, dir, entry, tp, sl):
    msg = (f"🔔 MIDPOINT-REV 5m\nSymbol: {sym}\nSignal: {dir}\nEntry: {entry:.4f}\n"
           f"TP: {tp:.4f}  (25× ≈ +{TP_MULT*100:.0f}%)\nSL: {sl:.4f}  (25× ≈ -{SL_MULT*100:.0f}%)")
    await bot.send_message(chat_id=CHAT_ID, text=msg)
    print(datetime.datetime.utcnow(), msg)

async def main():
    sent = set()
    while True:
        for sym in SYMBOLS:
            df = get_klines(sym)
            if df is None or len(df) < ATR_LEN+2:  continue
            dir = signal(df)
            atr_v = atr(df).iloc[-2]
            entry = df["c"].iloc[-1]
            tp = entry + (dir=="BUY" and 1 or -1) * TP_MULT * atr_v
            sl = entry - (dir=="BUY" and 1 or -1) * SL_MULT * atr_v
            if dir and (sym, dir) not in sent:
                await send(sym, dir, entry, tp, sl)
                sent.add((sym, dir))
            elif not dir and (sym, "BUY") in sent: sent.discard((sym, "BUY"))
            elif not dir and (sym, "SELL") in sent: sent.discard((sym, "SELL"))
        await asyncio.sleep(5*60)   # async-совместимый sleep

# ------- entry point for Render -------
if __name__ == "__main__":
    asyncio.run(main())
