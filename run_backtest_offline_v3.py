"""
完全离线回测脚本
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

# ========== 预定义市场数据 ==========
def _make_market(symbol, base, quote="USDT"):
    return {
        "id": symbol,
        "symbol": f"{base}/{quote}",
        "base": base,
        "quote": quote,
        "baseId": base,
        "quoteId": quote,
        "active": True,
        "type": "spot",
        "spot": True,
        "taker": 0.001,
        "maker": 0.001,
        "precision": {"amount": 2, "price": 6},
        "limits": {
            "amount": {"min": 0.01, "max": 90000000},
            "price": {"min": 0.000001, "max": 1000},
            "cost": {"min": 1, "max": None},
        },
        "info": {},
    }


MOCK_MARKETS = {
    "AGLD/USDT": _make_market("AGLDUSDT", "AGLD"),
    "VELVET/USDT": _make_market("VELVETUSDT", "VELVET"),
    "LAB/USDT": _make_market("LABUSDT", "LAB"),
    "MYX/USDT": _make_market("MYXUSDT", "MYX"),
}

MOCK_TIMEFRAMES = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "2h": "2h", "4h": "4h",
    "6h": "6h", "8h": "8h", "12h": "12h", "1d": "1d",
    "3d": "3d", "1w": "1w", "1M": "1M",
}


class MockCcxtApi:
    def __init__(self):
        self.markets = MOCK_MARKETS
        self.symbols = list(MOCK_MARKETS.keys())
        self.timeframes = MOCK_TIMEFRAMES
        self.precisionMode = 2
        self.options = {}
        self.id = "binance"
        self.name = "Binance"
        self.rateLimit = 200
        self.enableRateLimit = False

    def set_markets_from_exchange(self, other):
        pass

    def calculate_fee(self, symbol="", type="", side="", amount=1, price=1, takerOrMaker="maker"):
        return {"rate": 0.001}

    def has(self, feature):
        features = {
            "fetchOHLCV": True, "fetchTicker": True, "fetchL2OrderBook": True,
            "createMarketOrder": True, "createLimitOrder": True,
            "fetchBalance": True, "createOrder": True,
            "cancelOrder": True, "fetchOrder": True,
            "fetchClosedOrders": True, "fetchOpenOrders": True,
            "fetchMyTrades": True, "watchOHLCV": False,
            "fetchOrderBook": True, "fetchTickers": True,
        }
        return features.get(feature, False)

    def load_markets(self, reload=False, params=None):
        return self.markets

    def describe(self):
        return {"id": "binance", "name": "Binance"}


# ========== Monkey-patch ccxt.binance 初始化 ==========
import ccxt

original_binance_init = ccxt.binance.__init__

def patched_ccxt_binance_init(self, config=None):
    if config is None:
        config = {}
    # 不调用原始 init（避免网络请求）
    # 直接手动设置必要属性
    self.id = "binance"
    self.name = "Binance"
    self.markets = MOCK_MARKETS
    self.symbols = list(MOCK_MARKETS.keys())
    self.timeframes = MOCK_TIMEFRAMES
    self.precisionMode = 2
    self.options = {}
    self.rateLimit = 200
    self.enableRateLimit = config.get("enableRateLimit", False)
    self.apiKey = config.get("apiKey", "")
    self.secret = config.get("secret", "")
    self.password = config.get("password", "")
    self.uid = config.get("uid", "")
    self.headers = {}
    self.session = None
    self.proxy = config.get("proxy", "")
    self.aiohttp_proxy = config.get("aiohttp_proxy", "")
    self.aiohttp_socks = config.get("aiohttp_socks", "")

ccxt.binance.__init__ = patched_ccxt_binance_init

# 也 patch 异步版本
if hasattr(ccxt, 'async_support'):
    async_binance = ccxt.async_support.binance
    original_async_init = async_binance.__init__
    async_binance.__init__ = patched_ccxt_binance_init


# ========== Patch Exchange.reload_markets ==========
from freqtrade.exchange import exchange as exchange_mod

original_reload = exchange_mod.Exchange.reload_markets

def patched_reload_markets(self, force=False, *, load_leverage_tiers=True):
    # 直接使用 ccxt 对象中已有的 markets
    if hasattr(self, '_api') and self._api:
        self._markets = self._api.markets
    if hasattr(self, '_api_async') and self._api_async:
        self._api_async.markets = getattr(self, '_markets', self._api.markets)
    self._last_markets_refresh = exchange_mod.dt_ts()
    return None

exchange_mod.Exchange.reload_markets = patched_reload_markets

# ========== Patch get_fee ==========
original_get_fee = exchange_mod.Exchange.get_fee

def patched_get_fee(self, symbol, order_type="", side="", amount=1, price=1, taker_or_maker="maker"):
    return 0.001

exchange_mod.Exchange.get_fee = patched_get_fee

# ========== Patch additional_exchange_init ==========
original_additional_init = exchange_mod.Exchange.additional_exchange_init

def patched_additional_exchange_init(self):
    return None

exchange_mod.Exchange.additional_exchange_init = patched_additional_exchange_init

# ========== Patch Binance.additional_exchange_init ==========
from freqtrade.exchange.binance import Binance
original_binance_additional = Binance.additional_exchange_init

def patched_binance_additional(self):
    return None

Binance.additional_exchange_init = patched_binance_additional


# ========== Patch 策略验证 - 允许现货模式下 can_short ==========
from freqtrade.resolvers import strategy_resolver
original_validate = strategy_resolver.StrategyResolver._strategy_sanity_validations

@staticmethod
def patched_strategy_sanity_validations(strategy):
    from freqtrade.enums import TradingMode
    trading_mode = strategy.config.get("trading_mode", TradingMode.SPOT)
    if strategy.can_short and trading_mode == TradingMode.SPOT:
        # 现货模式下自动禁用做空，不报错
        strategy.can_short = False
    original_validate(strategy)

strategy_resolver.StrategyResolver._strategy_sanity_validations = patched_strategy_sanity_validations


# ========== 开始回测 ==========
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode

config_path = Path("user_data/config_backtest_offline.json")
with open(config_path) as f:
    config = json.load(f)

args = {
    "config": [str(config_path)],
    "strategy": "MultiTimeframeSuperTrendStrategy",
    "timeframe": "5m",
    "timerange": "20260529-20260627",
    "datadir": "user_data/data/binance",
    "user_data_dir": "user_data",
}

print("初始化配置...")
configuration = Configuration(args, RunMode.BACKTEST)
config = configuration.get_config()

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
