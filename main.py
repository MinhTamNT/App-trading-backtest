from datetime import datetime, timedelta

from QuantConnect import Resolution, DataNormalizationMode
from QuantConnect.Algorithm import QCAlgorithm
from QuantConnect.Brokerages import BrokerageName
from QuantConnect.Orders.Fees import ConstantFeeModel

import sys
import os
from dotenv import load_dotenv
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from stock_data import StockDataService
from signal_handler import SignalHandler

class Apptrading(QCAlgorithm):
    def initialize(self):
        load_dotenv()
        self.ApiKey = os.getenv("API_KEY")
        if not self.ApiKey:
            self.Debug("Error Get ApiKey")
        self.settings.daily_precise_end_time = False
        self.set_start_date(datetime.now() - timedelta(days=365))
        self.set_end_date(datetime.now())
        self.set_warmup(timedelta(days=1))
        self.set_security_initializer(lambda security: security.SetFeeModel(ConstantFeeModel(0.1)))

        self.symbols = ["ACB"]
        self.ema20_by_symbol = {}
        self.position_by_symbol = {}
        self.historical_data = {}

        self.signal_handler = SignalHandler(self)  # Signal handler
        self.stock_data_service = StockDataService(self)  # Historical data service

        for symbol in self.symbols:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.SetDataNormalizationMode(DataNormalizationMode.RAW)
            self.set_benchmark(symbol)
            self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
            self.ema20_by_symbol[symbol] = self.ema(symbol, 20, Resolution.DAILY)
            self.stock_data_service.GetStockHistoricalData(symbol)  # Fetch historical data

        self.period = timedelta(days=31)
        self.nextEntryTime = self.Time
        self.entryPrice = 0

        self.Debug("Initialization complete.")
        self.signal_handler.CheckSignals()

    def OnWarmupFinished(self):
        self.Debug(f"Finished warming up")
        self.signal_handler.CheckSignals()

    def HandleBuySignal(self, symbol, price):
        quantity = int(self.Portfolio.Cash / price)
        if quantity > 0:
            self.MarketOrder(symbol, quantity)
            self.entryPrice = price
            self.nextEntryTime = self.Time + self.period
            self.Debug(f"Market order placed for {symbol} at {price}")
            self.position_by_symbol[symbol] = True
            self.Debug(f"Buy signal for {symbol}: Price above EMA {self.ema20_by_symbol[symbol].Current.Value}")

    def HandleSellSignal(self, symbol):
        self.Debug(
            f"Sell signal for {symbol}: Price {self.entryPrice} below EMA {self.ema20_by_symbol[symbol].Current.Value}")
        self.position_by_symbol[symbol] = False
