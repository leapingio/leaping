from types import CodeType
from simpletracer import SimpleTracer, get_function_source_from_frame
import sys
import subprocess
import ast
from gpt import GPT
from _pytest.runner import runtestprotocol
import os

class SymbolExtractor(ast.NodeVisitor):
    def __init__(self):
        self.symbols = set()
        self.assigned_symbols = set() 

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.assigned_symbols.add(target.id)
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id not in self.assigned_symbols:
            self.symbols.add(node.id)
        self.generic_visit(node)


project_dir = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], encoding='utf-8').strip()
tracer = SimpleTracer(project_dir)


def monitor_call_trace(code: CodeType, instruction_offset: int):
    global tracer

    func_name = code.co_name

    if "test_failure" in func_name or (tracer and tracer.stack_size > 0):
        if os.path.abspath(code.co_filename).startswith(tracer.project_dir) and "<" not in code.co_filename and "<" not in code.co_name and "conftest" not in code.co_filename:
            tracer.call_stack_history.append((code.co_filename, func_name, "CALL", tracer.stack_size))
            tracer.stack_size += 1


def monitor_return_trace(code: CodeType, instruction_offset: int, retval: object):
    global tracer

    if tracer and tracer.stack_size > 0 and os.path.abspath(code.co_filename).startswith(tracer.project_dir) and "<" not in code.co_filename and "<" not in code.co_name and "conftest" not in code.co_filename:
        tracer.call_stack_history.append((code.co_filename, code.co_name, "RETURN", tracer.stack_size))
        tracer.stack_size -= 1


def pytest_runtest_setup(item):
    global tracer

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


error_context_prompt = """There was an '{}' when executing '{}' in the following function:

{}

Here's the history of the relevant variables to this error:

{}

You have two options:
1. If you are certain about the root cause, describe the fix in as short of a declarative sentence as possible.
2. If you need more variable history, output the value of a variable name, and NOTHING else."""


def pytest_runtest_makereport(item, call):
    global tracer

    if call.excinfo is not None:
        error_type, error_message, traceback = call.excinfo._excinfo

        tracer.error_type = error_type
        tracer.error_message = error_message
        tracer.traceback = traceback    


def generate_suggestion():
    global tracer

    traceback = tracer.traceback
    while traceback.tb_next:
        traceback = traceback.tb_next

    frame = traceback.tb_frame

    file_path = frame.f_code.co_filename
    func_name = frame.f_code.co_name
    line_no = frame.f_lineno - frame.f_code.co_firstlineno + 1

    breakpoint()
    source = tracer.function_to_source[(file_path, func_name)]

    line = None
    with open(file_path) as f:
        line = f.readlines()[frame.f_lineno-1].strip()

    tree = ast.parse(line)
    extractor = SymbolExtractor()
    extractor.visit(tree)
    error_symbols = extractor.symbols
    error_symbol = error_symbols.pop() # todo: there can definitely be multiple but let's assume one for now
    history_message = tracer.get_variable_history(error_symbol, file_path, func_name, frame.f_code.co_firstlineno)
    source = get_function_source_from_frame(frame)
    prompt = error_context_prompt.format(error_type, line, source, history_message)
    gpt = GPT("gpt-4-0125-preview", 0.5)
    gpt.add_message("user", prompt)
    response = gpt.chat_completion()


# Before re-running failed test, need to add scope information to tracer so that we can instrument the re-run
def add_scope():
    global tracer

    scope = set()

    for file_name, func_name, call_type, depth in tracer.call_stack_history:
        if call_type != "RETURN" and depth < 4:
            scope.add((file_name, func_name))

    tracer.scope = scope


def pytest_runtest_protocol(item, nextitem):
    reports = runtestprotocol(item, nextitem=nextitem, log=False)

    test_failed = any(report.failed for report in reports if report.when == 'call')

    if test_failed:
        add_scope()
        runtestprotocol(item, nextitem=nextitem, log=False)
        response = generate_suggestion() # todo: log message somewhere, what about back and forth in shell?

    for report in reports:
        item.ihook.pytest_runtest_logreport(report=report)

    return True
