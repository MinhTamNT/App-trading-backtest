import requests
import time
from datetime import datetime, timedelta
from QuantConnect import Resolution, DataNormalizationMode
from QuantConnect.Algorithm import QCAlgorithm
from QuantConnect.Brokerages import BrokerageModel, BrokerageName
from QuantConnect.Data import Slice
from QuantConnect.Indicators import ExponentialMovingAverage, IndicatorDataPoint
from QuantConnect.Orders.Fees import ConstantFeeModel
import pandas as pd

class Apptrading(QCAlgorithm):
    ApiKey = "2a23659e-635d-4b93-851a-19ceadb8305f"
    ExchangeApiKey = "32c53e4496-e90a921d28-sjvu3i"

    def initialize(self):
        self.settings.daily_precise_end_time = False
        self.set_start_date(datetime.now() - timedelta(days=60))
        self.set_end_date(datetime.now())
        self.set_warmup(timedelta(days=2))
        self.set_security_initializer(lambda security: security.SetFeeModel(ConstantFeeModel(0.1)))

        self.symbols = ["ACB"]
        self.ema20_by_symbol = {}
        self.position_by_symbol = {}
        self.historical_data = {}

        for symbol in self.symbols:
            equity = self.add_equity(symbol, Resolution.MINUTE)
            equity.SetDataNormalizationMode(DataNormalizationMode.RAW)
            self.set_benchmark(symbol)
            self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
            self.ema20_by_symbol[symbol] = self.ema(symbol, 5, 0.5)
            self.GetStockHistoricalData(symbol, 50)

        self.period = timedelta(31)
        self.nextEntryTime = self.Time
        self.entryPrice = 0
        # self.Schedule.On(self.DateRules.EveryDay(),
        #                  self.TimeRules.Every(timedelta(minutes=5)),
        #                  self.CheckSignals)
        self.Debug("Initialization complete.")
        self.CheckSignals()

    def CheckSignals(self):
        signals_changed = False

        for symbol in self.ema20_by_symbol.keys():
            if symbol in self.historical_data:
                ema = self.ema20_by_symbol[symbol]
                historical_data = self.historical_data[symbol]

                if historical_data:
                    # Cập nhật EMA với dữ liệu mới nhất
                    for bar in sorted(historical_data, key=lambda x: x.Time):
                        if ema.IsReady:
                            ema.Update(bar)

                    # Lấy dữ liệu mới nhất để kiểm tra tín hiệu
                    latest_bar = historical_data[-1]
                    close = latest_bar.Value

                    # Kiểm tra tín hiệu mua/bán
                    if ema.IsReady:
                        if close > ema.Current.Value:
                            if symbol not in self.position_by_symbol or not self.position_by_symbol[symbol]:
                                # Thực hiện lệnh mua nếu chưa đầu tư và đã đến thời điểm để mua
                                if not self.Portfolio.Invested and self.nextEntryTime <= self.Time:
                                    price = close
                                    if price > 0:
                                        quantity = int(self.Portfolio.Cash / price)
                                        self.MarketOrder(symbol, quantity)
                                        self.entryPrice = price
                                        self.nextEntryTime = self.Time + self.period
                                        self.Debug(f"Market order placed for {symbol} at {price}")

                                    self.SetHoldings(symbol, 0.1)
                                    self.Debug(f"Buy signal for {symbol}: Price above EMA {ema.Current.Value}")
                                    signals_changed = True
                                    self.position_by_symbol[symbol] = True
                        elif close < ema.Current.Value:
                            if symbol in self.position_by_symbol and self.position_by_symbol[symbol]:
                                self.Liquidate(symbol)
                                self.Debug(f"Sell signal for {symbol}: Price below EMA {ema.Current.Value}")
                                signals_changed = True
                                self.position_by_symbol[symbol] = False
                else:
                    self.Debug(f"No historical data found for {symbol}.")
            else:
                self.Debug(f"No price data for {symbol} at {self.Time}. Check registration or data source.")

        if not signals_changed:
            self.Debug(f"No signal changes detected at {self.Time}")

    def GetStockHistoricalData(self, symbol, count):
        try:
            url = self.CreateApiUrl(symbol, count)
            response = self.MakeRequestWithRetries(url)

            if response and response.status_code == 200:
                data = response.json()
                historical_bars = []
                if "data" in data:
                    for data_point in data["data"]:
                        time_str = data_point.get("t", "")
                        price = data_point.get("p", 0)
                        try:
                            date = datetime.strptime(time_str, "%H:%M:%S").replace(year=datetime.now().year,
                                                                                   month=datetime.now().month,
                                                                                   day=datetime.now().day)
                            historical_bars.append(IndicatorDataPoint(date, float(price)))
                        except Exception as ex:
                            self.Debug(f"Error processing data point with time {time_str}: {str(ex)}")

                    self.historical_data[symbol] = historical_bars

                    ema = self.ema20_by_symbol[symbol]
                    for bar in sorted(historical_bars, key=lambda x: x.Time):
                        ema.Update(bar)
                else:
                    self.Debug(f"No historical data found for {symbol}.")
            else:
                self.Debug(
                    f"Failed to fetch data for {symbol}. Status: {response.status_code if response else 'No response'}")
        except Exception as ex:
            self.Debug(f"Error fetching historical data for {symbol}: {str(ex)}")

    def CreateApiUrl(self, symbol, count):
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

        start_timestamp = int(time.mktime(datetime.strptime(start_date, "%Y-%m-%d").timetuple()))
        end_timestamp = int(time.mktime(datetime.strptime(end_date, "%Y-%m-%d").timetuple()))

        url = (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/intraday/{symbol}/his/paging?"
                       f"ticker={symbol}&resolution=1&from={start_timestamp}&to={end_timestamp}")
        return url

    def MakeRequestWithRetries(self, url, retries=3, delay=5):
        for attempt in range(retries):
            try:
                headers = {"X-Fiin-Key": self.ApiKey, "Accept": "application/json"}
                response = requests.get(url, headers=headers , timeout=10)
                if response.status_code == 200:
                    return response
                else:
                    self.Debug(f"Request failed with status {response.status_code}: {response.text}")
            except Exception as ex:
                self.Debug(f"Attempt {attempt + 1} failed: {str(ex)}")
            time.sleep(delay)
        return None
