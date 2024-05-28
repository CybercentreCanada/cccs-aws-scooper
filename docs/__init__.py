try:
    with open("docs/__version__", "r") as f:
        VERSION = f.readline().rstrip()
except FileNotFoundError:
    with open("../../docs/__version__", "r") as f:
        VERSION = f.readline().rstrip()
