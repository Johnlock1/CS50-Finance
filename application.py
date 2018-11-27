from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():

    # store the stocks owned by current user, grouped by symbol
    # and ordering them by ascessing order.
    # columns are stock's symbol, name and sum of shares
    stocks = db.execute("SELECT \
                            symbols.symbol, \
                            symbols.name, \
                            SUM(transactions.shares) AS shares\
                        FROM \
                            transactions \
                            JOIN symbols ON transactions.symbolid = symbols.id \
                        WHERE \
                            transactions.userid = :id \
                        GROUP BY \
                            symbols.symbol \
                        HAVING \
                            SUM(transactions.shares) > 0\
                        ORDER BY \
                            symbols.symbol ASC",
                        id=session.get("user_id"))

    # for total stock value calculation
    stocks_value = 0

    # add to stocks current stock price and total value per stock
    for stock in stocks:
        stock["price"] = (lookup(stock["symbol"]).get("price"))
        stock["total"] = stock["shares"] * stock["price"]
        stocks_value += stock["total"]
        stock["price"] = usd(stock["price"])
        stock["total"] = usd(stock["total"])

    # store current's user cash
    cash = db.execute("SELECT users.cash \
                        FROM users \
                        WHERE users.id = :id",
                      id=session.get("user_id"))

    return render_template("index.html", total=usd(stocks_value + cash[0]["cash"]), stocks=stocks, cash=usd(cash[0]["cash"]))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # save inputs into variables
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # ensure symbol was submitted
        if not symbol:
            return apology("missing symbol")

        # ensure shares were submitted
        elif not shares:
            return apology("missing shares")

        # lookup symbol
        quote = lookup(symbol)

        # ensure sumbol is valid
        if not quote:
            return apology("invalid symbol")

        # ensure shares is a positive integer
        elif not shares.isnumeric() or not int(shares) > 0:
            return apology("invalid shares")

        # see how much cash user has
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session.get("user_id"))

        #username=db.execute("SELECT username FROM users WHERE id = :id", id=session.get("user_id"))

        # ensure user can afford transaction
        if float(shares) * float(quote.get("price")) > float(cash[0]["cash"]):
            return apology("can't afford")
        # add transaction to database
        else:

            # check if symbol exists to symbols table
            result = db.execute("SELECT id FROM symbols WHERE symbol = :symbol",
                                symbol=quote.get("symbol"))

            # if symbol exists store its id
            if len(result) == 1:
                symbolid = result[0]["id"]

            # add symbol to symbols table
            else:
                db.execute("INSERT INTO symbols (symbol, name) \
                            VALUES (:symbol, :name)",
                           symbol=quote.get("symbol"), name=quote.get("name"))

                result = db.execute("SELECT id FROM symbols WHERE symbol = :symbol",
                                    symbol=quote.get("symbol"))
                symbolid = result[0]["id"]

            # add transaction to transactions table
            db.execute("INSERT INTO transactions \
                        (userid, symbolid, price, shares) \
                        VALUES \
                        (:userid, :symbolid, :price, :shares)",
                       userid=session.get("user_id"),
                       symbolid=symbolid,
                       price=quote.get("price"),
                       shares=int(shares))

        # update user's cash
        db.execute("UPDATE users SET cash = cash - :cash WHERE id = :id",
                   cash=(float(shares) * float(quote.get("price"))),
                   id=session.get("user_id"))

        # redirect user to home page with alert message
        flash("Bought!")
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions."""

    # get all users transactions
    stocks = db.execute("SELECT \
                            symbols.symbol, \
                            transactions.shares, \
                            transactions.price, \
                            transactions.time \
                        FROM \
                            transactions \
                            JOIN symbols ON transactions.symbolid = symbols.id \
                        WHERE \
                            transactions.userid = :id \
                        ORDER BY \
                            transactions.time ASC",
                        id=session.get("user_id"))

    for stock in stocks:
        stock["price"] = usd(stock["price"])

    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username!")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        # ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol")

        # lookup symbol
        quote = lookup(request.form.get("symbol"))

        # ensure sumbol is valid
        if not quote:
            return apology("invalid symbol")

        return render_template("quoted.html",
                               name=quote.get("name"),
                               symbol=quote.get("symbol"),
                               price=usd(quote.get("price")))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""

    username = request.form.get("username")
    password = request.form.get("password")
    password_confirmation = request.form.get("confirm password")

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not username:
            return apology("must provide username")

        # ensure password was submitted
        elif not password:
            return apology("must provide password")

        # ensure password and confirm password match
        if password != password_confirmation:
            return apology("passwords don't match")

        # insert username and password into database
        result = db.execute("INSERT INTO users (username, hash) \
                            VALUES (:username, :hash)",
                            username=username,
                            hash=pwd_context.hash(password))

        # if db.execute fails, return apology
        if not result:
            return apology("username is being used")

        # remember which user has logged in
        session["user_id"] = result

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # save inputs into variables
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # ensure symbol was submitted
        if not symbol:
            return apology("missing symbol")

        # ensure shares were submitted
        elif not shares:
            return apology("missing shares")

        # get current's user porfolio
        stocks = db.execute("SELECT \
                            symbols.symbol, \
                            symbols.id, \
                            SUM(transactions.shares) AS shares\
                        FROM \
                            transactions \
                            JOIN symbols ON transactions.symbolid = symbols.id \
                        WHERE \
                            transactions.userid = :id \
                            AND symbols.symbol = :symbol",
                            id=session.get("user_id"),
                            symbol=lookup(symbol).get("symbol"))

        # ensure user owns the stock
        if not stocks:
            return apology("symbol not own")

        # ensure valid number or shares
        elif not shares.isnumeric() or int(shares) < 0:
            return apology("invalid shares")

        # ensure user owns enough stock
        elif int(shares) > stocks[0]["shares"]:
            return apology("too many shares")

        # get symbol id and username
        symbolid = stocks[0]["id"]

        # add transaction to transactions table
        db.execute("INSERT INTO transactions (userid, symbolid, price, shares) \
                    VALUES (:userid, :symbolid, :price, :shares)",
                   userid=session.get("user_id"),
                   symbolid=symbolid,
                   price=lookup(symbol).get("price"),
                   shares=-int(shares))

        # update user's cash
        db.execute("UPDATE users SET cash = cash + :cash WHERE id = :id",
                   cash=(float(shares) * float(lookup(symbol).get("price"))),
                   id=session.get("user_id"))

        # redirect user to home page with alert message
        flash("Sold!")
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html")


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    # get user's username
    user = db.execute("SELECT * FROM users WHERE id = :id", id=session.get("user_id"))

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide old password")

        # ensure password was submitted
        elif not request.form.get("new password"):
            return apology("must provide new password")

        # ensure username exists and password is correct
        if not pwd_context.verify(request.form.get("password"), user[0]["hash"]):
            return apology("invalid password")

        # ensure password and confirm password match
        if request.form.get("new password") != request.form.get("confirm new password"):
            return apology("new passwords don't match")

        # update password
        db.execute("UPDATE users SET hash = :hash WHERE id = :id",
                   hash=pwd_context.hash(request.form.get("new password")),
                   id=user[0]["id"])

        # redirect user to profile
        flash("Password updated!")
        return redirect(url_for("profile"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("profile.html", username=user[0]["username"])
