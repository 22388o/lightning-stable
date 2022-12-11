from time import time

def timestamp() -> int:
    return int(time())

def percentage(x: float, y: float) -> float:
    return (x * y / 100)
