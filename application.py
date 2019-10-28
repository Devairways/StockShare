import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

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
    portfolio = db.execute("select symbol,shares,price from shares where id = :id", id=session.get("user_id"))
    cash = db.execute("select cash from users where id = :id", id=session.get("user_id"))[0]["cash"]
    pricelist = list()
    total = cash
    for i in portfolio:
        quote = lookup(i["symbol"])
        money = i["shares"] * i["price"]
        total += money
        quote["money"] = usd(money)
        pricelist.append(quote)
    return render_template("index.html", pricelist=pricelist, portfolio=portfolio, cash=usd(cash), total=usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        id = session.get("user_id")
        symbol = request.form.get("symbol").upper()
        if not request.form.get("shares").isdigit():
            return apology("insert valid number", 400)
        n = int(request.form.get("shares"))
        cash = db.execute("select cash from users where id = :id", id=id)
        stock = db.execute("select * from shares where id = :id and  symbol = :symbol", id=id, symbol=symbol)
        quote = lookup(request.form.get("symbol"))
        if quote:
            if not cash[0]["cash"] - (quote["price"] * float(n)) <= 0:
                db.execute("update users set cash = :cash where id = :id", cash=(
                           cash[0]["cash"] - (quote["price"] * float(n))), id=id)
                historylist(id, "buy", n, symbol, quote["price"])
                if stock:
                    db.execute("update shares set shares = shares +:shares where id = :id and  symbol = :symbol",
                               shares=int(n), symbol=symbol, id=session.get("user_id"))
                else:
                    db.execute("insert into shares(id,shares,symbol,price) values (:id,:shares,:symbol,:price)",
                               id=id, shares=n, symbol=quote["symbol"], price=quote["price"])
            cash = db.execute("select cash from users where id = :id", id=id)
            return redirect("/")
    """Buy shares of stock"""
    return apology("none existent stock")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    if db.execute("select username from users where username=:username", username=username):
        return jsonify(False)
    return jsonify(True)


@app.route("/history")
@login_required  # zorgt ervoor dat de route protected is dus als een gebruiker niet is ingelogd redirect hij automatisch naar login
def history():
    history = db.execute("select * from history where id = :id ", id=session.get("user_id"))
    if history:
        return render_template("history.html", history=history)
    return apology("TODO")


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
    if request.method == "GET":
        return render_template("quote.html")
    else:
        quote = lookup(request.form.get("symbol"))
        if not quote:
            return apology("sorry not valid symbol", 400)
        else:
            quote["price"] = usd(quote["price"])
            return render_template("quoted.html", quote=quote)
    return apology("TODO", 400)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password") or not request.form.get("password") == request.form.get("confirmation"):
            return apology("must provide password", 400)
        elif db.execute("select username from users where username=:username", username=request.form.get("username")):
            return apology("username already exists", 400)
        else:
            # Query database for username
            rows = db.execute("insert into users (username, hash) values(:username, :password)",
                              username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))
            return redirect("/")

    """Register user"""
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    id = session.get("user_id")
    if request.method == "GET":
        stocks = db.execute("select symbol from shares where id = :id", id=id)
        return render_template("sell.html", stocks=stocks)
    else:
        n = int(request.form.get("shares"))
        symbol = request.form.get("symbol").upper()
        print("this is the symbol", symbol)
        if not symbol or n < 0:
            return apology("please fill in correctly", 400)
        stockOwned = db.execute("select shares from shares where id = :id and symbol = :symbol", id=id, symbol=symbol)[0]["shares"]
        quote = lookup(request.form.get("symbol"))
        if quote and stockOwned >= n:
            db.execute("update users set cash = cash + :cash where id = :id", cash=(quote["price"] * float(n)), id=id)
            historylist(id, "sell", n, symbol, quote["price"])
            if stockOwned == n:
                db.execute("delete from shares where id = :id and symbol = :symbol", symbol=symbol, id=id)
            else:
                db.execute("update shares set shares = shares - :shares where id = :id and symbol = :symbol",
                           shares=n, symbol=symbol, id=id)
            return redirect("/")
    return apology("Not enough shares of that stock")


@app.route("/reset", methods=["POST"])
@login_required
def reset():
    id = session.get("user_id")
    if id:
        db.execute("update users set cash = :cash where id = :id", cash=int(request.form.get("money")), id=id)
        return redirect("/")
    return apology("Not sure what happened:(")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)\



def historylist(id, action, shares, symbol, price):
    if id:
        db.execute("insert into history(id, action, shares, symbol, price) values (:id, :action, :shares, :symbol, :price)",
                   id=id, action=action, shares=shares, symbol=symbol, price=price)
        return True
    else:
        return False