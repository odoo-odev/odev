def sizeof(num, suffix="B"):
    """
    Formats a number to its human readable representation in bytes-units.
    """
    for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
        if abs(num) < 1024.0:
            return "{:3.1f} {unit}{suffix}".format(num, unit=unit, suffix=suffix)
        num /= 1024.0
    return "{:.1f} Y{suffix}".format(num, suffix=suffix)
