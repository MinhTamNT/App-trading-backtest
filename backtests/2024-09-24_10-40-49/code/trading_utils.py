class TradingUtils:
    def __init__(self, fee_percent, tax_percent):
        self.FEE_PERCENT = fee_percent
        self.TAX_PERCENT = tax_percent

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
        new_cash_balance, nav = self.update_cash_balance_and_nav(cash_balance, total_value, total_cost, is_buy=False)
        df.at[index, 'Cash Balance'] = new_cash_balance
        df.at[index, 'NAV'] = nav

        # Use purchasing power of the last buy
        df.at[index, 'Purchasing Power'] = df.at[index - 1, 'Purchasing Power']

        return new_cash_balance
