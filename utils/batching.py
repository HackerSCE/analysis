def unique_preserve_order(values):
    seen = set()
    unique_values = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def batch_values(values, batch_size):
    values = list(values)
    for index in range(0, len(values), batch_size):
        yield values[index:index + batch_size]
