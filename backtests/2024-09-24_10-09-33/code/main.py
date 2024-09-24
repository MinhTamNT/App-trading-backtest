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
from tabulate import tabulate
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
        self.TAX_PERCENT = 0.15 / 100

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
        self.log_transaction(symbol, "B", price, fee=self.FEE_PERCENT, tax=None, date=date)

    def HandleSellSignal(self, symbol, price, date):
        self.log_transaction(symbol, "S", price,  fee=self.FEE_PERCENT, tax=self.TAX_PERCENT, date=date)

    def log_transaction(self, symbol, action, price, fee=None, tax=None, date=None,
                        cash_balance=None):
        transaction = {
            'Symbol': symbol,
            'Date': date.strftime('%Y-%m-%d') if date else self.Time.strftime('%Y-%m-%d'),
            'Action': action,
            'Volume': 0,
            'Price': price,
            'Purchasing Power': 0,
            'Fee': fee,
            'Tax': tax,
            'Total Value': 0,
            'Total Cost': 0,
            'Cash Balance': self.Portfolio.Cash,
            'NAV': self.Portfolio.Cash,
            'Profit': 0,
        }
        self.transactions_log.append(transaction)

    def calculate_fees_and_taxes(self, action, total_value):
        fee = self.FEE_PERCENT * total_value
        tax = 0 if action == 'B' else self.TAX_PERCENT * total_value
        total_cost = fee + tax
        return fee, tax, total_cost

    def calculate_volume_and_value(self, purchasing_power, price):
        volume = (purchasing_power // price).astype(int)
        volume = (volume // 100) * 100
        total_value = volume * price
        return volume, total_value

    def update_cash_balance_and_nav(self, cash_balance, total_value, total_cost, is_buy=True):
        if is_buy:
            new_cash_balance = cash_balance - total_value - total_cost
        else:
            new_cash_balance = cash_balance + total_value - total_cost
        nav = new_cash_balance + total_value
        return new_cash_balance, nav

    def process_buy(self, df, index, cash_balance, initial_cash_balance):
        # Calculate purchasing power and volume
        purchasing_power = cash_balance - cash_balance * 0.0015
        df.at[index, 'Purchasing Power'] = purchasing_power
        volume, total_value = self.calculate_volume_and_value(purchasing_power, df.at[index, 'Price'])

        # Update DataFrame with calculated values
        df.at[index, 'Volume'] = volume
        df.at[index, 'Total Value'] = total_value

        # Calculate fees, taxes, and costs
        fee, tax, total_cost = self.calculate_fees_and_taxes('B', total_value)
        df.at[index, 'Fee'] = fee
        df.at[index, 'Tax'] = tax
        df.at[index, 'Total Cost'] = total_cost

        # Update cash balance, NAV, and profit
        new_cash_balance, nav = self.update_cash_balance_and_nav(cash_balance, total_value, total_cost)
        df.at[index, 'Cash Balance'] = new_cash_balance
        df.at[index, 'NAV'] = nav
        df.at[index, 'profit'] = nav - initial_cash_balance

        return new_cash_balance

    def process_sell(self, df, index, cash_balance):
        # Use the volume of the last buy
        df.at[index, 'Volume'] = df.at[index - 1, 'Volume']

        # Calculate total value
        total_value = df.at[index, 'Volume'] * df.at[index, 'Price']
        df.at[index, 'Total Value'] = total_value

        # Calculate fees, taxes, and costs
        fee, tax, total_cost = self.calculate_fees_and_taxes('S', total_value)
        df.at[index, 'Fee'] = fee
        df.at[index, 'Tax'] = tax
        df.at[index, 'Total Cost'] = total_cost

        # Update cash balance and NAV
        new_cash_balance, nav = self.update_cash_balance_and_nav(cash_balance, total_value, total_cost)
        df.at[index, 'Cash Balance'] = new_cash_balance
        df.at[index, 'NAV'] = nav

        # Use purchasing power of the last buy
        df.at[index, 'Purchasing Power'] = df.at[index - 1, 'Purchasing Power']

        return new_cash_balance

    def OnEndOfAlgorithm(self):
        if self.transactions_log:
            df = pd.DataFrame(self.transactions_log)

            if not df.empty and df.iloc[0]['Action'] == 'S':
                df = df.iloc[1:]

            cash_balance = self.Portfolio.Cash
            df['profit'] = 0
            df['Cash Balance'] = 0
            df['NAV'] = 0
            initial_cash_balance = cash_balance

            for index, row in df.iterrows():
                if row['Action'] == 'B':  # Buy action
                    df.at[index, 'Purchasing Power'] = cash_balance - cash_balance * 0.0015
                    df.at[index, 'Volume'] = (df.at[index, 'Purchasing Power'] // df.at[index, 'Price']).astype(int)
                    df.at[index, "Volume"] = (df.at[index, "Volume"] // 100) * 100

                    total_value = df.at[index, 'Volume'] * df.at[index, 'Price']
                    df.at[index, 'Total Value'] = total_value
                    fee, tax, total_cost = self.calculate_fees_and_taxes('B', total_value)
                    df.at[index, 'Fee'] = fee
                    df.at[index, 'Tax'] = tax
                    df.at[index, 'Total Cost'] = total_cost

                    new_cash_balance, nav = self.update_cash_balance_and_nav(cash_balance, total_value, total_cost,
                                                                             is_buy=True)
                    df.at[index, 'Cash Balance'] = new_cash_balance
                    df.at[index, 'NAV'] = nav
                    if index == 1 or df.at[index - 1, 'Action'] == 'S':  # Mua đầu tiên hoặc mua sau lần bán
                        df.at[index, 'profit'] = nav - initial_cash_balance
                    else:  # Mua tiếp theo sau lần bán gần nhất
                        df.at[index, 'profit'] = nav - df.at[index - 1, 'NAV']


                    df.at[index, 'profit'] = nav - initial_cash_balance

                    cash_balance = new_cash_balance

                elif row['Action'] == 'S':  # Sell action
                    df.at[index, 'Volume'] = df.at[index - 1, 'Volume']
                    total_value = df.at[index, 'Volume'] * df.at[index, 'Price']
                    df.at[index, 'Total Value'] = total_value
                    fee, tax, total_cost = self.calculate_fees_and_taxes('S', total_value)
                    df.at[index, 'Fee'] = fee
                    df.at[index, 'Tax'] = tax
                    df.at[index, 'Total Cost'] = total_cost

                    new_cash_balance, _ = self.update_cash_balance_and_nav(cash_balance, total_value, total_cost,
                                                                           is_buy=False)
                    df.at[index, 'Cash Balance'] = new_cash_balance

                    df.at[index, 'NAV'] = new_cash_balance

                    df.at[index, 'profit'] = df.at[index, 'NAV'] - df.at[index - 1, 'NAV']

                    df.at[index, 'Purchasing Power'] = df.at[index - 1, 'Purchasing Power']

                    cash_balance = new_cash_balance

            # Convert profit to int
            df['profit'] = df['profit'].astype(int)

            # Debugging output for validation
            self.Debug("\nTransaction DataFrame before summary:")
            self.Debug(tabulate(df, headers='keys', tablefmt='psql'))

            # Calculate totals for summary
            total_profit = df['profit'].sum()
            total_cash = df['NAV'].sum()
            total_profit_percentage = (total_profit / total_cash * 100) if total_cash != 0 else 0
            total_fee = df['Fee'].sum()
            total_tax = df['Tax'].sum()
            total_cost = total_fee + total_tax

            # Create a summary DataFrame
            summary_df = pd.DataFrame({
                'Cash Balance': [cash_balance],
                'NAV': [initial_cash_balance]
            })

            # Rearrange and format the final DataFrame
            df = df[['Symbol', 'Date', 'Action', 'Price', 'Purchasing Power', 'Volume', 'Total Value', 'Fee', 'Tax',
                     'Total Cost', 'NAV', 'profit', 'Cash Balance']]
            final_df = pd.concat([summary_df, df], ignore_index=True)

            final_df.columns = [
                'Cash Balance', 'NAV', 'Symbol', 'Date', 'Action', 'Price', 'Purchasing Power', 'Volume', 'Total Value',
                'Fee', 'Tax', 'Total Cost', 'Profit'
            ]

            # Format and display final DataFrame
            final_df = final_df.applymap(
                lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else '-' if pd.isna(x) else x)

            self.Debug("\nSummary and Transaction Log:")
            self.Debug(tabulate(final_df, headers='keys', tablefmt='psql'))

            # Display totals
            self.Debug(f"\nTotal Profit: {total_profit:,.0f} VND")
            self.Debug(f"Total Profit Percentage: {total_profit_percentage:.2f}%")
            self.Debug(f"Total Fee: {total_fee:,.0f} VND")
            self.Debug(f"Total Tax: {total_tax:,.0f} VND")
            self.Debug(f"Total Cost: {total_cost:,.0f} VND")
        else:
            self.Debug("No transactions were made.")



















