from simpletracer import SimpleTracer
import sys
import subprocess

tracer = None

def pytest_sessionstart(session):
    global tracer

    project_dir = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], encoding='utf-8').strip()

    tracer = SimpleTracer(project_dir)
    sys.settrace(tracer.simple_tracer)

def pytest_sessionfinish(session, exitstatus):
    sys.settrace(None)

def pytest_runtest_makereport(item, call):
    if call.excinfo is not None:
        error_type, error_message, traceback = call.excinfo._excinfo
        

        for (file_path, func_name), mappings in tracer.function_to_mapping.items(): 
            print(file_path, func_name)
            for line_no, ast_assignments in mappings.items():
                print(line_no, ast_assignments)

        for (file_path, func_name), lines in tracer.function_to_deltas.items():
            print(file_path, func_name)
            for line_no, deltas in lines.items():
                print(line_no)
                for delta in deltas:
                    print(delta)


