import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get username of current session
    username = db.execute("SELECT username FROM users WHERE id=?", session["user_id"])

    # Get available cash from the user
    avail_cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])

    # Get number of stocks purchased from transaction database
    num_stocks = db.execute("SELECT DISTINCT stock FROM 'transaction' WHERE user = ?", session["user_id"])
    count = len(num_stocks)     # Length of the list

    # If summary exists, remove
    db.execute("DROP TABLE IF EXISTS 'summary'")

    # Create Summary Table Database
    if count != 0:
        # Get shares owned by user
        stock_shares = db.execute("SELECT user, stock, SUM(no_shares) FROM 'transaction' WHERE user = ? GROUP BY stock", session['user_id'])

        for i in range(0, count):
             if stock_shares[i]['SUM(no_shares)'] != 0:
                 # Get stock symbol
                stock = num_stocks[i]['stock']
                # Lookup the value of the stock
                stock_value = lookup(stock)

                # Get total value of the stock
                stock_total = stock_value['price'] * stock_shares[i]['SUM(no_shares)']

                # Store the summary into a separate table
                db.execute("CREATE TABLE IF NOT EXISTS 'summary' (stock TEXT, shares INTEGER, market_price REAL, price REAL)")
                db.execute("INSERT into 'summary' (stock, shares, market_price, price) VALUES (?, ?, ?, ?)", stock_shares[i]['stock'], stock_shares[i]['SUM(no_shares)'], stock_value['price'], stock_total)

                summary = db.execute("SELECT * FROM 'summary'")

                total_assets = avail_cash[0]['cash'] + summary[0]['price']

        return render_template("index.html", user=username[0]['username'], cash=usd(avail_cash[0]['cash']), summary=summary, total_assets=usd(total_assets))

    ### Else, if there is no stocks in the system yet, then display nothing, but only your cash.
    else:
        total_assets = avail_cash[0]['cash']

        return render_template("index.html", user=username[0]['username'], cash=usd(avail_cash[0]['cash']), total_assets=usd(total_assets))




@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Check if the user entered a valid symbol or number of shares
        if not request.form.get("symbol"):
            return apology ("Enter a valid stock symbol")

        # Check if user entered a valid number of shares
        if int(request.form.get("shares")) < 0:
            return apology("Enter quantity greater than 0")

        # Check the stock price
        stock = lookup(request.form.get("symbol"))

        # If stock symbol is not valid
        if not stock:
            return apology("Enter a valid stock symbol")

        # Total cost of shares to buy
        stock_purchase = stock['price'] * int(request.form.get("shares"))

        # Check available cash the user has
        avail_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])

        # Check if user has enough money, if not return
        if avail_cash[0]['cash'] < stock_purchase:
            return apology("Not enough cash to buy")

        # Proceed with purchase of stocks and record in finance.db database
        else:
            # If no new table is created, create new table storing user purchase, number of shares, cost, date
            # Create a new table
            db.execute("CREATE TABLE IF NOT EXISTS 'transaction' (user TEXT, stock TEXT, no_shares INTEGER, shares_cost REAL, purchase_price REAL, buy_sell TEXT, date TEXT)")

            # Log transaction into the table
            db.execute("INSERT into 'transaction' (user, stock, no_shares, shares_cost, purchase_price, buy_sell, date) VALUES (?, ?, ?, ?, ?, ?, ?)", session["user_id"], stock['symbol'], request.form.get("shares"), stock_purchase, stock['price'], "buy", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            # Update remaining cash in the database
            avail_cash = avail_cash[0]['cash'] - stock_purchase

            db.execute("UPDATE users SET cash = ? WHERE id = ?", avail_cash, session["user_id"])

        return redirect("/")

    else:
        # When wanting to get an input from the user
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM 'transaction' WHERE user = ?", session['user_id'])

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # If user access the quote via Post
    if request.method == "POST":

        # Check if the user entered a symbol
        if not request.form.get("symbol"):
            return apology("Please enter a stock symbol")

        # Look up the user entered symbol
        stock = lookup(request.form.get("symbol"))

        # Check if symbol entered is valid
        if stock == None:
            return apology('Symbol is not Valid')

        # Format price to USD
        price = usd(stock['price'])

        return render_template("quoted.html", stockname=stock, price=price)

    else:
        # If user is getting another symbol, direct to GET
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # If user access the register via Post
    if request.method == "POST":

        # If user does not enter a valid username
        if not request.form.get("username"):
            return apology("Must Enter a Username")

        elif not request.form.get("password"):
            return apology("Must Enter a Valid Password")

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match")

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Generate Hash
        hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)

        if not hash:
            return apology("User already exists")

        # Insert to Database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)

        session[id] = hash

        return redirect("/")

    # If the HTML is submitted as GET, then redirect the user to register again as a Post method
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Check if user selected a stock
        if not request.form.get("symbol"):
            return apology("Select a Stock")

        # Check if user picked a stock not found in the portfolio
        stocks = db.execute("SELECT stock FROM 'summary'")

        # Add stocks to list
        list_stock = []
        count = len(stocks)

        # Loop through the stock and add to the list
        for i in range(0, count):
            list_stock.append(stocks[i]['stock'])

        # Check if the user used a stock that is in their portfolio
        if request.form.get("symbol") not in list_stock:
            return apology("Stock not in your Portfolio")

        # Check if user entered a valid number
        if int(request.form.get("shares")) < 1:
            return apology("Please enter valid share number")

        # Check if the number of shares entered to sell is less than the number of shares owned
        # Get total number of shares for the specifc share to sell
        shares = db.execute("SELECT shares FROM 'summary' WHERE stock = ?", request.form.get("symbol"))

        # Check if their is enough shares to sell
        if int(request.form.get("shares")) > shares[0]['shares']:
            return apology("Not enough shares")

        # Final cost when selling stock
        stock_price = lookup(request.form.get("symbol"))
        return_price = stock_price['price'] * int(request.form.get("shares"))
        neg_price = -return_price

        # Get new shares and price to be inputted into the summary database
        new_shares = shares[0]['shares'] - int(request.form.get("shares"))
        new_price = stock_price['price'] * new_shares
        neg_shares = -int(request.form.get("shares"))

        # Log transaction into the database transaction
        db.execute("INSERT into 'transaction' (user, stock, no_shares, shares_cost, purchase_price, buy_sell, date) VALUES (?, ?, ?, ?, ?, ?, ?)", session["user_id"], request.form.get("symbol"), neg_shares, neg_price, stock_price['price'], "sell", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Update Summary database with the new shares and prices
        db.execute("UPDATE 'summary' SET shares = ?, market_price = ?, price = ? WHERE stock = ?", new_shares, stock_price['price'], new_price, request.form.get("symbol"))

        # Update the users Database to return their cash to available funds
        avail_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        avail_cash = avail_cash[0]['cash'] + return_price
        db.execute("UPDATE users SET cash = ? WHERE id= ?", avail_cash, session["user_id"])

        return redirect("/")
    # User reached route via GET (as by clicking a link or via redirect)
    else:

        list_stocks = db.execute("SELECT * FROM 'summary'")

        return render_template("sell.html", list_stocks=list_stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
