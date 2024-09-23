import requests
import time
from datetime import datetime
import pandas as pd
from QuantConnect.Indicators import IndicatorDataPoint

class StockDataService:
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.ApiKey = "2a23659e-635d-4b93-851a-19ceadb8305f"

    def get_stock_price_tcbs(self, symbol, from_date_str, to_date_str):
        try:
            from_date = datetime.strptime(from_date_str, "%d-%m-%Y")
            to_date = datetime.strptime(to_date_str, "%d-%m-%Y")

            url = self.create_api_url(symbol, from_date, to_date)
            response = self.make_request_with_retries(url)

            if response is None:
                return None  # Không có phản hồi từ API

            data = response.json()
            historical_prices = []

            if "data" in data:
                for data_point in data["data"]:
                    time_str = data_point.get("tradingDate", "")
                    price = data_point.get("close", 0)
                    volume = data_point.get("volume", 0)
                    try:
                        date = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
                        if from_date <= date <= to_date:
                            historical_prices.append({
                                'date': date,
                                'price': price,
                                'volume': volume
                            })
                    except Exception as ex:
                        self.algorithm.Debug(f"Error processing data point with time {time_str}: {str(ex)}")

            if historical_prices:
                df = pd.DataFrame(historical_prices)
                self.algorithm.Debug(f"{symbol}: {df}")
                return df
            else:
                self.algorithm.Debug(f"No historical data found for {symbol} in the specified date range.")
                return None

        except Exception as ex:
            self.algorithm.Debug(f"Error fetching historical data for {symbol}: {str(ex)}")
            return None

    def create_api_url(self, symbol, from_date, to_date):
        start_timestamp = int(time.mktime(from_date.timetuple()))
        end_timestamp = int(time.mktime(to_date.timetuple()))

        url = (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term?"
               f"ticker={symbol}&type=stock&resolution=D&from={start_timestamp}&to={end_timestamp}")
        self.algorithm.Debug(f"url: {url}")
        return url

    def make_request_with_retries(self, url, retries=3, delay=5):
        for attempt in range(retries):
            try:
                headers = {"X-Fiin-Key": self.ApiKey, "Accept": "application/json"}
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    return response
                else:
                    self.algorithm.Debug(f"Request failed with status {response.status_code}: {response.text}")
            except Exception as ex:
                self.algorithm.Debug(f"Attempt {attempt + 1} failed: {str(ex)}")
            time.sleep(delay)
        return None
