"""
从币安公开数据仓库 (data.binance.vision) 下载 U 本位永续合约日度 K 线数据
并转换为 freqtrade feather 格式

合约 K 线路径: data/futures/um/daily/klines/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-{YYYY-MM-DD}.zip
"""
import os
import io
import zipfile
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# 配置 - 三个山寨币合约
PAIRS = {
    "VELVET/USDT": "VELVETUSDT",
    "LAB/USDT": "LABUSDT",
    "MYX/USDT": "MYXUSDT",
}
TIMEFRAMES = ["5m", "15m"]
DAYS = 30  # 下载最近30天数据
OUTPUT_DIR = "user_data/data/binance"

BASE_URL = "https://data.binance.vision/data/futures/um/daily/klines"


def get_dates_to_download(days):
    """获取需要下载的日期列表 (YYYY-MM-DD)"""
    dates = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y-%m-%d"))
    return dates


def download_daily_kline(symbol, interval, date_str):
    """下载单个日期的 K 线数据"""
    url = f"{BASE_URL}/{symbol}/{interval}/{symbol}-{interval}-{date_str}.zip"
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                df = pd.read_csv(f, header=None)
                df.columns = [
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "trades",
                    "taker_buy_base", "taker_buy_quote", "ignore",
                ]
                return df
    except Exception as e:
        return None


def convert_to_freqtrade(df):
    """将币安 CSV 转换为 freqtrade feather 格式"""
    # 强制转 numeric，避免字符串混入
    df = df.copy()
    for col in ["open_time", "open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open_time"])

    ts = df["open_time"].iloc[0]
    if ts > 1e15:  # 微秒
        unit = "us"
    elif ts > 1e12:  # 毫秒
        unit = "ms"
    else:  # 秒
        unit = "s"

    df_out = pd.DataFrame({
        "date": pd.to_datetime(df["open_time"], unit=unit, utc=True),
        "open": df["open"].astype(np.float64),
        "high": df["high"].astype(np.float64),
        "low": df["low"].astype(np.float64),
        "close": df["close"].astype(np.float64),
        "volume": df["volume"].astype(np.float64),
    })
    df_out = df_out.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df_out


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    dates = get_dates_to_download(DAYS)
    print(f"将下载最近 {DAYS} 天数据 ({dates[-1]} ~ {dates[0]})")

    for pair_ft, symbol in PAIRS.items():
        pair_name = pair_ft.replace("/", "_")
        for tf in TIMEFRAMES:
            print(f"\n{pair_ft} - {tf}:")
            all_dfs = []
            ok_count = 0
            for d in dates:
                df = download_daily_kline(symbol, tf, d)
                if df is not None and len(df) > 0:
                    all_dfs.append(df)
                    ok_count += 1
            print(f"  成功获取 {ok_count}/{len(dates)} 天数据")

            if not all_dfs:
                print(f"  无数据可下载")
                continue

            combined = pd.concat(all_dfs, ignore_index=True)
            ft_df = convert_to_freqtrade(combined)

            filename = f"{pair_name}-{tf}.feather"
            filepath = os.path.join(OUTPUT_DIR, filename)
            ft_df.to_feather(filepath)
            print(f"  保存: {filepath} ({len(ft_df)} 根 K 线)")
            print(f"  时间范围: {ft_df['date'].iloc[0]} -> {ft_df['date'].iloc[-1]}")

    print("\n数据下载完成!")


if __name__ == "__main__":
    main()
