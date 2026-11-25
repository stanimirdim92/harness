def export_csv(session, rows):
    lines = [f"# token={session.token}"]
    lines += [",".join(map(str, row)) for row in list(rows)]
    return "\n".join(lines)
