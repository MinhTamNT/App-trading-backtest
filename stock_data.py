import requests
import time
from datetime import datetime, timedelta
from QuantConnect.Indicators import IndicatorDataPoint
from api_requests import MakeRequestWithRetries

class StockDataService:
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.ApiKey = "2a23659e-635d-4b93-851a-19ceadb8305f"
    def GetStockHistoricalData(self, symbol):
        try:
            url = self.CreateApiUrl(symbol)
            response = MakeRequestWithRetries(self.algorithm, url)

            if response and response.status_code == 200:
                data = response.json()
                historical_bars = []

                if "data" in data:
                    for data_point in data["data"]:
                        time_str = data_point.get("tradingDate", "")
                        price = data_point.get("close", 0)
                        try:
                            date = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                            historical_bars.append(IndicatorDataPoint(date, price))
                        except Exception as ex:
                            self.algorithm.Debug(f"Error processing data point with time {time_str}: {str(ex)}")

                    self.algorithm.historical_data[symbol] = historical_bars

                    ema = self.algorithm.ema20_by_symbol[symbol]
                    for bar in sorted(historical_bars, key=lambda x: x.Time):
                        ema.Update(bar)
            else:
                self.algorithm.Debug(f"Failed to fetch data for {symbol}. Status: {response.status_code if response else 'No response'}")
        except Exception as ex:
            self.algorithm.Debug(f"Error fetching historical data for {symbol}: {str(ex)}")

    def CreateApiUrl(self, symbol):
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        start_timestamp = int(time.mktime(datetime.strptime(start_date, "%Y-%m-%d").timetuple()))
        end_timestamp = int(time.mktime(datetime.strptime(end_date, "%Y-%m-%d").timetuple()))

        url = (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?"
               f"ticker={symbol}&type=stock&resolution=D&from={start_timestamp}&to={end_timestamp}")
        return url
