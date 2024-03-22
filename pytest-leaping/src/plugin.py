import traceback
from collections import defaultdict
import sys
import threading
from types import CodeType

import pexpect

from simpletracer import SimpleTracer
import subprocess
from leaping_gpt import GPT
from _pytest.runner import runtestprotocol
import os
import time
from leaping_models import FunctionCallNode, VariableAssignmentNode
from _pytest.capture import MultiCapture
from posthog import Posthog

tracer = SimpleTracer()
in_server_mode = False

posthog = Posthog(project_api_key='phc_D109xSvTkwTKvxK65CE6TdIxjPoJLXnkVERctUrompz', host='https://app.posthog.com')
global_timestamp = time.time()


def pytest_configure(config):
    leaping_option = config.getoption('--leaping')
    if not leaping_option:
        return

    # Somewhere here, say that we're going into the hit our own server mode

    capture_manager = config.pluginmanager.getplugin('capturemanager')  # force the -s option
    if capture_manager._global_capturing is not None:
        capture_manager._global_capturing.pop_outerr_to_orig()
        capture_manager._global_capturing.stop_capturing()
        capture_manager._global_capturing = MultiCapture(in_=None, out=None, err=None)

    try:
        project_dir = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], encoding='utf-8').strip()
    except Exception:
        project_dir = str(config.rootdir)

    posthog.capture(global_timestamp, 'leaping_started')

    tracer.project_dir = project_dir

    config.addinivalue_line("filterwarnings", "ignore")


def pytest_addoption(parser):
    group = parser.getgroup('leaping')
    group.addoption(
        '--leaping',
        action='store_true',
        default=False,
        help='Enable Leaping for failed tests'
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--leaping'):
        return
    total_tests_collected = len(items)
    setattr(config, 'total_tests_collected', total_tests_collected)


def _should_trace(file_name: str, func_name: str) -> bool:
    leaping_specific_files = [
        "plugin",
        "leaping_models",
        "leaping_gpt",  # TODO: maybe make this LEAPING_ or something less likely to run into collisions
    ]
    if "<" in file_name:
        return False
    if any(leaping_specific_file in file_name for leaping_specific_file in leaping_specific_files):
        return False

    if (".pyenv" in file_name) or (".venv" in file_name) or ("site-packages" in file_name):
        return False

    if os.path.abspath(file_name).startswith(tracer.project_dir):
        return True
    return False


def monitor_call_trace(code: CodeType, instruction_offset: int):
    global tracer

    func_name = code.co_name

    if tracer and tracer.test_name in func_name or (tracer and tracer.stack_size > 0):
        if _should_trace(code.co_filename, func_name):
            tracer.call_stack_history.append((code.co_filename, func_name, "CALL", tracer.stack_size))
            tracer.stack_size += 1


def monitor_return_trace(code: CodeType, instruction_offset: int, retval: object):
    global tracer

    if tracer and tracer.stack_size > 0 and _should_trace(code.co_filename, code.co_name):
        tracer.call_stack_history.append((code.co_filename, code.co_name, "RETURN", tracer.stack_size))
        tracer.stack_size -= 1


def pytest_runtest_setup(item):
    if not item.config.getoption('--leaping'):
        return

    global tracer

    tracer.test_name = item.name
    tracer.test_start = time.time()

    if tracer.scope or tracer.monitoring_possible:
        sys.settrace(tracer.simple_tracer)
        return
    elif sys.version_info >= (3, 12):
        sys.monitoring.use_tool_id(3, "Tracer")
        sys.monitoring.register_callback(3, sys.monitoring.events.PY_START, monitor_call_trace)
        sys.monitoring.register_callback(3, sys.monitoring.events.PY_RETURN, monitor_return_trace)

        sys.monitoring.set_events(3, sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN)

    if sys.version_info < (3, 12):
        tracer.monitoring_possible = True


def pytest_runtest_teardown(item, nextitem):
    leaping_option = item.config.getoption('--leaping')
    if not leaping_option:
        return
    sys.settrace(None)
    if sys.version_info >= (3, 12):
        sys.monitoring.free_tool_id(3)


error_context_prompt = """I got an error. Here's the trace:

{}

Here's the source code that we got the trace from:

{}

If you are certain about the root cause, describe it as tersely as possible, in a single sentence. Don't start the sentence with 'The root cause of the error is', just say what it is.

In addition, please output the exact series of steps that occurred to get to the erroring state, with their associated places in code.

"""

test_passing_prompt = """The test passed. Here's the trace:
{}

Here's the source code that we got the trace from:
{}

Please output the exact series of steps that occurred to get to the passing state, with their associated places in code. For all questions that I ask going forward, please back up your claims 
with the exact series of steps that occurred to get to the state you are describing, with their associated places in code.
"""


def pytest_runtest_makereport(item, call):
    leaping_option = item.config.getoption('--leaping')
    if not leaping_option:
        return
    global tracer

    if call.excinfo is not None:
        error_type, error_message, traceback = call.excinfo._excinfo

        tracer.error_type = error_type
        tracer.error_message = error_message
        tracer.traceback = traceback


def add_deltas(tracer, key, stack, counter_map, line_no, greater_than=False):
    assignments = tracer.function_to_assign_mapping[key]  # all assignments in that function (which we got from AST parsing)

    assignments_to_add_line_nos = set()
    if not assignments:
        return
    
    # from ast assignemnt we get name and line number
    # from deltas we get name and line number + value
    # but sometimes the line numbers don't match, so do we even need the line number from the deltas?
    # well technically, the variable could show up multiple times at different lines so we need to still have a notion of ordering.
    # but even the ordering gets funky when we start talking about loops, for example
    # for ex, b only updates at the first line of the loop, so the ordering gets messed up.
    # i guess we can assume that if we take the line numbers for one variable, the order should be fine, and we can default to the closest line number

    for assignment_line_no in assignments.keys():
        if greater_than and assignment_line_no > line_no:  # when we want to get all the assignments after line_no
            assignments_to_add_line_nos.add(assignment_line_no)
        if not greater_than and assignment_line_no < line_no:  # when we want to get all the assignments before line_no
            assignments_to_add_line_nos.add(assignment_line_no)

    for assignment_line_no in assignments_to_add_line_nos:
        for ast_assignment in assignments[assignment_line_no]:  # all the ast assignments at that line number
            var_name = ast_assignment.name
            value = None
            delta_list = None
            if counter_map[key] < len(tracer.function_to_deltas[key]):
                delta_list = tracer.function_to_deltas[key][counter_map[key]]
            elif tracer.function_to_deltas[key]:  # this should only get hit to accomodate the case of last root function assignments (root call funcs should only be called once in an execution)
                delta_list = tracer.function_to_deltas[key][-1]

            if not delta_list:
                continue
                # deltas are runtime assignments, which means that since a function can get executed multiple times during an execution trace, we need to keep a
            # monotonically increasing counter (per function and per line number) to get the right deltas
            
            for runtime_assignment in delta_list:
                # This inner loop matches up static AST assignments with runtime deltas. We shouldn't need to have a loop, but would need to refactor some data structure.
                # Fine for now since there should rarely be more than one variable assignment per line
                if runtime_assignment == var_name:
                    value = delta_list[runtime_assignment][assignment_line_no]
                    if value:
                        break
                    else:  # line numbers don't match up between deltas and AST parsing, look for closest line number as heuristic for now
                        closest = float('inf')
                        for line_no, deltas in delta_list[runtime_assignment].items():
                            if not deltas:
                                continue
                            if abs(assignment_line_no - line_no) < abs(assignment_line_no - closest):
                                closest = line_no
                        value = delta_list[runtime_assignment][closest]
                        break

            if value:
                del delta_list[runtime_assignment][assignment_line_no]
                value_string = ""
                if len(value) > 1:
                    if len(value) > 5:
                        value_string = "Last 5 values in loop: [" + ", ".join(value[:5]) + "]"
                    else:
                        value_string = "Values in loop: [" + ", ".join(value) + "]"
                else:
                    value_string = value[0]

                context_line = tracer.function_to_source[key].split("\n")[assignment_line_no - 1].strip()
                if len(stack) != 0:
                    stack[-1].children.append(VariableAssignmentNode(var_name, value_string, context_line))


def build_call_hierarchy_interval(stack, trace_data, trace_data_index, file_name, func_name, function_to_call_mapping, function_to_call_args, counter_map):
    last_root_call_line = 0
    
    index = 0
    for index, (trace_file_name, trace_func_name, event_type, depth) in enumerate(trace_data[trace_data_index:]):  # sequence of "CALL" and "RETURN" calls gathered from sys.monitoring, representing execution trace
        if len(stack) == 0:
            break
        key = (stack[-1].file_name, stack[-1].func_name)

        if event_type == 'CALL':  # strategy here is to create VariableAssignmentObjects for all the lines up to the current call

            call_mapping = function_to_call_mapping[key]  # if there is no call mapping, probably out of scope

            if call_mapping and call_mapping[trace_func_name]:
                line_nos = call_mapping[trace_func_name]  # ascending list of line numbers where the function gets called (from AST parsing)
                line_no = line_nos[0]  # grab the first one
                remaining_line_nos = line_nos[1:]
                call_mapping[trace_func_name] = remaining_line_nos  # re-assign the rest of the line numbers to the dict such that next time this function gets called, we grab the next line number

                if not remaining_line_nos and key == (file_name, func_name):  # this means we are the last call within the root function, and we want to save that line number (see add_deltas call after end of loop)
                    last_root_call_line = line_no  # save that line

                add_deltas(tracer, key, stack, counter_map, line_no)  

            call_args_list = function_to_call_args[(trace_file_name, trace_func_name)]  # list of call args
            if call_args_list:
                new_call = FunctionCallNode(trace_file_name, trace_func_name, call_args_list.pop(0))  # pop off the first item from the list of call args such that next time the list is accessed we'll pop off the 2nd element
            else:
                new_call = FunctionCallNode(trace_file_name, trace_func_name, [])

            stack[-1].children.append(new_call)
            stack.append(new_call)

        elif event_type == 'RETURN':
            add_deltas(tracer, key, stack, counter_map, 0, greater_than=True)
            counter_map[key] += 1
            stack.pop()

    # add the last variable assignments in the root func that happen after the last function call within root
    add_deltas(tracer, (file_name, func_name), stack, counter_map, last_root_call_line, greater_than=True)

    return index


def build_call_hierarchy(tracer):
    trace_data = tracer.call_stack_history
    function_to_call_mapping = tracer.function_to_call_mapping
    function_to_call_args = tracer.function_to_call_args
    counter_map = defaultdict(int)  # one function can get called multiple times throughout execution, so we keep an index to figure out which execution number we're at

    trace_data_index = 0

    full_stack = []
    
    while trace_data_index < len(trace_data) - 1:
        file_name, func_name, event_type, _ = trace_data[trace_data_index]
        root_call = FunctionCallNode(file_name, func_name, [])  # todo: can root level pytest functions/fixtures have call args?
        stack = [root_call]

        trace_data_index += 1

        trace_data_index += build_call_hierarchy_interval(stack, trace_data, trace_data_index, file_name, func_name, function_to_call_mapping, function_to_call_args, counter_map)

        full_stack.append(root_call)

    # add the erroring line to the trace
    traceback = tracer.traceback
    if traceback:
        while traceback.tb_next:
            traceback = traceback.tb_next
        frame = traceback.tb_frame
        file_path = frame.f_code.co_filename
        func_name = frame.f_code.co_name
        line_no = frame.f_lineno - frame.f_code.co_firstlineno + 1
        try:
            source_code = tracer.function_to_source[(file_path, func_name)]
        except KeyError:  # we've likely hit library code
            return full_stack

        error_context_line = source_code.split("\n")[line_no - 1].strip()
        full_stack.append(VariableAssignmentNode(tracer.error_type, tracer.error_message, error_context_line))  # todo: this assume the error messages at the root pytest function call. is that true?

    return full_stack


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


def fetch_source(key):
    func_source = ""
    try:
        if key in tracer.method_to_class_source:
            func_source = tracer.method_to_class_source[key]
        else:
            func_source = tracer.function_to_source[key]
    except KeyError:
        pass

    return func_source


def generate_suggestion(gpt: GPT, test_failed: bool):
    global tracer
    root = build_call_hierarchy(tracer)
    output = []
    output_call_hierarchy(root, output)

    source_text = ""
    source_char_limit = 40000  # 10 cents
    seen_keys = set()
    if tracer.scope_list:
        for key in (tracer.scope_list[::-1]):
            if key not in seen_keys:
                func_source = fetch_source(key)
                if func_source:
                    source_text += func_source + "\n\n"
                    if len(source_text) > source_char_limit:
                        break
                seen_keys.add(key)
    else:  # case for < 3.12
        for file_path, func_name, _, _ in tracer.call_stack_history[::-1]:
            key = (file_path, func_name)
            if key not in seen_keys:
                func_source = fetch_source(key)
                if func_source:
                    source_text += func_source + "\n\n"
                    if len(source_text) > source_char_limit:
                        break
                seen_keys.add(key)


    if test_failed:
        output_string = ""

        num_tokens = sum([len(line) for line in output]) / 4      
        if num_tokens > 10000:  # $10 per million tokens, limit to 10 cents, so 10000 tokens max
            output_index_within_limit = len(output) - int(len(output) * 10000/num_tokens)
            output_string = "\n".join(output[output_index_within_limit:])
        else:
            output_string = "\n".join(output)

        prompt = error_context_prompt.format(output_string, source_text)
    else:
        prompt = test_passing_prompt.format("\n".join(output), source_text)

    gpt.add_message("user", prompt)
    return gpt.chat_completion(stream=True)


# Before re-running failed test, need to add scope information to tracer so that we can instrument the re-run
def add_scope():
    global tracer

    scope = []

    for file_name, func_name, call_type, depth in tracer.call_stack_history:
        if call_type != "RETURN":
            scope.append((file_name, func_name))

    tracer.call_stack_history = []  # reset stack history since we are re-running test
    tracer.scope_list = scope
    tracer.scope = set(scope)


def launch_cli(test_failed: bool):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))  # let the os pick a port
    sock.listen(1)
    port = sock.getsockname()[1]

    def handle_output(sock, child):
        connection, client_address = sock.accept()
        gpt = GPT("gpt-4-0125-preview", 0.5, in_server_mode)
        initial_message = generate_suggestion(gpt, test_failed)
        if traceback_obj := tracer.traceback:
            error_type = tracer.error_type
            error_message = tracer.error_message
            exception_str = "".join(traceback.format_exception_only(error_type, error_message))

            connection.sendall(b"\033[0mInvestigating the following error:\n")
            connection.sendall(f"{str(exception_str)} \n".encode('utf-8'))
        for chunk in initial_message:
            try:
                connection.sendall(chunk.encode('utf-8'))
            except BrokenPipeError:
                child.sendcontrol('c')  # Send Ctrl+C to the child process
                child.terminate(force=False)  # Try to gracefully terminate the child
                sys.exit(0)
        connection.sendall(b"LEAPING_STOP")

        exit_command_received = False
        while not exit_command_received:
            data = connection.recv(2048)
            if data == b'exit':
                break
            user_input = data.decode('utf-8')
            gpt.add_message("user", user_input)
            response = gpt.chat_completion(stream=True)
            for chunk in response:
                try:
                    connection.sendall(chunk.encode('utf-8'))
                except BrokenPipeError:
                    child.sendcontrol('c')  # Send Ctrl+C to the child process
                    child.terminate(force=False)  # Try to gracefully terminate the child
                    sys.exit(0)
            connection.sendall(b"LEAPING_STOP")

        connection.close()

    child = pexpect.spawn(f"leaping --port {port}")
    thread = threading.Thread(target=handle_output, args=(sock, child))
    thread.start()
    child.interact()
    thread.join()
    sock.close()


def pytest_runtest_protocol(item, nextitem):
    global tracer

    leaping_option = item.config.getoption('leaping')
    if not leaping_option:
        return
    reports = runtestprotocol(item, nextitem=nextitem, log=False)

    test_failed = any(report.failed for report in reports if report.when == 'call')

    if not test_failed and item.config.total_tests_collected > 1:  # Only run leaping on passing tests if explicitly requested
        return None

    tracer.test_duration = time.time() - tracer.test_start
    tracer.test_start = None
    add_scope()
    runtestprotocol(item, nextitem=nextitem, log=False)
    launch_cli(test_failed)

    for report in reports:
        item.ihook.pytest_runtest_logreport(report=report)

    return True
