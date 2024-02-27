import sqlite3
from datetime import datetime
from fastapi import FastAPI


class DB:
    def __init__(self, db_path: str = ":memory:"):
        self.conn: sqlite3.Connection = sqlite3.connect(db_path)
        self.cursor: sqlite3.Cursor = self.conn.cursor()
        self.setup()

    def setup(self):
        self.cursor.execute(
            """
        CREATE TABLE employee (
            id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT
        )
        """
        )
        self.cursor.execute(
            """
        CREATE TABLE leave_request (
            id INTEGER PRIMARY KEY,
            emp_id INTEGER,
            start DATE NOT NULL,
            end DATE NOT NULL
        )
        """
        )
        self.cursor.execute(
            """
        CREATE TABLE leave_day (
            id INTEGER PRIMARY KEY,
            emp_id INTEGER,
            day DATE,
            is_weekend BOOL
        )
        """
        )
        self.conn.commit()

    def insert_one(self, statement):
        self.cursor.execute(statement)
        return self.cursor.lastrowid

    def fetchone(self, query):
        self.cursor.execute(query)
        return self.cursor.fetchone()


class DB2:
    def __init__(self):
        pass

    def fetchone(self):
        return


DAYS_PER_MONTH = {
    1: 31,
    2: 28,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}

db = DB()
app = FastAPI()


@app.get("/create_emp")
def create_emp(first_name, last_name):
    statement = f"INSERT INTO employee (first_name, last_name) VALUES ('{first_name}', '{last_name}')"
    emp_id = db.insert_one(statement)
    return emp_id


def create_leave_days(emp_id, start, end):
    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d")

    curr_date = start_date
    while curr_date <= end_date:
        curr_date_string = curr_date.strftime("%Y-%m-%d")
        statement = f"INSERT INTO leave_day (emp_id, day, is_weekend) VALUES ({emp_id}, '{curr_date_string}', 1)"
        db.insert_one(statement)
        _, month, day = curr_date_string.split("-") 
        curr_date = curr_date.replace(day = int(day)+1)
        if curr_date.day > DAYS_PER_MONTH[curr_date.month]:
            curr_date = curr_date.replace(day=1).replace(month=int(month)+1)


@app.get("/create_leave_request")
def create_leave_request(emp_id, start, end):
    statement = f"INSERT INTO leave_request (emp_id, start, end) VALUES ({emp_id}, '{start}', '{end}')"
    db.insert_one(statement)
    create_leave_days(emp_id, start, end)


def pay_for_employees(day):
    ees = db.query("Select id for employees")
    for ee in ees:
        pay_for_day(ee, day)


@app.get("/pay_for_day")
def pay_for_day(emp_id, day_string):
    day = datetime.strptime(day_string, "%Y-%m-%d")
    query = f"""
    SELECT * FROM leave_request
    WHERE emp_id = {emp_id} AND start <= '{day}' AND end >= '{day}'
    """
    leave_request = db.fetchone(query)
    if leave_request:
        query = f"SELECT day, is_weekend FROM leave_day WHERE emp_id = {emp_id} AND day = '{day}'"
        result = db.fetchone(query)
        if result.is_weekend:
            return 100
    else:
        return 200
