from ibapi.client import *
from ibapi.wrapper import *
import datetime
import time
import threading
from ib_insync import *
import yfinance as yf
from datetime import datetime

port = 7497
stk = "RKLB"
days_array = []

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
        endDateTime="20250923 11:00:00 US/Eastern", 
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
        
def get_daily_change(threshold, data, name, expiry):
    
    delta = (data.close - data.open)/data.open
    delta = round(delta,2)
    if  delta > threshold:
        days = get_days_to_expiry(expiry, data.date.split()[0])
        days_array.append(days)
        print(f"The option {name} went {round(delta+1,2)}x from {data.open} to {data.close}, {days} days from expiry on {data.date}")
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
                    name = c.symbol + c.lastTradeDateOrContractMonth[2:] + c.right + "00" + str(int(c.strike)) + "000"
                    for data in time_data:
                        if (get_daily_change(1,data, name,c.lastTradeDateOrContractMonth)):
                            ctr = ctr + 1                            
                    if ctr:
                      total = total + 1
                      print(f"{total}. The option {name} went >= {1+1}x {ctr} times \n")
                #else:
                    #print("No historical data was returned.")
        print(f"{avail_time_data} contracts out of a total of {total_contracts} eligible contracts were provided by IBKR")
        days_array.sort()
        middle_element = days_array[len(days_array) // 2]
        print(f"Median days from expiry is {middle_element}")

    else:
        print("No options contracts found for {stk}.")

    # Cleanly disconnect from both connections
    ib.disconnect()
    app.disconnect_and_stop()
    client_thread.join() # Ensure the thread is finished before exiting