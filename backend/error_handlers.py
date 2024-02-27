import re
from backend.source_code_analyzer import seen_files
import builtins
from backend.code_modifier import CodeSnippet, FileModifier
from backend.utils import get_error


def handle_name_error(output, source_code_analyzer, imports, script_path, step):
    line_number_pattern = r"line (\d+)"

    line_number_match = re.findall(line_number_pattern, output, re.DOTALL)

    if line_number_match:
        line_number = line_number_match[-1]

    variable_pattern = r"NameError: name '(\w+)' is not defined"

    variable_match = re.search(variable_pattern, output, re.DOTALL)

    if variable_match:
        variable_name = variable_match.group(1)

    if var_import := imports.get(
        variable_name
    ):  # return early if we find it in the import dict
        modifier = FileModifier(script_path)  # TODO: unhardcode this
        prev_snippet = CodeSnippet(0, 0, [])
        modifier.delete_and_insert(
            prev_snippet,
            CodeSnippet(start_line=0, end_line=1, new_lines=[var_import]),
            step,
        )
        seen_files.add(script_path)
        return var_import

    filename_pattern = r'File "(.*)", line \d+'

    filename_matches = re.findall(filename_pattern, output)

    if filename_matches:
        filename = filename_matches[-1]

    # THIS CAN ALSO BE A statement, not just a function
    try:
        (
            function_text,
            start,
            _,
        ) = source_code_analyzer.get_function_text_containing_line(
            filename, int(line_number) - 1
        )
    except:
        (
            function_text,
            start,
            _,
        ) = source_code_analyzer.get_statement_text_containing_line(
            filename, int(line_number) - 1
        )

    relative_number = (
        int(line_number) - start[0] - 1
    )  # relative to where the fn starts, figure out why I needed to add one

    modifier = FileModifier(
        script_path
    )  # TODO: unhardcode this, this should be a const - with the abs path

    modifier.delete_and_insert(
        CodeSnippet(0, 0, []),
        CodeSnippet(
            start_line=0, end_line=1, new_lines=[f"from example import {variable_name}"]
        ),
        step,
    )

    return


def handle_error(
    result,
    modifier,
    imports,
    source_code_analyzer,
    script_path,
    socket_wrapper,
    original_exception_type,
    original_exception_message,
    step,
):
    error_types = [
        err
        for err in dir(builtins)
        if isinstance(getattr(builtins, err), type)
        and issubclass(getattr(builtins, err), BaseException)
    ]

    stderr = result.stderr

    if not stderr:
        return "no_error", result.stdout

    error = get_error(stderr)

    if not error:
        return stderr

    _, exception_type, exception_message = get_error(stderr)

    for error in error_types:
        if error in stderr:
            formatted_error = f"{exception_type + ': ' + exception_message}"
            if error == "ImportError":
                socket_wrapper.notify_frontend_of_print(
                    "Fixing {} error.".format(formatted_error), step
                )
                modifier.insert_at_line(CodeSnippet(0, 1, imports[""]))
                return
            elif error == "NameError":
                socket_wrapper.notify_frontend_of_print(
                    "Fixing imports...".format(formatted_error), step, "imports"
                )
                handle_name_error(
                    result.stderr, source_code_analyzer, imports, script_path, step
                )
                return

            if (
                exception_type == original_exception_type
                and exception_message == original_exception_message
            ):
                socket_wrapper.notify_frontend_of_print(
                    "Looks like we got that {} error we were trying to reproduce!".format(
                        formatted_error
                    ),
                    step,
                )
                return "same_error"

            return stderr
