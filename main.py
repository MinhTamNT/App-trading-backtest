import requests
import time
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime, timedelta
from QuantConnect import Resolution, DataNormalizationMode
from QuantConnect.Algorithm import QCAlgorithm
from QuantConnect.Brokerages import BrokerageName
from QuantConnect.Data import Slice
from QuantConnect.Indicators import IndicatorDataPoint
from QuantConnect.Orders.Fees import ConstantFeeModel

class Apptrading(QCAlgorithm):
    ApiKey = "2a23659e-635d-4b93-851a-19ceadb8305f"
    ExchangeApiKey = "32c53e4496-e90a921d28-sjvu3i"

    def initialize(self):
        self.settings.daily_precise_end_time = False
        self.set_start_date(datetime.now() - timedelta(days=365))  # Start date adjusted to 1 year ago
        self.set_end_date(datetime.now())
        self.set_warmup(timedelta(days=1))
        self.set_security_initializer(lambda security: security.SetFeeModel(ConstantFeeModel(0.1)))

        self.symbols = ["ACB"]
        self.ema20_by_symbol = {}
        self.position_by_symbol = {}
        self.historical_data = {}

        for symbol in self.symbols:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.SetDataNormalizationMode(DataNormalizationMode.RAW)
            self.set_benchmark(symbol)
            self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
            self.ema20_by_symbol[symbol] = self.ema(symbol, 20, Resolution.DAILY)
            self.GetStockHistoricalData(symbol)  # Fetch historical data for 1 year

        self.period = timedelta(days=31)
        self.nextEntryTime = self.Time
        self.entryPrice = 0

        self.Debug("Initialization complete.")
        self.CheckSignals()

    def OnWarmupFinished(self):
        self.Debug(f"Finished warming up")
        self.CheckSignals()

    def CheckSignals(self):
        for symbol in self.ema20_by_symbol.keys():
            if symbol not in self.historical_data:
                self.Debug(f"No historical data found for {symbol}.")
                continue

            ema = self.ema20_by_symbol[symbol]
            historical_data = sorted(self.historical_data[symbol], key=lambda x: x.Time)

            if not historical_data:
                self.Debug(f"No historical data available for {symbol}.")
                continue

            previous_difference = None

            for i in range(len(historical_data) - 1):
                current_bar = historical_data[i]
                next_bar = historical_data[i + 1]

                ema.Update(current_bar)

                close = current_bar.Value
                next_close = next_bar.Value

                difference = close - ema.Current.Value
                date_str = current_bar.Time.strftime("%Y-%m-%d %H:%M:%S")

                self.Debug(
                    f"{symbol} - {date_str} - Close: {close}, EMA: {ema.Current.Value}, Difference: {difference}")

                if previous_difference is not None:
                    if previous_difference < 0 and difference > 0:
                        self.HandleBuySignal(symbol, close)
                    elif previous_difference > 0 and difference < 0:
                        self.HandleSellSignal(symbol)

                # Update previous difference
                previous_difference = difference


    def GetStockHistoricalData(self, symbol):
        try:
            url = self.CreateApiUrl(symbol)
            response = self.MakeRequestWithRetries(url)

            if response and response.status_code == 200:
                data = response.json()

                historical_bars = []
                if "data" in data:
                    for data_point in data["data"]:
                        time_str = data_point.get("tradingDate", "")
                        price = data_point.get("close", 0)
                        self.Debug(f"price: {price}")
                        try:
                            date = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                            historical_bars.append(IndicatorDataPoint(date, price))
                        except Exception as ex:
                            self.Debug(f"Error processing data point with time {time_str}: {str(ex)}")

                    self.historical_data[symbol] = historical_bars

                    ema = self.ema20_by_symbol[symbol]
                    for bar in sorted(historical_bars, key=lambda x: x.Time):
                        ema.Update(bar)
            else:
                self.Debug(f"Failed to fetch data for {symbol}. Status: {response.status_code if response else 'No response'}")
        except Exception as ex:
            self.Debug(f"Error fetching historical data for {symbol}: {str(ex)}")

    def CreateApiUrl(self, symbol):
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        start_timestamp = int(time.mktime(datetime.strptime(start_date, "%Y-%m-%d").timetuple()))
        end_timestamp = int(time.mktime(datetime.strptime(end_date, "%Y-%m-%d").timetuple()))

        url = (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?"
               f"ticker={symbol}&type=stock&resolution=D&from={start_timestamp}&to={end_timestamp}")
        return url

    def MakeRequestWithRetries(self, url, retries=3, delay=5):
        for attempt in range(retries):
            try:
                headers = {"X-Fiin-Key": self.ApiKey, "Accept": "application/json"}
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    return response
                else:
                    self.Debug(f"Request failed with status {response.status_code}: {response.text}")
            except Exception as ex:
                self.Debug(f"Attempt {attempt + 1} failed: {str(ex)}")
            time.sleep(delay)
        return None


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
        self.Debug(f"Sell signal for {symbol}: Price {self.entryPrice} below EMA {self.ema20_by_symbol[symbol].Current.Value}")
        self.position_by_symbol[symbol] = False
