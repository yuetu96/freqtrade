"""
完全离线回测脚本 - 绕过所有交易所连接
通过 monkey-patch 伪造市场数据
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

# ========== 预定义市场数据 ==========
MOCK_MARKETS = {
    "AGLD/USDT": {
        "id": "AGLDUSDT",
        "symbol": "AGLD/USDT",
        "base": "AGLD",
        "quote": "USDT",
        "baseId": "AGLD",
        "quoteId": "USDT",
        "active": True,
        "type": "spot",
        "spot": True,
        "taker": 0.001,
        "maker": 0.001,
        "precision": {
            "amount": 2,
            "price": 6,
        },
        "limits": {
            "amount": {"min": 0.01, "max": 90000000},
            "price": {"min": 0.000001, "max": 1000},
            "cost": {"min": 1, "max": None},
        },
        "info": {},
    },
}

MOCK_TIMEFRAMES = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
    "1M": "1M",
}


class MockCcxtApi:
    """模拟 ccxt API 对象"""
    def __init__(self):
        self.markets = MOCK_MARKETS
        self.symbols = list(MOCK_MARKETS.keys())
        self.timeframes = MOCK_TIMEFRAMES
        self.precisionMode = 2  # DECIMAL_PLACES
        self.options = {}
        self.id = "binance"
        self.name = "Binance"

    def set_markets_from_exchange(self, other):
        pass

    def calculate_fee(self, symbol="", type="", side="", amount=1, price=1, takerOrMaker="maker"):
        return {"rate": 0.001}

    def has(self, feature):
        has_features = {
            "fetchOHLCV": True,
            "fetchTicker": True,
            "fetchL2OrderBook": True,
            "createMarketOrder": True,
            "createLimitOrder": True,
            "fetchBalance": True,
            "createOrder": True,
            "cancelOrder": True,
            "fetchOrder": True,
            "fetchClosedOrders": True,
            "fetchOpenOrders": True,
            "fetchMyTrades": True,
            "watchOHLCV": False,
        }
        return has_features.get(feature, False)

    def load_markets(self, params=None):
        return self.markets


# ========== Monkey-patch: 伪造交易所市场数据 ==========
from freqtrade.exchange import exchange as exchange_module

def patched_init(self, config, validate=True, exchange_config=None, load_leverage_tiers=False):
    """修补后的 Exchange.__init__ - 跳过网络连接，伪造市场数据"""
    from freqtrade.enums import TradingMode, MarginMode

    self._config = config
    self._api = MockCcxtApi()
    self._api_async = MockCcxtApi()
    self._ws_async = None
    self._exchange_ws = None
    self._last_markets_refresh = 0
    self._markets = MOCK_MARKETS
    self._trading_fees = {}
    self._leverage_tiers = {}
    self._ft_has = {
        "stoploss_on_exchange": False,
        "ohlcv_partial_candle": True,
        "ws_enabled": False,
        "needs_trading_fees": False,
        "order_time_in_force": ["gtc"],
        "tickers_have_price": True,
        "exchangeHasTickerInWS": False,
        "stop_price_type_value_mapping": {},
    }
    self.trading_mode = TradingMode.SPOT
    self.margin_mode = MarginMode.NONE
    self.required_candle_call_count = 1
    self.markets_refresh_interval = 60 * 60 * 1000

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Using Exchange \"{self.name}\" (offline mode)")

    self._klines = {}
    self._trades = {}
    self._dry_run_open_orders = {}
    self._is_demo_trading = False
    self._ohlcv_partial_candle = True
    self._ft_balance_stake = None

    self._entry_rate_cache = {}
    self._exit_rate_cache = {}

    self.loop = None

exchange_module.Exchange.__init__ = patched_init
exchange_module.Exchange.reload_markets = lambda self, force=False, *, load_leverage_tiers=True: None
exchange_module.Exchange.fetch_trading_fees = lambda self: {}
exchange_module.Exchange.validate_stakecurrency = lambda self, stake_currency: None
exchange_module.Exchange.fill_leverage_tiers = lambda self: None
exchange_module.Exchange.ft_additional_exchange_init = lambda self: None
exchange_module.Exchange.close = lambda self: None
exchange_module.Exchange.get_required_startup_candles = lambda self, startup, tf: startup


def patched_get_fee(self, symbol, order_type="", side="", amount=1, price=1, taker_or_maker="maker"):
    return 0.001
exchange_module.Exchange.get_fee = patched_get_fee


def patched_get_precision_amount(self, pair):
    market = self._markets.get(pair, {})
    return market.get("precision", {}).get("amount", 8)
exchange_module.Exchange.get_precision_amount = patched_get_precision_amount


def patched_get_precision_price(self, pair):
    market = self._markets.get(pair, {})
    return market.get("precision", {}).get("price", 8)
exchange_module.Exchange.get_precision_price = patched_get_precision_price


def patched_market_is_future(self, market):
    return False
exchange_module.Exchange.market_is_future = patched_market_is_future


def patched_get_quote_currencies(self):
    return ["USDT", "BTC", "ETH", "BNB"]
exchange_module.Exchange.get_quote_currencies = patched_get_quote_currencies


def patched_exchange_has(self, feature):
    return self._api.has(feature)
exchange_module.Exchange.exchange_has = patched_exchange_has


@property
def patched_precisionMode(self):
    return 2
exchange_module.Exchange.precisionMode = patched_precisionMode


@property
def patched_precision_mode_price(self):
    return 2
exchange_module.Exchange.precision_mode_price = patched_precision_mode_price


@property
def patched_markets(self):
    return self._markets
exchange_module.Exchange.markets = patched_markets


@property
def patched_timeframes(self):
    return MOCK_TIMEFRAMES
exchange_module.Exchange.timeframes = patched_timeframes


# ========== patch Binance 特定方法 ==========
from freqtrade.exchange.binance import Binance
Binance.__init__ = patched_init
Binance.ft_additional_exchange_init = lambda self: None

# ========== patch ExchangeResolver ==========
from freqtrade.resolvers import exchange_resolver

def patched_load_exchange(config, *, exchange_config=None, validate=True, load_leverage_tiers=False):
    return Binance(config, validate=False, exchange_config=exchange_config, load_leverage_tiers=False)

exchange_resolver.ExchangeResolver.load_exchange = staticmethod(patched_load_exchange)

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
    "timeframe": "1m",
    "timerange": "20260501-20260531",
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
