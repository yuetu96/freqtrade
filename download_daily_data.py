"""
从币安公开数据仓库下载日度 K 线数据
获取最新数据（6月份）
"""
import os
import io
import zipfile
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# 配置
PAIRS = {
    "AGLD/USDT": "AGLDUSDT",
}
TIMEFRAMES = ["1m", "5m", "15m"]
DAYS = 27  # 下载最近27天（6月1日到6月26日）
OUTPUT_DIR = "user_data/data/binance"

BASE_URL = "https://data.binance.vision/data/spot/daily/klines"


def download_daily_kline(symbol, interval, date_str):
    """下载单日 K 线数据"""
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
        print(f"    下载失败 {date_str}: {e}")
        return None


def convert_to_freqtrade(df):
    """将币安 CSV 转换为 freqtrade feather 格式"""
    ts = df["open_time"].iloc[0]
    if ts > 1e15:
        unit = "us"
    elif ts > 1e12:
        unit = "ms"
    else:
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

    today = datetime.now(timezone.utc).date()
    dates = [(today - timedelta(days=i)) for i in range(1, DAYS + 1)]
    dates.reverse()  # 从最早到最新
    print(f"下载日期范围: {dates[0]} -> {dates[-1]}")

    for pair_ft, symbol in PAIRS.items():
        pair_name = pair_ft.replace("/", "_")
        for tf in TIMEFRAMES:
            print(f"\n{pair_ft} - {tf}:")
            all_dfs = []

            for date in dates:
                date_str = date.strftime("%Y-%m-%d")
                df = download_daily_kline(symbol, tf, date_str)
                if df is not None:
                    all_dfs.append(df)
                    print(f"  {date_str}: {len(df)} 行")
                else:
                    print(f"  {date_str}: 无数据")

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
