import json
import subprocess
import time
from backend.editor_socket_wrapper import EditorSocketWrapper
from backend.error_handlers import handle_error
from backend.lsp import LspClientWrapper
from backend.source_code_analyzer import SourceCodeAnalyzer
from backend.source_code_analyzer import seen_files
from backend.github_helper import GitHubHelper
from backend.code_matcher import CodeMatcher
from .utils import analyze_source, get_error
from .code_modifier import CodeSnippet, FileModifier
from .gpt import LLMWrapper
import re
import os


def change_code(
    modifier, response, step, socket_wrapper, file_path="backend/scratch.py"
):
    try:
        old_code_pattern = "<old_code>(.*?)</old_code>"
        old_code = re.findall(old_code_pattern, response, re.DOTALL)[0]
    except Exception:
        old_code = None

    new_code_pattern = "<new_code>(.*?)</new_code>"
    try:
        new_code = re.findall(new_code_pattern, response, re.DOTALL)[0]
    except Exception as e:
        print("No new code tags:", response)

    if not old_code and new_code:
        with open("backend/scratch.py", "a") as f:
            num_lines = len(modifier.current_lines)
            if ";" in new_code:
                lines = new_code.split(";")
            else:
                lines = new_code.split("\n")
            for idx, line in enumerate(lines):
                f.write(line + "\n")
                socket_wrapper.notify_frontend_of_insert(
                    num_lines + idx, line, step, idx == len(lines) - 1
                )
        return

    comparator = CodeMatcher(set([file_path]))
    best_fit = comparator.find_best_match(old_code)

    split = None
    if "\\n" in new_code:
        split = new_code.split("\\n")
    else:
        split = new_code.split("\n")

    new_code_snippet = CodeSnippet(
        best_fit.start_line, best_fit.last_line, split
    )
    old_snippet = CodeSnippet(
        best_fit.start_line, best_fit.last_line, old_code.split("\n")
    )
    modifier = FileModifier(file_path)
    modifier.delete_and_insert(old_snippet, new_code_snippet, step)

    # now get and send the explanation
    explanation_pattern = "<explanation>(.*?)</explanation>"
    matches = re.findall(explanation_pattern, response, re.DOTALL)
    if not matches:
        explanation = response.split("<old_code>")[0].strip()
    else:
        explanation = "LLM: " + re.findall(explanation_pattern, response, re.DOTALL)[0]

    socket_wrapper.notify_frontend_of_print(explanation, step, "explanation")


def add_source_code_to_gpt(gpt, func, source_code, socket_wrapper, step):
    socket_wrapper.notify_frontend_of_print(f"Getting the source for '{func}'...", step)
    source_code_info = f"Source code of {func} is: {source_code}"
    gpt.add_message("user", source_code_info, "source_code_info")


system_prompt = """You are a brilliant and meticulous engineer investigating a runtime error in a python environment. Here's the error: 

{}

Here's the script:

{}

Here's the application source code:

{}


You are only allowed to modify code at the end of the file, such as the print statement. You are only allowed to make function calls from the source snippet I will give you. Your goal is to reproduce the error. You are permitted to modify a code snippet, but the new snippet should only have one additional line. Give a concise one sentence explanation of why you're making that change, and then the change itself, strictly following the following format.

<explanation>Your one sentence explanation here</explanation>
<code_change>
    <old_code>old code</old_code>
    <new_code>new code</new_code>
<code_change> 

In each subsequent step I will run the script again with your change and tell you what the output was. Do not output anything besides the tags above and the content inside of them. We will continue this process until we experience the same error.
"""

same_error_prompt = """I just ran the script and we are indeed getting the same error and traceback as the original runtime error. 
As briefly as you can, can you explain the root cause of this bug? Please pay careful attention to not just identify what the symptom, but go a level deeper and figure out why the data is in an incorrect format. 
"""

no_error_prompt = """There was no error, and the script printed out {}. We still need to reproduce the AttributeError, so please add or modify a function call following this format again:

<explanation>Your one sentence explanation here</explanation>
<code_change>
    <old_code>old code</old_code>
    <new_code>new code</new_code>
<code_change>
"""
no_error_no_output_prompt = """No output. We still need to reproduce the AttributeError, so please add or modify a function call following this format again:

<explanation>Your one sentence explanation here</explanation>
<code_change>
    <old_code>old code</old_code>
    <new_code>new code</new_code>
<code_change>
"""

unrelated_error_prompt = """The script errored out with this:

{}

The error comes from a change you've made, so fix the error by modifying one of the lines you've already added following this format again:

<explanation>Your one sentence explanation here</explanation>
<code_change>
    <old_code>old code</old_code>
    <new_code>new code</new_code>
<code_change>
"""


def change_code(
    modifier, response, step, socket_wrapper, file_path="backend/scratch.py"
):
    try:
        old_code_pattern = "<old_code>(.*?)</old_code>"
        old_code = re.findall(old_code_pattern, response, re.DOTALL)[0]
    except Exception:
        old_code = None

    new_code_pattern = "<new_code>(.*?)</new_code>"
    new_code = re.findall(new_code_pattern, response, re.DOTALL)[0]

    if not old_code and new_code:
        with open("backend/scratch.py", "a") as f:
            num_lines = len(modifier.current_lines)
            lines = new_code.split("\n")
            for idx, line in enumerate(lines):
                f.write(line)
                socket_wrapper.notify_frontend_of_insert(
                    num_lines + idx, line, step, idx == len(lines) - 1
                )
        return

    comparator = CodeMatcher(set([file_path]))
    best_fit = comparator.find_best_match(old_code)

    new_code_snippet = CodeSnippet(
        best_fit.start_line, best_fit.last_line, new_code.split("\n")
    )
    old_snippet = CodeSnippet(
        best_fit.start_line, best_fit.last_line, old_code.split("\n")
    )
    modifier = FileModifier(file_path)
    modifier.delete_and_insert(old_snippet, new_code_snippet, step)

    # now get and send the explanation
    explanation_pattern = "<explanation>(.*?)</explanation>"
    matches = re.findall(explanation_pattern, response, re.DOTALL)
    explanation = ""
    if not matches:
        explanation = response.split("<old_code>")[0].strip()
    else:
        explanation = "GPT: " + re.findall(explanation_pattern, response, re.DOTALL)[0]

    socket_wrapper.notify_frontend_of_print(explanation, step, "explanation")


def run(socket_wrapper: EditorSocketWrapper, traceback: str):
    stack, exception_type, exception_message = get_error(traceback)

    step = 0

    lsp_wrapper = LspClientWrapper(os.getcwd())
    lsp_wrapper.initialize()
    source_code_analyzer = SourceCodeAnalyzer(lsp_wrapper)

    complete_function_tree, imports = analyze_source(
        118,
        stack[1]["filename"],
        source_code_analyzer,  # todo: fix line number
    )

    script_path = "backend/scratch.py"

    gpt = LLMWrapper("gpt-4-0125-preview", 0.5, socket_wrapper)

    seen_files.add(script_path)

    modifier = FileModifier(script_path, headless=False, socket_wrapper=socket_wrapper)

    first_func = stack[1]["function"]

    first_func_source_code = complete_function_tree[first_func].data.source_code

    prev_snippet = CodeSnippet(0, 0, [])
    new_lines = first_func_source_code.split("\n") + ["\n", f"print({first_func}())"]

    new_snippet = CodeSnippet(0, len(new_lines), new_lines)
    modifier.delete_and_insert(prev_snippet, new_snippet, step)

    with open("backend/example.py") as f:
        source_code = f.read()

    gpt.add_message(
        "system",
        system_prompt.format(traceback, "\n".join(modifier.current_lines), source_code),
        step,
        "system_prompt",
    )

    result = subprocess.run(["python3", script_path], capture_output=True, text=True)

    while True:
        step += 1

        if command := socket_wrapper.check_for_fe_commands():
            command = json.loads(command)
            if command["type"] == "pause":
                resume_command_received = False
                while not resume_command_received:
                    command = socket_wrapper.check_for_fe_commands()
                    if not command:
                        continue
                    command = json.loads(command)
                    if command["type"] == "resume":
                        resume_command_received = True
                    if command["type"] == "context":
                        step = command["step"]
                        modifier.current_lines = modifier.history[step]
                        gpt.messages = gpt.messages[: gpt.step_to_message[step]]
                        additional_context = command["additionalContext"]
                        gpt.add_message(
                            "user", additional_context, step, "additional_user_context"
                        )
            if command["type"] == "context":
                step = command["step"]
                modifier.current_lines = modifier.history[step]
                gpt.messages = gpt.messages[: gpt.step_to_message[step]]
                additional_context = command["additionalContext"]
                gpt.add_message(
                    "user", additional_context, step, "additional_user_context"
                )
            if command == "stop":
                return

        output = handle_error(
            result,
            modifier,
            imports,
            source_code_analyzer,
            script_path,
            socket_wrapper,
            exception_type,
            exception_message,
            step,
        )

        if output:  # if import error or nameerror, don't need to message GPT
            if output == "same_error":
                break

            elif len(output) == 2:  # no error
                prompt = None
                if output[1]:
                    prompt = no_error_prompt.format(output[1])

                else:
                    prompt = no_error_no_output_prompt
                no_error_prompt.format(output[1])

                gpt.add_message("user", prompt, step, "no_error")

            else:  # unrelated error
                error = unrelated_error_prompt.format(
                    output,
                )
                socket_wrapper.notify_frontend_of_print("Unrelated error:", step)
                socket_wrapper.notify_frontend_of_print(output, step, "error")
                gpt.add_message("user", error, step, "unrelated_error")

            response = gpt.chat_completion(step)

            if response == "Over limit":
                return

            change_code(modifier, response, step, socket_wrapper)

        else:
            step -= 1

        result = subprocess.run(
            ["python3", script_path], capture_output=True, text=True
        )

        socket_wrapper.notify_frontend_of_print(
            "Running code again...", step, format="running"
        )

        result = subprocess.run(
            ["python3", script_path], capture_output=True, text=True
        )
    gpt.add_message(
        "user",
        same_error_prompt,
        step,
        "same_error",
    )
    # response = gpt.chat_completion(step)
    # print(response)

    why = """
    I am going to recursively ask you 'why?' to your previous answers, unless you deem that the answer you've provided is axiomatic, or no longer is hypothesizing about the code. 
    For example, if you talk about the inattention of an engineer, or the laws of the universe, you are done. If that's the case, respond with <done>. In all other cases, I ask you this of your previous answer: why?"
    """

    step += 1
    i = 0
    repro = []
    repro.append(
        """The root cause of the bug is that the `result` variable, which is expected to hold the result of a database query for a leave day, is `None`. This happens because there's no record in the `leave_day` table matching the criteria of the query for the employee ID and the specific day ('2024-02-29'). 

The absence of a matching record in `leave_day` is likely due to the logic in the `create_leave_days` function, which is supposed to populate this table. On closer inspection, the issue stems from the handling of dates when inserting leave days. Specifically, there's a problem with how the function increments the date and checks for the end of the month. This logic might not correctly handle leap years, such as 2024, or there might be an issue with how the end of the month is determined and how the date is incremented. 

Additionally, the `create_leave_days` function assumes every day as a weekend (with `is_weekend` set to 1 in the insert statement), which is incorrect logic but not directly related to the `NoneType` error. The correct approach should involve determining if a day is actually a weekend based on the date.
"""
    )
    repro.append(
        """The immediate error is due to the lack of a null check before accessing `result.is_weekend`. However, the deeper issue lies in the data insertion logic in `create_leave_days`, which fails to insert the required record for '2024-02-29', possibly due to incorrect date handling, especially considering leap years and month-end logic.
The reason the `result` variable can become `None` and lead to an `AttributeError` when attempting to access `result.is_weekend` is because the query to the `leave_day` table may not find a matching record for the given employee ID and day. This situation can occur due to several reasons:

1. **Incorrect Date Handling in Data Insertion:** If the `create_leave_days` function does not correctly handle leap years or end-of-month logic when inserting records into the `leave_day` table, it might skip inserting a record for certain dates, such as February 29 in a leap year (like 2024).

2. **Assumption of Every Day as a Weekend:** The function inserts every day as a weekend (`is_weekend` set to 1), which is not the cause of the `NoneType` error but indicates potential logic issues in determining whether a day is a weekend or not. This could affect business logic elsewhere but does not directly result in the absence of a record.
    """
    )
    repro.append(
        """Now, why might the `create_leave_days` function not handle leap years or end-of-month logic correctly?
The `create_leave_days` function might not handle leap years or end-of-month logic correctly due to a misunderstanding or oversight regarding how Python's `datetime` objects manage date arithmetic, specifically in relation to incrementing days across month and year boundaries. This includes the special case of leap years, where February has 29 days instead of the usual 28.

1. **Leap Year Oversight:** Handling leap years requires specific logic because they add an extra day to February. The code must account for this to correctly increment dates around the end of February in a leap year. Failure to do so can lead to missing or incorrect data for February 29th.

2. **End-of-Month Logic:** Properly incrementing a date across the end of a month involves adjusting both the day and month components of a `datetime` object, and potentially the year at the end of December. If the logic does not correctly handle these transitions, it could skip days or insert data with incorrect dates.

Both of these issues could stem from a lack of familiarity with Python’s `datetime` module capabilities or from an underestimation of the complexity of date arithmetic. Date and time handling is a common source of bugs in software development due to its inherent complexity and the variety of special cases, such as leap years and time zones.

Developing robust date-handling logic requires careful consideration of these edge cases and thorough testing to ensure correctness. The oversight in handling these cases might not be due to a lack of effort but rather the subtlety and complexity of date arithmetic, which can easily lead to errors if not meticulously managed.

Why might there be a misunderstanding or oversight in handling date arithmetic, specifically regarding leap years and end-of-month transitions?
    """
    )
    while i < 3:
        step += 1
        socket_wrapper.notify_frontend_of_print(repro[i], step)
        step += 1
        socket_wrapper.notify_frontend_of_print("Can you explain why that is?", step)
            
        i += 1

    # while "<done>" not in response and step < 15:
    #     step += 1
    #     gpt.add_message("user", why, step, "root_cause")
    #     response = gpt.chat_completion(step)
    #     if "<done" not in response:
    #         socket_wrapper.notify_frontend_of_print(response, step)
    #     print(response)

    step += 1
    gpt.add_message(
        "user",
        "With this root cause in mind, please suggest a fix that will fix the root cause of the error"
        "Please format all of your code changes in the format, with an explanation of the change. Only use python "
        "code, DO NOT use &gt; if you're trying to compare values, use the pythonic '>' instead. Please add an import statement for all of the external"
        "libraries that you are using"
        "<explanation>Your one sentence explanation here</explanation>"
        "<code_change>"
        "   <old_code>old code</old_code>"
        "   <new_code>new code</new_code>"
        "</code_change>",
        step,
        "fixes",
    )

    socket_wrapper.notify_frontend_of_print("Generating fix...", step) 

    fix = gpt.chat_completion(step)

    socket_wrapper.notify_frontend_of_print(fix, step)

    change_code(modifier, fix, step, socket_wrapper, file_path="backend/example.py")

    socket_wrapper.notify_frontend_of_print("Running code...", step)

    result = subprocess.run(["python3", script_path], capture_output=True, text=True)

    socket_wrapper.notify_frontend_of_print("Code ran with no errors!", step)

    github_helper = GitHubHelper()
    github_helper.create_branch_and_push()
    
    pr_url = github_helper.create_pull_request("leapingio", "demo")
    socket_wrapper.notify_frontend_of_print(f"A PR has been opened with the changes: {pr_url}", step+1)
