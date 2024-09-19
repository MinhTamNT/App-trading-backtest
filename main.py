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

        self.symbols = ["FPT"]
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

        self.period = timedelta(31)
        self.nextEntryTime = self.Time
        self.entryPrice = 0

        self.Debug("Initialization complete.")
        self.CheckSignals()

    def onData(self, data: Slice):
        self.Debug(f"Data of the on data {data}")
        pass

    def OnWarmupFinished(self):
        self.Debug(f"Finished warming up")
        self.CheckSignals()

    def CheckSignals(self):
        for symbol in self.ema20_by_symbol.keys():
            if symbol in self.historical_data:
                ema = self.ema20_by_symbol[symbol]
                historical_data = self.historical_data[symbol]

                if historical_data:
                    # Ensure historical_data is sorted by time
                    historical_data = sorted(historical_data, key=lambda x: x.Time)

                    previous_difference = None  # Variable to store previous candle's difference

                    for i in range(len(historical_data) - 1):
                        current_bar = historical_data[i]
                        next_bar = historical_data[i + 1]

                        ema.Update(current_bar)  # Update EMA with current candle

                        close = current_bar.Value
                        next_close = next_bar.Value

                        # Calculate difference between close price and EMA
                        difference = close - ema.Current.Value

                        date_str = current_bar.Time.strftime("%Y-%m-%d %H:%M:%S")

                        # Display the difference
                        self.Debug(
                            f"{symbol} - {date_str} - Close: {close}, EMA: {ema.Current.Value}, Difference: {difference}")

                        # Check buy/sell signal based on the previous difference
                        if previous_difference is not None:
                            if previous_difference < 0 and difference > 0:
                                if symbol not in self.position_by_symbol or not self.position_by_symbol[symbol]:
                                    if not self.Portfolio.Invested and self.nextEntryTime <= self.Time:
                                        price = next_close
                                        if price > 0:
                                            quantity = int(self.Portfolio.Cash / price)
                                            self.MarketOrder(symbol, quantity)
                                            self.entryPrice = price
                                            self.nextEntryTime = self.Time + self.period
                                            self.Debug(f"Market order placed for {symbol} at {price}")

                                        self.Debug(f"Buy signal for {symbol}: Price above EMA {ema.Current.Value}")
                                        self.position_by_symbol[symbol] = True  # Update position status

                            elif previous_difference > 0 and difference < 0:
                                # Sell signal
                                if symbol in self.position_by_symbol and self.position_by_symbol[symbol]:
                                    self.Debug(f"Sell signal for {symbol}: Price below EMA {ema.Current.Value}")
                                    self.position_by_symbol[symbol] = False  # Update position status

                        # Update previous difference
                        previous_difference = difference
                else:
                    self.Debug(f"No historical data found for {symbol}.")

                # Plot historical data
                self.PlotHistoricalData(symbol)

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
                        try:
                            # Adjusted format to handle ISO 8601 date format
                            date = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                            historical_bars.append(IndicatorDataPoint(date, float(price)))
                        except Exception as ex:
                            self.Debug(f"Error processing data point with time {time_str}: {str(ex)}")

                    self.historical_data[symbol] = historical_bars

                    ema = self.ema20_by_symbol[symbol]
                    for bar in sorted(historical_bars, key=lambda x: x.Time):
                        ema.Update(bar)
            else:
                self.Debug(
                    f"Failed to fetch data for {symbol}. Status: {response.status_code if response else 'No response'}")
        except Exception as ex:
            self.Debug(f"Error fetching historical data for {symbol}: {str(ex)}")

    def CreateApiUrl(self, symbol):
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")  # Start date adjusted to 1 year ago

        start_timestamp = int(time.mktime(datetime.strptime(start_date, "%Y-%m-%d").timetuple()))
        end_timestamp = int(time.mktime(datetime.strptime(end_date, "%Y-%m-%d").timetuple()))

        url = (
            f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?ticker={symbol}&type=stock&resolution=D&from={start_timestamp}&to={end_timestamp}")
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

    def PlotHistoricalData(self, symbol):
        if symbol in self.historical_data:
            historical_data = self.historical_data[symbol]
            if historical_data:
                dates = [data.Time for data in historical_data]
                prices = [data.Value for data in historical_data]

                # Plot the historical data
                plt.figure(figsize=(10, 6))
                plt.plot(dates, prices, label='Price', color='blue')
                plt.xlabel('Date')
                plt.ylabel('Price')
                plt.title(f'Historical Data for {symbol}')
                plt.legend()
                plt.grid(True)
                plt.xticks(rotation=45)
                plt.tight_layout()

                # Save the plot to a file
                plt.savefig(f"{symbol}_historical_data.png")
                plt.close()

                # Save data to Excel
                df = pd.DataFrame({
                    'Date': dates,
                    'Price': prices
                })
                df.to_excel(f"{symbol}_historical_data.xlsx", index=False)
                self.Debug(f"Saved historical data for {symbol} to Excel.")
            else:
                self.Debug(f"No historical data available for {symbol}.")
        else:
            self.Debug(f"No historical data found for {symbol}.")
