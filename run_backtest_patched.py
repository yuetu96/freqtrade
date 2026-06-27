"""
离线回测脚本 - 完全绕过交易所连接
通过 monkey-patch 跳过市场数据加载
"""
import sys
from pathlib import Path
import json

# 添加工作目录
sys.path.insert(0, str(Path(__file__).parent))

# Monkey-patch: 在导入 freqtrade 模块之前禁用市场加载
from freqtrade.exchange import exchange
original_reload_markets = exchange.Exchange.reload_markets

def fake_reload_markets(self, *args, **kwargs):
    """伪造的市场数据加载 - 直接返回"""
    print("跳过市场数据加载 (离线模式)")
    return None

exchange.Exchange.reload_markets = fake_reload_markets

# 继续导入其他模块
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode

# 加载配置
config_path = Path("user_data/config_backtest_offline.json")
with open(config_path) as f:
    config = json.load(f)

# 设置必要的配置项
config["user_data_dir"] = "user_data"
config["datadir"] = "user_data/data/binance"
config["timeframe"] = "1m"
config["timerange"] = "20260501-20260531"  # 2026年5月整月数据

# 创建配置对象
args = {
    "config": [str(config_path)],
    "strategy": "MultiTimeframeSuperTrendStrategy",
    "timeframe": "1m",
    "timerange": "20260501-20260531",
    "datadir": "user_data/data/binance",
    "user_data_dir": "user_data",
}

# 初始化配置
configuration = Configuration(args, RunMode.BACKTEST)
config = configuration.get_config()

# 尝试初始化回测
try:
    print("初始化回测...")
    backtesting = Backtesting(config)
    print("开始回测...")
    backtesting.start()
    print("回测完成!")
except Exception as e:
    print(f"回测失败: {e}")
    import traceback
    traceback.print_exc()
