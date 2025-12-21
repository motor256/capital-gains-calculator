import yfinance as yf
import pandas as pd
from datetime import datetime


def fetch_share_prices(ticker, start_date, end_date):
    # Log the input parameters for debugging
    print(f"Fetching data for ticker: {ticker}, start: {start_date}, end: {end_date}")
    stock_data = yf.download(ticker, start=start_date, end=end_date)
    if stock_data.empty:
        raise Exception(f"No data found for ticker '{ticker}' from {start_date} to {end_date}.")
    return stock_data


def fetch_closest_close_price(data, target_date):
    """
    Fetch the market close price closest to a given date from the DataFrame.
        data (pd.DataFrame): DataFrame containing historical stock prices.
        target_date (str): The target date in 'YYYY-MM-DD' format.

    Returns:
        float: The close price closest to the target date, or None if not found.
    """
    target_date = datetime.strptime(target_date, "%Y-%m-%d")
    data.index = pd.to_datetime(data.index)  # Ensure the index is datetime
    closest_date = data.index[data.index.get_indexer([target_date], method='nearest')[0]]
    if abs((closest_date - target_date).days) > 5: # We consider that 5 days apart is too far
        raise Exception(f"Fetch_closest_close_price: {closest_date} and {target_date} are too far apart")
    closest_data_row = data.loc[closest_date]
    closest_close_price = float(closest_data_row['Close'].iloc[0])
    if closest_close_price == None:
        raise Exception (f"Could not find price for {target_date}")
    return closest_close_price


if __name__ == "__main__":
    # Example usage
    # Predefined values for testing in environments where input() might not work
    ticker_symbol = "NVDA"  # Replace with desired ticker
    start_date = "2017-01-01"  # Replace with desired start date
    end_date = "2024-12-21"  # Replace with desired end date

    data = fetch_share_prices(ticker_symbol, start_date, end_date)

    if data is not None:
        print(data.head())  # Display the first few rows of the data

        # Optionally, save to a CSV file
        save_to_csv = "yes"  # Replace with 'yes' or 'no' as needed
        if save_to_csv == 'yes':
            filename = f"{ticker_symbol}_prices_{start_date}_to_{end_date}.csv"
            data.to_csv(filename)
            print(f"\nData saved to {filename}")

        # Fetch close price closest to a specific date
        target_date = "2024-12-01"  # Replace with desired target date
        x = fetch_closest_close_price(data, target_date)
        print(f"\nFetched value: {x}, of type {type(x)}")
