"""
从币安公开数据仓库 (data.binance.vision) 下载 K 线数据
并转换为 freqtrade feather 格式
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
    "VELVET/USDT": "VELVETUSDT",
    "MAGMA/USDT": "MAGMAUSDT",
    "BEAT/USDT": "BEATUSDT",
}
TIMEFRAMES = ["1m", "5m", "15m"]
DAYS = 30  # 下载最近30天数据
OUTPUT_DIR = "user_data/data/binance"

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"


def get_months_to_download(days):
    """获取需要下载的月份列表"""
    months = []
    now = datetime.now(timezone.utc)
    for i in range(days // 28 + 2):
        dt = now - timedelta(days=i * 28)
        month_str = dt.strftime("%Y-%m")
        if month_str not in months:
            months.append(month_str)
    return months


def download_monthly_kline(symbol, interval, year_month):
    """下载单个月份的 K 线数据"""
    url = f"{BASE_URL}/{symbol}/{interval}/{symbol}-{interval}-{year_month}.zip"
    print(f"  下载: {url}")
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 404:
            print(f"    404 - 不存在，跳过")
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
                print(f"    获取 {len(df)} 行数据")
                return df
    except Exception as e:
        print(f"    下载失败: {e}")
        return None


def convert_to_freqtrade(df, pair_name):
    """将币安 CSV 转换为 freqtrade feather 格式"""
    # 币安 CSV 时间戳可能是微秒级，需要判断
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
    # 去重
    df_out = df_out.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df_out


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    months = get_months_to_download(DAYS)
    print(f"需要下载月份: {months}")

    for pair_ft, symbol in PAIRS.items():
        pair_name = pair_ft.replace("/", "_")
        for tf in TIMEFRAMES:
            print(f"\n{pair_ft} - {tf}:")
            all_dfs = []
            for ym in months:
                df = download_monthly_kline(symbol, tf, ym)
                if df is not None:
                    all_dfs.append(df)

            if not all_dfs:
                print(f"  无数据可下载")
                continue

            combined = pd.concat(all_dfs, ignore_index=True)
            ft_df = convert_to_freqtrade(combined, pair_ft)

            filename = f"{pair_name}-{tf}.feather"
            filepath = os.path.join(OUTPUT_DIR, filename)
            ft_df.to_feather(filepath)
            print(f"  保存: {filepath} ({len(ft_df)} 根 K 线)")

            # 显示时间范围
            print(f"  时间范围: {ft_df['date'].iloc[0]} -> {ft_df['date'].iloc[-1]}")

    print("\n数据下载完成!")


if __name__ == "__main__":
    main()
