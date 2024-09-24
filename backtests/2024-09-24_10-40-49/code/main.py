from datetime import datetime, timedelta
from fileinput import close

import requests
from QuantConnect import Resolution, DataNormalizationMode
from QuantConnect.Algorithm import QCAlgorithm
from QuantConnect.Brokerages import BrokerageName
from QuantConnect.Orders.Fees import ConstantFeeModel
import sys
import os
from dotenv import load_dotenv
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from get_stock_price_tcbs import StockDataService

class EMAlgorithm(QCAlgorithm):
    def initialize(self):
        load_dotenv()
        self.ApiKey = "2a23659e-635d-4b93-851a-19ceadb8305f"
        self.set_start_date(datetime.now() - timedelta(days=365))
        self.set_end_date(datetime.now())
        self.set_warmup(timedelta(days=1))
        self.set_security_initializer(lambda security: security.SetFeeModel(ConstantFeeModel(0.1)))

        self.set_cash(1000000000)

        self.FEE_PERCENT = 0.15 / 100
        self.TAX_PERCENT = 0.1 / 100

        self.symbols = ["GAS"]
        self.ema_symbol = {}
        self.historical_data = {}
        self.stock_data_service = StockDataService(self)

        # Thêm chứng khoán và cài đặt EMA
        for symbol in self.symbols:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.SetDataNormalizationMode(DataNormalizationMode.RAW)
            self.set_benchmark(symbol)
            self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
            self.ema_symbol[symbol] = self.ema(symbol, 20, Resolution.DAILY)
            self.historical_data[symbol] = self.stock_data_service.get_stock_price_tcbs(symbol, "20-09-2023", "20-09-2024")

        self.Debug("Initialization complete.")
        self.transactions_log = []
        self.check_ema_signal(20)

    def OnWarmupFinished(self):
        self.Debug("Finished warming up")
        self.check_ema_signal(20)

    def check_ema_signal(self, ema_period=20):
        for symbol in self.symbols:
            if symbol not in self.historical_data:
                self.Debug(f"No historical data found for {symbol}.")
                continue

            historical_data = self.historical_data[symbol]
            previous_difference = None
            for i in range(len(historical_data) - 1):
                current_bar = historical_data.iloc[i]
                price = current_bar['price']
                self.ema_symbol[symbol].Update(self.Time, price)

                close = current_bar['price']
                difference = close - self.ema_symbol[symbol].Current.Value

                if previous_difference is not None:
                    if previous_difference < 0 and difference > 0:
                        self.HandleBuySignal(symbol, close, current_bar['date'])
                    elif previous_difference > 0 and difference < 0:
                        self.HandleSellSignal(symbol, close, current_bar['date'])

                previous_difference = difference

    def HandleBuySignal(self, symbol, price, date):
        purchasing_power = self.Portfolio.Cash - self.Portfolio.Cash * 0.0015
        volume = int(purchasing_power / price)
        self.MarketOrder(symbol, volume)  # Buy shares
        self.log_transaction(symbol, "B", price, volume, fee=self.FEE_PERCENT, tax=None, date=date)

    def HandleSellSignal(self, symbol, price, date):
        volume = self.Portfolio[symbol].Quantity
        self.MarketOrder(symbol, -volume)
        self.log_transaction(symbol, "S", price, volume, fee=self.FEE_PERCENT, tax=self.TAX_PERCENT, date=date)

    def log_transaction(self, symbol, action, price, volume, fee=None, tax=None, date=None):
        total_value = volume * price
        total_cost = (fee if fee is not None else 0) + (tax if tax is not None else 0)
        self.Debug(f"Volume {volume}")
        # Đảm bảo giao dịch hợp lệ
        if total_value < 0 or volume < 0 or price < 0:
            self.Debug(f"Invalid transaction for {symbol}: volume={volume}, price={price}, fee={fee}, tax={tax}, total_value={total_value}")
            return

        transaction = {
            'Symbol': symbol,
            'Action': action,
            'Volume': volume,
            'Price': price,
            'Fee': fee,
            'Tax': tax,
            'Total Value': total_value,
            'Total Cost': total_cost,
            'Date': date.strftime('%Y-%m-%d') if date else self.Time.strftime('%Y-%m-%d')
        }

        self.transactions_log.append(transaction)

    def OnEndOfAlgorithm(self):


        if self.transactions_log:
            df = pd.DataFrame(self.transactions_log)

            # Ensure that the first action is not 'S'
            if not df.empty and df.iloc[0]['Action'] == 'S':
                df = df.iloc[1:]

            df['Volume'] = (df['Volume'] // 100) * 100

            # Calculate total value
            df['Total Value'] = df['Volume'] * df['Price']

            # Calculate fees and taxes
            df['Fee'] = self.FEE_PERCENT * df['Total Value']

            df['Tax'] = df.apply(lambda row: 0 if row['Action'] == 'B' else self.TAX_PERCENT * row['Total Value'],
                                 axis=1)

            df['Total Cost'] = df['Fee'] + df['Tax']

            # Calculate net value (NAV)
            df['Total Value'] = df['Total Value'].astype(int)
            df['NAV'] = (df['Total Value'] - df['Total Cost']).astype(int)

            df['profit'] = 0
            last_buy_net_value = None
            last_buy_volume = None

            # Initialize cash balance with the initial cash
            # df['Cash Balance'] = init_cash

            # Loop to assign volumes and calculate profit for matched buy-sell pairs
            for index, row in df.iterrows():
                if row['Action'] == 'B':
                    last_buy_net_value = df.at[index, 'NAV']
                    last_buy_volume = df.at[index, 'Volume']  # Store the buy volume

                    self.Debug(f"index {index}")
                    # if index == 1:
                    #
                    #     df.at[index, 'Cash Balance'] = init_cash - df.at[index, 'Total Value'] - df.at[
                    #         index, 'Total Cost']
                    # else:
                    #     if index - 1 in df.index:  # Check if previous index exists
                    #         df.at[index, 'Cash Balance'] = df.at[index - 1, 'Cash Balance'] - df.at[
                    #             index, 'Total Value'] - df.at[index, 'Total Cost']

                elif row['Action'] == 'S':
                    if last_buy_net_value is not None and last_buy_volume is not None:
                        # Match sell volume with the previous buy volume
                        df.at[index, 'Volume'] = last_buy_volume

                        # Recalculate values based on the updated volume
                        df.at[index, 'Total Value'] = df.at[index, 'Volume'] * row['Price']
                        df.at[index, 'Fee'] = self.FEE_PERCENT * df.at[index, 'Total Value']
                        df.at[index, 'Tax'] = self.TAX_PERCENT * df.at[index, 'Total Value']
                        df.at[index, 'Total Cost'] = df.at[index, 'Fee'] + df.at[index, 'Tax']
                        df.at[index, 'NAV'] = df.at[index, 'Total Value'] - df.at[index, 'Total Cost']

                        # Calculate profit as the difference between sell NAV and buy NAV
                        df.at[index, 'profit'] = df.at[index, 'NAV'] - last_buy_net_value

                        # Update cash balance after a sell
                        # if index - 1 in df.index:  # Check if previous index exists
                        #     df.at[index, 'Cash Balance'] = df.at[index - 1, 'Cash Balance'] + df.at[
                        #         index, 'Total Value'] - df.at[index, 'Total Cost']

                        # After the sell, reset the buy value and volume for next transactions
                        last_buy_net_value = None
                        last_buy_volume = None

            df['profit'] = df['profit'].astype(int)

            # Summary calculations
            total_profit = df['profit'].sum()
            total_cash = df['NAV'].sum()
            total_profit_percentage = (total_profit / total_cash) * 100 if total_cash != 0 else 0
            total_fee = df['Fee'].sum()
            total_tax = df['Tax'].sum()
            total_cost = total_fee + total_tax

            # Rearrange columns
            df = df[['Symbol', 'Date', 'Action', 'Price', 'Volume', 'Total Value', 'Fee', 'Tax', 'Total Cost',
                      'NAV', 'profit']]

            # Output results
            self.Debug(
                f"\n{df.to_string(index=False, formatters={'Total Value': '{:,.0f} VND'.format, 'Fee': '{:,.0f} VND'.format, 'Tax': '{:,.0f} VND'.format, 'Total Cost': '{:,.0f} VND'.format, 'Cash Balance': '{:,.0f} VND'.format, 'NAV': '{:,.0f} VND'.format, 'profit': '{:,.0f} VND'.format})}")
            self.Debug(f"Total Profit: {total_profit:,.0f} VND")
            self.Debug(f"Total Profit Percentage: {total_profit_percentage:.2f}%")
            self.Debug(f"Total Fee: {total_fee:,.0f} VND")
            self.Debug(f"Total Tax: {total_tax:,.0f} VND")
            self.Debug(f"Total Cost: {total_cost:,.0f} VND")
        else:
            self.Debug("No transactions were made.")






