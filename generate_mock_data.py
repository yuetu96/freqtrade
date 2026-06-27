"""
生成模拟 K 线数据用于回测
模拟最近 2 天的 1m/5m/15m 数据
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
import os

# 交易对配置 (模拟山寨币价格区间)
PAIRS = {
    "AGLD/USDT": {"base_price": 0.15, "volatility": 0.003},
    "VELVET/USDT": {"base_price": 0.08, "volatility": 0.004},
    "MAGMA/USDT": {"base_price": 0.25, "volatility": 0.005},
    "BEAT/USDT": {"base_price": 0.05, "volatility": 0.006},
}

TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
}

DAYS = 2
OUTPUT_DIR = "user_data/data/binance"


def generate_ohlcv(base_price, volatility, num_candles, timeframe_seconds, seed=None):
    """生成带趋势的模拟 OHLCV 数据"""
    if seed is not None:
        np.random.seed(seed)

    # 生成基础价格序列 (带趋势和均值回归)
    returns = np.random.normal(0, volatility, num_candles)
    # 添加一些趋势
    trend = np.sin(np.linspace(0, 4 * np.pi, num_candles)) * volatility * 0.5
    returns += trend

    # 生成收盘价
    close_prices = [base_price]
    for r in returns[1:]:
        new_price = close_prices[-1] * (1 + r)
        close_prices.append(max(new_price, base_price * 0.5))  # 防止价格过低

    close = np.array(close_prices)

    # 生成 OHLC
    high = close * (1 + np.abs(np.random.normal(0, volatility * 0.5, num_candles)))
    low = close * (1 - np.abs(np.random.normal(0, volatility * 0.5, num_candles)))
    open_prices = np.roll(close, 1)
    open_prices[0] = base_price

    # 确保 high >= max(open, close) 且 low <= min(open, close)
    high = np.maximum(high, np.maximum(open_prices, close))
    low = np.minimum(low, np.minimum(open_prices, close))

    # 生成成交量 (带波动)
    volume = np.random.lognormal(mean=10, sigma=1, size=num_candles)

    # 生成时间戳
    end_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_time = end_time - timedelta(seconds=num_candles * timeframe_seconds)
    dates = pd.date_range(start=start_time, periods=num_candles,
                          freq=f"{timeframe_seconds}s", tz="UTC")

    df = pd.DataFrame({
        "date": dates,
        "open": open_prices.astype(np.float64),
        "high": high.astype(np.float64),
        "low": low.astype(np.float64),
        "close": close.astype(np.float64),
        "volume": volume.astype(np.float64),
    })

    return df


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for pair, config in PAIRS.items():
        pair_name = pair.replace("/", "_")
        print(f"\n生成 {pair} 模拟数据...")

        for tf_name, tf_seconds in TIMEFRAMES.items():
            num_candles = (DAYS * 24 * 3600) // tf_seconds
            seed = hash(f"{pair_name}_{tf_name}") % (2**31)
            df = generate_ohlcv(
                config["base_price"],
                config["volatility"],
                num_candles,
                tf_seconds,
                seed=seed
            )

            filename = f"{pair_name}-{tf_name}.feather"
            filepath = os.path.join(OUTPUT_DIR, filename)
            df.to_feather(filepath)
            print(f"  {tf_name}: {len(df)} 根 K 线 -> {filepath}")

    print(f"\n数据生成完成! 保存在 {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
