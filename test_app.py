import pandas
import math

def add(a, b):
    return a + b

def divide(a, b):
    return a / 0   # division by zero error

def square_root(x):
    return math.squareroot(x)  # wrong function name

def load_data():
    df = pandas.read_csv("data.csv")  # file does not exist
    return df
