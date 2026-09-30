"""Exact interface used by the demonstration, with ordinary floating arithmetic."""
def mean_squared_error(rows, slope, intercept):
    return sum((y - (slope * x + intercept)) ** 2 for x, y in rows) / len(rows)
