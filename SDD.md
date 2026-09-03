### RANKED ASSET ALLOCATION MODEL OPTIMISED FOR INDIAN EQUITIES (NIFTY 50).

NOTE:   This is Quantitative trading Strategy. When backtesting it, we should take into consideration the following:
        - Avoid Look-ahead bias: Always shift the trading signal by 1 so that it avoid look ahead bias.
        - Avoid Survivorship bias. Take all the ETFs from 2018 to 2016 that has been included.
        - Any mistake may falsify the backtest and make it irrelavant. Always be carefull when writing the code in Python.

1. INTRODUCTION:

This Strategy is based on the Ranked asset allocation model proposed by GIOELE GIORDANO.
We take ETFs in the indian markets as the assets. (Should be survivorship bias free.)
After the Universe is considered , we rank them based on Momentum, Volatility and Volume confirmation. (instead of Correlation and ATR as mention in the model)


Data: from yfinance
Timeframe: 1D data

2. DATA ACQUISITION & CLEAN-UP:

OHLC Data is acquired from yfinance.
- 10 year Data period.
- Universe => [GOLDBEES.NS, NIFTYBEES.NS, SILVERBEES.NS, ITBEES.NS, LIQUIDBEES.NS, PSUBANKBEES.NS, MID150BEES.NS, NIFTYSMLCAP250.NS]
- Data should be winsorized with a lowerbound bound of 99.9 percentile and an upper bound of 0.01 percentile to avoid fake tail events.
- Avoid Muhurat trading days, because it can cause extreme events. 
- Split the data into 3 sections with 60% percentage of the data for training, 20% percentage for validation and 20% for testing. 


3. CORE STRATEGY:

Apply the following for each stock in the Data File

Take Weights as:
    W1 = 0.3
    W2 = 0.3
    W3 = 0.3
    x = 10

Take 3 factors:
    - Momentum (M):
        Calculated by: Taking the rate of change of close prices (ROC of close prices) across a time period of 22 days.
        Formula: (Close - Close.shift(22)) / Close.shift(22)
    - Volatility (V)
        Calculated by: The Yang Zhang Volatility over a period of 10 days.
    - Volume Confirmation (VC):
        Calculated by: Taking Volume.rolling(10).mean() / Volume.rolling(22).mean()

Then the following are calculated:
    - Rank_of_M: Rank the Momentum values in descending order. (The highest momentum will get the highest rank)
    - Rank_of_V: Rank the Volatility Values in ascending order. (The lowest Volatility values will get the highest rank)
    - Rank_of_VC: Rank the the Volume Confirmation in descending order (The highest Volume confirmation will get the highest rank)
    - Total_Rank = (W1 * Rank_of_M + W2 * Rank_of_V + W3 * Rank_of_VC) + M/x

Note: Eventhough the factors and ranks are calculated on a daily basis, Total Rank is done on a monthly basis by taking the last values of the month.

Capital is allocated to the first 5 ranking assets with equal weights until the next ranking in done.

4. BACKTESTING ENGINE
- Backtest over the data provided and show all the important metrics like :
    - Total returns and p&l
    - CAGR
    - Sharp Ratio
    - Calmar Ratio
    - Sortino ratio
    - etc....
- Include Indian stock market trading costs and taxes. (brokerage, STT, Capital gains tax, etc. ) when backtesting.
- Plot the graph on the cummulative returns of the strategy and cummmulative returns of the nifty50 index taken from yfinance.

