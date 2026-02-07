import requests
import pandas as pd
import numpy as np
import os

# GitHub Secrets üzerinden gelecek
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# STRATEJİ AYARLARI (Long Odaklı)
LONG_CHANGE_LIMIT = -8   # Son 24 saatte en az %8 düşmüş olmalı
LONG_RSI_LIMIT = 32      # RSI 32'nin altında (Aşırı satım) olmalı
BUY_WALL_RATIO = 2.0     # Alıcılar satıcılardan en az 2 kat güçlü olmalı

def send_telegram(msg):
    if TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

def get_data(endpoint, params={}):
    base = "https://www.okx.com"
    try:
        res = requests.get(base + endpoint, params=params).json()
        return res.get('data', [])
    except: return []

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_long_whale_walls(symbol):
    depth = get_data("/api/v5/market/books", {"instId": symbol, "sz": "20"})
    if not depth: return 1
    asks = sum([float(a[1]) for a in depth[0]['asks']])
    bids = sum([float(b[1]) for b in depth[0]['bids']])
    return (bids / asks if asks > 0 else 1)

def scan_long_only():
    # BTC Genel Durumu
    btc = get_data("/api/v5/market/tickers", {"instId": "BTC-USDT-SWAP"})
    btc_change = (float(btc[0]['last']) / float(btc[0]['open24h']) - 1) * 100 if btc else 0
    btc_emoji = "📉" if btc_change < 0 else "📈"

    tickers = get_data("/api/v5/market/tickers", {"instType": "SWAP"})
    # En hacimli 100 coin
    tickers = sorted(tickers, key=lambda x: float(x['vol24h']), reverse=True)[:100]
    
    signals = []
    
    for t in tickers:
        symbol = t['instId']
        if "-USDT-" not in symbol: continue
        
        change = (float(t['last']) / float(t['open24h']) - 1) * 100
        
        # KRİTER 1: Sert düşüş yapmış mı?
        if change <= LONG_CHANGE_LIMIT:
            candles = get_data("/api/v5/market/candles", {"instId": symbol, "bar": "1H", "limit": "50"})
            if not candles: continue
            
            df = pd.DataFrame(candles, columns=['ts','o','h','l','c','v','vc','vq','conf'])
            df['c'] = df['c'].astype(float)
            
            rsi_series = calculate_rsi(df['c'][::-1])
            rsi = rsi_series.iloc[-1]
            
            # KRİTER 2: RSI dipte mi?
            if rsi <= LONG_RSI_LIMIT:
                # KRİTER 3: Alttan balina desteği var mı?
                wall_ratio = check_long_whale_walls(symbol)
                
                if wall_ratio >= BUY_WALL_RATIO:
                    msg = (f"🚀 *LONG FIRSATI YAKALANDI* 🚀\n\n"
                           f"💎 *Coin:* {symbol}\n"
                           f"📊 *RSI (1H):* {round(rsi, 2)}\n"
                           f"📉 *24s Değişim:* %{round(change, 2)}\n"
                           f"🧱 *Alım Duvarı:* {round(wall_ratio, 1)}x Güçlü\n"
                           f"🌍 *BTC 24s:* %{round(btc_change, 2)} {btc_emoji}\n\n"
                           f"⚠️ _Dip dönüşü onayı beklenmeli!_")
                    signals.append(msg)
                    
    if signals:
        send_telegram("\n---\n".join(signals))

if __name__ == "__main__":
    scan_long_only()
