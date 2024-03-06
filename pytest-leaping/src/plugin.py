from collections import defaultdict
import os
import sys
import signal
import threading
from types import CodeType

import pexpect

from simpletracer import SimpleTracer
import subprocess
from gpt import GPT
from _pytest.runner import runtestprotocol
import os
import time
from models import FunctionCallNode, VariableAssignmentNode


def pytest_configure(config):
    leaping_option = config.getoption('--leaping')
    if not leaping_option:
        return
    config.option.capture = 'no'  # setting the -s flag
    config.addinivalue_line("filterwarnings", "ignore")


def pytest_addoption(parser):
    group = parser.getgroup('leaping')
    group.addoption(
        '--leaping',
        action='store_true',
        default=False,
        help='Enable Leaping for failed tests'
    )

    parser.addini('HELLO', 'Dummy pytest.ini setting')




project_dir = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], encoding='utf-8').strip()
tracer = SimpleTracer(project_dir)


def monitor_call_trace(code: CodeType, instruction_offset: int):
    global tracer

    func_name = code.co_name

    if tracer and tracer.test_name in func_name or (tracer and tracer.stack_size > 0):
        leaping_specific_files = [
            "conftest",
            "gpt",  # TODO: maybe make this LEAPING_ or something less likely to run into collisions
        ]
        if os.path.abspath(code.co_filename).startswith(
                tracer.project_dir) and "<" not in code.co_filename and "<" not in code.co_name and not any(
            file in code.co_filename for file in leaping_specific_files):
            tracer.call_stack_history.append((code.co_filename, func_name, "CALL", tracer.stack_size))
            tracer.stack_size += 1


def monitor_return_trace(code: CodeType, instruction_offset: int, retval: object):
    global tracer

    if tracer and tracer.stack_size > 0 and os.path.abspath(code.co_filename).startswith(
            tracer.project_dir) and "<" not in code.co_filename and "<" not in code.co_name and "conftest" not in code.co_filename:
        tracer.call_stack_history.append((code.co_filename, code.co_name, "RETURN", tracer.stack_size))
        tracer.stack_size -= 1


def pytest_runtest_setup(item):
    global tracer

    tracer.test_name = item.name
    tracer.test_start = time.time()

    sys.monitoring.use_tool_id(3, "Tracer")

    if tracer.scope:
        sys.settrace(tracer.simple_tracer)
    else:
        sys.monitoring.register_callback(3, sys.monitoring.events.PY_START, monitor_call_trace)
        sys.monitoring.register_callback(3, sys.monitoring.events.PY_RETURN, monitor_return_trace)

    sys.monitoring.set_events(3, sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN)


def pytest_runtest_teardown(item, nextitem):
    sys.settrace(None)
    sys.monitoring.free_tool_id(3)


error_context_prompt = """I got an error. Here's the trace:

{}

Here's the source code that we got the trace from:

{}

If you are certain about the root cause, describe it as tersely as possible, in a single sentence. Don't start the sentence with 'The root cause of the error is', just say what it is."""


def pytest_runtest_makereport(item, call):
    # leaping_option = item.config.getoption('--leaping')
    # if not leaping_option:
    #     return
    global tracer

    if call.excinfo is not None:
        error_type, error_message, traceback = call.excinfo._excinfo

        tracer.error_type = error_type
        tracer.error_message = error_message
        tracer.traceback = traceback


def build_call_hierarchy(trace_data, function_to_source, function_to_call_mapping, function_to_assign_mapping,
                         function_to_deltas, function_to_call_args):
    file_name, func_name, event_type, _ = trace_data[0]
    root_call = FunctionCallNode(file_name, func_name, [])  # todo: can root level pytest functions have call args?
    stack = [root_call]

    counter_map = defaultdict(lambda: defaultdict(int))  # one function can get called multiple times throughout execution, so we keep an index to figure out which execution # we're at
    last_root_call_line = 0

    for trace_file_name, trace_func_name, event_type, depth in trace_data[1:]:
        key = (stack[-1].file_name, stack[-1].func_name)

        if event_type == 'CALL':  # strategy here is to create VariableAssignmentObjects for all the lines up to the current call
            call_mapping = function_to_call_mapping[key]

            line_nos = function_to_call_mapping[key][trace_func_name]

            if line_nos:
                line_no = line_nos[0]
                remaining_line_nos = line_nos[1:]
                call_mapping[trace_func_name] = remaining_line_nos
                if not remaining_line_nos and key == (file_name, func_name):  # this means we are the last call within the root function
                    last_root_call_line = line_no  # save that line

                assignments = function_to_assign_mapping[key]

                assignments_to_add_line_nos = set()
                for assignment_line_no in assignments.keys():
                    if assignment_line_no < line_no:
                        assignments_to_add_line_nos.add(assignment_line_no)

                for assignment_line_no in assignments_to_add_line_nos:
                    for ast_assignment in assignments[assignment_line_no]:
                        var_name = ast_assignment.name
                        value = None
                        delta_list = function_to_deltas[key][assignment_line_no]
                        if not delta_list:  # todo: what does this mean
                            continue 
                        delta_index = counter_map[key][assignment_line_no]  
                        if delta_index >= len(delta_list):
                            continue
                        deltas = delta_list[delta_index]
                        for runtime_assignment in deltas: 
                            if runtime_assignment.name == var_name:
                                value = runtime_assignment.value

                        if value:
                            counter_map[key][assignment_line_no] += 1
                            context_line = function_to_source[key].split("\n")[assignment_line_no  - 1].strip()
                            stack[-1].children.append(VariableAssignmentNode(var_name, value, context_line))

            call_args_list = function_to_call_args[(trace_file_name, trace_func_name)]
            if call_args_list:
                new_call = FunctionCallNode(trace_file_name, trace_func_name, call_args_list.pop(0))
            else:
                new_call = FunctionCallNode(trace_file_name, trace_func_name, [])

            stack[-1].children.append(new_call)
            stack.append(new_call)
        elif event_type == 'RETURN':
            stack.pop()


    # here we add the last variable variable assignments in the root func that happen after the last function call within root
    key = (file_name, func_name)
    assignments = function_to_assign_mapping[key]
    assignments_to_add_line_nos = set()
    for assignment_line_no in assignments.keys():
        if assignment_line_no > last_root_call_line:
            assignments_to_add_line_nos.add(assignment_line_no)

    for assignment_line_no in assignments_to_add_line_nos:
        for ast_assignment in assignments[assignment_line_no]:
            var_name = ast_assignment.name
            value = None
            if not function_to_deltas[key][assignment_line_no]:
                continue
            deltas = function_to_deltas[key][assignment_line_no][0]  # should be precisely one since root func should only get called once
            for runtime_assignment in deltas: 
                if runtime_assignment.name == var_name:
                    value = runtime_assignment.value

            if value:
                context_line = function_to_source[key].split("\n")[assignment_line_no  - 1].strip()
                stack[-1].children.append(VariableAssignmentNode(var_name, value, context_line))


    # here we are adding the erroring line to the trace
    traceback = tracer.traceback
    while traceback.tb_next:
        traceback = traceback.tb_next
    frame = traceback.tb_frame
    file_path = frame.f_code.co_filename
    func_name = frame.f_code.co_name
    line_no = frame.f_lineno - frame.f_code.co_firstlineno + 1
    source_code = tracer.function_to_source[(file_path, func_name)]
    error_context_line = source_code.split("\n")[line_no - 1].strip()
    root_call.children.append(VariableAssignmentNode(tracer.error_type, tracer.error_message, error_context_line))

    return root_call


def output_call_hierarchy(nodes, output, indent=0):
    last_index = len(nodes) - 1
    for index, node in enumerate(nodes):
        branch_prefix = "    "
        if indent > 0:
            branch_prefix = "|   " * (indent - 1) + ("+--- " if index < last_index else "\\--- ")

        if isinstance(node, FunctionCallNode):
            formatted_args = ", ".join([arg.name + "=" + arg.value for arg in node.call_args])
            line = f"{branch_prefix}Function: {node.func_name}({formatted_args})"  # todo: maybe differentiate between def func and func(), since one means we are expanding inline, the second means we're not going further
            output.append(line)
            output_call_hierarchy(node.children, output, indent + 1)
        elif isinstance(node, VariableAssignmentNode):
            line = f"{branch_prefix}{node.context_line}  # {node.var_name}: {node.value}"
            output.append(line)


def generate_suggestion(gpt: GPT):
    global tracer

    root = build_call_hierarchy(tracer.call_stack_history, tracer.function_to_source, tracer.function_to_call_mapping,
                                tracer.function_to_assign_mapping, tracer.function_to_deltas, tracer.function_to_call_args)
    output = []
    output_call_hierarchy([root], output)

    source_text = ""

    for key in tracer.scope:
        func_source = None
        if key in tracer.method_to_class_source:
            func_source = tracer.method_to_class_source[key]
        else:
            func_source = tracer.function_to_source[key]

        if func_source:
            source_text += func_source + "\n\n"

    prompt = error_context_prompt.format("\n".join(output), source_text)

    gpt.add_message("user", prompt)
    response = gpt.chat_completion()

    return response


# Before re-running failed test, need to add scope information to tracer so that we can instrument the re-run
def add_scope():
    global tracer

    scope = set()

    for file_name, func_name, call_type, depth in tracer.call_stack_history:
        if call_type != "RETURN" and depth < 4:
            scope.add((file_name, func_name))

    tracer.call_stack_history = []  # reset stack history since we are re-running test
    tracer.scope = scope


def launch_cli():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))  # let the os pick a port
    sock.listen(1)
    port = sock.getsockname()[1]


    def handle_output(sock):
        connection, client_address = sock.accept()
        gpt = GPT("gpt-4-0125-preview", 0.5)
        initial_message = generate_suggestion(gpt)
        connection.sendall(initial_message.encode('utf-8'))
        exit_command_received = False
        while not exit_command_received:
            data = connection.recv(2048)
            if data == b'exit':
                exit_command_received = True
            if data == b"get_traceback":
                connection.sendall(b"some-traceback-string")
            user_input = data.decode('utf-8')
            gpt.add_message("user", user_input)
            response = gpt.chat_completion()
            connection.sendall(response.encode('utf-8'))

        connection.close()

    thread = threading.Thread(target=handle_output, args=(sock,))
    thread.start()

    child = pexpect.spawn(f"leaping --port {port}")
    child.interact()

    thread.join()
    sock.close()


def pytest_runtest_protocol(item, nextitem):
    leaping_option = item.config.getoption('leaping')
    if not leaping_option:
        return
    reports = runtestprotocol(item, nextitem=nextitem, log=False)

    test_failed = any(report.failed for report in reports if report.when == 'call')

    tracer.test_duration = time.time() - tracer.test_start
    tracer.test_start = None

    if test_failed:
        add_scope()
        runtestprotocol(item, nextitem=nextitem, log=False)
        launch_cli()

    for report in reports:
        item.ihook.pytest_runtest_logreport(report=report)

    return True


def is_application_code(file_path, project_root=None):
    file_path = os.path.abspath(file_path)
    project_root = os.path.abspath(project_root)

    if "opt/homebrew" in file_path:
        return False

    if file_path.startswith(project_root):
        return True

    python_lib_paths = [os.path.join(p, "site-packages") for p in sys.path] + [
        os.path.join(p, "dist-packages") for p in sys.path
    ]

    if "site-packages" in file_path:
        return False

    return not any(
        file_path.startswith(os.path.abspath(lib_path))
        for lib_path in python_lib_paths
    )


def my_tracer(frame, event, arg=None):
    if not is_application_code(frame.f_code.co_filename, os.getcwd()):
        return

    code = frame.f_code

    # extracts calling function name
    func_name = code.co_name

    # extracts the line number
    line_no = frame.f_lineno
    file_name = code.co_filename

    return my_tracer
