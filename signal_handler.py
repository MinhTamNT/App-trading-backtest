class SignalHandler:
    def __init__(self, algorithm):
        self.algorithm = algorithm

    def CheckSignals(self):
        for symbol in self.algorithm.ema20_by_symbol.keys():
            if symbol not in self.algorithm.historical_data:
                self.algorithm.Debug(f"No historical data found for {symbol}.")
                continue

            ema = self.algorithm.ema20_by_symbol[symbol]
            historical_data = sorted(self.algorithm.historical_data[symbol], key=lambda x: x.Time)

            if not historical_data:
                self.algorithm.Debug(f"No historical data available for {symbol}.")
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

                self.algorithm.Debug(f"{symbol} - {date_str} - Close: {close}, EMA: {ema.Current.Value}, Difference: {difference}")

                if previous_difference is not None:
                    if previous_difference < 0 and difference > 0:
                        self.algorithm.HandleBuySignal(symbol, close)
                    elif previous_difference > 0 and difference < 0:
                        self.algorithm.HandleSellSignal(symbol)

                previous_difference = difference
