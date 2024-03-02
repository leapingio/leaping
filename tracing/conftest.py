from simpletracer import SimpleTracer, get_function_source_from_frame
import sys
import subprocess
import ast
from gpt import GPT

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


tracer = None


def pytest_runtest_setup(item):
    global tracer

    project_dir = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], encoding='utf-8').strip()

    tracer = SimpleTracer(project_dir)
    sys.settrace(tracer.simple_tracer)

def pytest_runtest_teardown(item, nextitem):
    sys.settrace(None)

error_context_prompt = """There was an '{}' when executing '{}' in the following function:

{}

Here's the history of the relevant variables to this error:

{}

You have two options:
1. If you are certain about the root cause, describe the fix to solve the root cause in as short of a declarative sentence as possible.
2. If you need more variable history, output the value of a variable name, and NOTHING else."""


def pytest_runtest_makereport(item, call):
    if call.excinfo is not None:
        error_type, error_message, traceback = call.excinfo._excinfo

        while traceback.tb_next:
            traceback = traceback.tb_next

        frame = traceback.tb_frame

        file_path = frame.f_code.co_filename
        func_name = frame.f_code.co_name
        line_no = frame.f_lineno - frame.f_code.co_firstlineno + 1

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

        # response = gpt.chat_completion()