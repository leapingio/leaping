import builtins
import re


def get_error(traceback):
    error_types = [
        err
        for err in dir(builtins)
        if isinstance(getattr(builtins, err), type)
        and issubclass(getattr(builtins, err), BaseException)
    ]

    lines = []
    error_line = None
    for line in traceback.split("\n"):
        if "^^^" in line:
            continue
        lines.append(line.strip())
        for error in error_types:
            if error in line:
                error_line = line.strip()
                break
        if error_line:
            break

    if not error_line:
        return

    exception_type, exception_message = [x.strip() for x in error_line.split(":", 1)]

    frame_pattern = r'File "(?P<filepath>.+)", line (?P<lineno>\d+), in (?P<func>.+)'

    stack = []

    for idx, line in enumerate(lines):
        frame = re.match(frame_pattern, line)
        if not frame:
            continue
        file_path = frame.group("filepath")
        lineno = frame.group("lineno")
        func = frame.group("func")
        context = lines[idx + 1].strip()

        stack.append(
            {
                "filename": file_path,
                "function": func,
                "lineno": int(lineno),
                "context": context,
            }
        )

    return stack, exception_type, exception_message


def analyze_source(failing_line, file_path, source_code_analyzer):
    tree = source_code_analyzer.construct_function_tree(file_path, failing_line)
    imports = source_code_analyzer.get_all_imports(file_path)

    return tree, imports
