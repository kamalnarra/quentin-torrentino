# this prints a string in different colors
def pretty_print(str, color, **kwargs):
    if color == "red":
        print("\033[91m" + str + "\033[0m", **kwargs)
    elif color == "green":
        print("\033[92m" + str + "\033[0m", **kwargs)
    elif color == "yellow":
        print("\033[93m" + str + "\033[0m", **kwargs)
    elif color == "blue":
        print("\033[94m" + str + "\033[0m", **kwargs)
    elif color == "magenta":
        print("\033[95m" + str + "\033[0m", **kwargs)
    elif color == "cyan":
        print("\033[96m" + str + "\033[0m", **kwargs)
    elif color == "white":
        print("\033[97m" + str + "\033[0m", **kwargs)
    else:
        print(str)
