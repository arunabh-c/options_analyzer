from ibapi.client import *
from ibapi.wrapper import *
import datetime
import time
import threading
from ib_insync import *
import yfinance as yf
from datetime import datetime
import webbrowser

from datetime import date

today = date.today().strftime("%Y%m%d")

port = 7497
stk = "GOOG"
days_array = []
time_array = []
chrome_path = 'C:/Program Files/Google/Chrome/Application/chrome.exe %s'
threshold = 1.5
browser_switch=False
max_trade_string=""
max_trade = 0.0

def get_historical_data(app, contract):
    """
    Requests historical data for a given contract.
    This function is called by the main thread.
    """
    app.historical_data = [] # Clear the list before each new request
    app.done.clear() # Clear the event for a new request
    
    # Use a unique reqId for each request
    req_id = app.nextId() 
    
    app.reqHistoricalData(
        reqId=req_id, 
        contract=contract, 
        endDateTime=today + " 17:30:00 US/Eastern", 
        durationStr="6 M", 
        barSizeSetting="1 hour", 
        whatToShow="TRADES", 
        useRTH=1, 
        formatDate=1, 
        keepUpToDate=False, 
        chartOptions=[]
    )
    
    # Wait for the done event to be set or for a timeout
    app.done.wait(timeout=60)
    
    # Return the data
    return app.historical_data

def get_current_stock_price(ticker_symbol):
    """
    Retrieves the current stock price for a given ticker symbol using yfinance.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        current_price = info.get('currentPrice')
        if current_price:
            print(f"Current Price for {ticker_symbol}: ${current_price:,.2f}")
            return current_price
        else:
            print(f"Could not retrieve current price for {ticker_symbol}.")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def get_days_to_expiry(expiry, date):
    date1 = datetime.strptime(date, "%Y%m%d")
    date2 = datetime.strptime(expiry, "%Y%m%d")

    # Calculate the difference, which results in a timedelta object
    time_difference = date2 - date1

    # Return the absolute number of days
    return abs(time_difference.days)
        
def get_daily_change(threshold, data, prev_data, name, expiry):
    
    delta = float(data.wap)/float(prev_data.wap)
    delta = round(delta,2)
    global max_trade
    global max_trade_string
    if  delta > threshold:
        days = get_days_to_expiry(expiry, data.date.split()[0])
        days_array.append(days)
        time_array.append(data.date.split()[1])
        print(f"The option {name} went {round(delta,2)}x from {prev_data.wap} @ {prev_data.date} to {data.wap} @ {data.date}, {days} days from expiry")
        trade_vol = round(data.wap * 100 * data.volume,2)
        if trade_vol > max_trade:
            max_trade = trade_vol
            max_trade_string = "The option " + name + " had trading volume of " + str(data.volume) + " for a total of " + str(trade_vol) + " on " + data.date

        print(f"The option {name} had trading volume of {data.volume} for a total of ${trade_vol}")
        return True
    else:
        return False
    

class TestApp(EClient, EWrapper):
    def __init__(self):
        EClient.__init__(self, self)
        self.historical_data = []
        self.done = threading.Event()
        self.orderId = -1

    def nextValidId(self, orderId: OrderId):
        self.orderId = orderId

    def nextId(self):
        self.orderId += 1
        return self.orderId

    def historicalData(self, reqId, bar):
        # This is where the historical data is received
        self.historical_data.append(bar)

    def historicalDataEnd(self, reqId, start, end):
        # This method is called when the data request is complete.
        #print(f"Historical Data Ended for {reqId}.")
        self.done.set()

    def error(self, reqId, errorCode, errorString, advancedOrderReject=""):
        # Handle errors and signal completion to prevent hanging
        #print(f"Error: reqId={reqId}, code={errorCode}, string={errorString}")
        self.done.set()
        
    def disconnect_and_stop(self):
        # A separate method to cleanly disconnect and stop the thread
        self.disconnect()
        # You might need to add a small sleep or a flag to ensure the thread fully exits
        time.sleep(1)


if __name__ == "__main__":
    # Get current stock price for GOOG
    price = get_current_stock_price(stk)
    if price is None:
        exit() # Exit if we can't get the price

    # Connect to TWS/IB Gateway using the ibapi classes
    app = TestApp()
    app.connect("127.0.0.1", port, clientId=0)
    
    # Start the client thread
    client_thread = threading.Thread(target=app.run)
    client_thread.start()
    
    # Wait for the connection to be established and valid ID received
    app.nextValidId(1) 
    time.sleep(2) # Give it a moment to connect

    # Get option chain details
    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=1) # Use a separate clientId for ib_insync
    contract_details = ib.reqContractDetails(
        Option(
            symbol=stk,
            exchange='SMART',
            lastTradeDateOrContractMonth='',
            right='C',
            strike=0
        )
    )

    if contract_details:
        
        total = 0;
        total_contracts = 0
        avail_time_data = 0
        for d in contract_details:
            c = d.contract
            # Filter for a specific strike for this example
            if c.strike > price:
                time.sleep(4)
                #print(f"\nRequesting data for: {c.symbol} {c.lastTradeDateOrContractMonth} {c.right} {c.strike}")
                total_contracts = total_contracts + 1
                # Create a contract for the ibapi client
                option_contract = Contract()
                option_contract.symbol = c.symbol
                option_contract.secType = c.secType
                option_contract.exchange = c.exchange
                option_contract.currency = c.currency
                option_contract.right = c.right
                option_contract.strike = c.strike
                option_contract.lastTradeDateOrContractMonth = c.lastTradeDateOrContractMonth
                
                # Request historical data and wait for the result
                time_data = get_historical_data(app, option_contract)
                
                if time_data:
                    #print(f"Received {len(time_data)} bars of historical data.")
                    avail_time_data = avail_time_data + 1
                    ctr = 0
                    pre_strike_prefix = "000"
                    if (int(c.strike) >= 100):
                       pre_strike_prefix = "00"
                    elif (int(c.strike) < 10):
                       pre_strike_prefix = "0000"
                    name = c.symbol + c.lastTradeDateOrContractMonth[2:] + c.right + pre_strike_prefix + str(int((c.strike)*1000))
                    prev_data = time_data[0]
                    for data in time_data:
                        if (get_daily_change(threshold,data, prev_data,name,c.lastTradeDateOrContractMonth)):
                            ctr = ctr + 1
                        prev_data = data                            
                    if ctr:
                      total = total + 1
                      print(f"{total}. The option {name} went >= {threshold}x {ctr} times")
                      url = "https://finance.yahoo.com/chart/" + name
                      print(f"url: {url}\n")
                      if browser_switch:
                        webbrowser.get(chrome_path).open_new_tab(url)
                #else:
                    #print("No historical data was returned.")
        print(f"{avail_time_data} contracts out of a total of {total_contracts} eligible contracts were provided by IBKR ({round(100.0*avail_time_data/total_contracts,2)})%)")
        days_array.sort()
        middle_element = days_array[len(days_array) // 2]
        print(f"Median days from expiry is {middle_element}")
        time_array.sort()
        middle_idx = len(time_array) // 2
        print(f"Median trading times are {time_array[middle_idx]}, {time_array[max(0,middle_idx-1)]} & {time_array[min(middle_idx+1,len(time_array)-1)]}")
        print(max_trade_string)

    else:
        print("No options contracts found for {stk}.")

    # Cleanly disconnect from both connections
    ib.disconnect()
    app.disconnect_and_stop()
    client_thread.join() # Ensure the thread is finished before exiting
