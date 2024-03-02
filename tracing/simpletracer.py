
from models import ExecutionCursor, CallStack, ASTAssignment, RuntimeAssignment
import ast
import inspect
import textwrap
from collections import defaultdict
import os


def compare_objects(obj1, obj2, diffs, path="", depth=0):
    if depth > 2:
        return

    if not isinstance(obj1, type(obj2)):
        diffs.append((path, obj2))
        return

    if not hasattr(obj1, "__dict__") or not hasattr(obj2, "__dict__"):
        if hasattr(obj2, "__dict__"):
            diffs.append(path, obj2[path])
        elif not hasattr(obj1, "__dict__"):
            if obj1 != obj2:
                diffs.append((path, obj2))
            return

    obj1_dict, obj2_dict = obj1.__dict__, obj2.__dict__
    all_keys = set(obj1_dict.keys()) | set(obj2_dict.keys())

    for key in all_keys:
        new_path = (
            f"{path}.{key}" if path else key
        )  # todo: square brackets if array, list, or tuple. add validation that that's correct

        # todo: maybe have prev value as well

        if key not in obj1_dict:
            diffs.append((new_path, obj2_dict[key]))
        elif key not in obj2_dict:
            diffs.append((new_path, obj1_dict[key]))
        else:
            value1, value2 = obj1_dict[key], obj2_dict[key]

            compare_objects(value1, value2, diffs, new_path, depth + 1)


def get_deltas(prev_locals, curr_locals):
    deltas = []

    for local, val in curr_locals.items():
        if local in prev_locals:
            diffs = []
            compare_objects(prev_locals[local], val, diffs)
            if not diffs:
                continue
            for path, change in diffs:
                deltas.append(RuntimeAssignment(name=local, value=str(change), path=path, type="update"))

        if local not in prev_locals:
            deltas.append(RuntimeAssignment(name=local, value=str(val), path="", type="create"))
    
    return deltas


def create_ast_mapping(parsed_ast, mapping):

    def get_variables_in_assign(node):
        variables = []
        if type(node) == ast.Call:
            for arg in node.args:
                variables.extend(get_variables_in_assign(arg))
        elif type(node) == ast.BinOp:
            if hasattr(node.left, "id"):
                variables.append(node.left.id)
            if hasattr(node.right, "id"):
                variables.append(node.right.id)
            
        elif type(node) == ast.Name:
            if hasattr(node, "id"):
                variables.append(node.id)

        return variables

    for node in parsed_ast.body:
        if type(node) == ast.Assign:
            assignee = node.targets[0] # todo: deal with multi assign
            variables = get_variables_in_assign(node.value)

            # todo: What if lineno and end_lineno are different?
            mapping[node.lineno].append(ASTAssignment(name=assignee, deps=variables))

        elif type(node) == ast.Return:
            variables = get_variables_in_assign(node.value)
            mapping[node.lineno].append(ASTAssignment(name="return", deps=variables))


def get_function_assign_dep_mapping(frame):
    func_name = frame.f_code.co_name
    source_code = None

    if func_name in frame.f_globals:
        source_code = inspect.getsource(frame.f_globals[func_name])
    else:
        if 'self' in frame.f_locals:
            cls = frame.f_locals['self'].__class__
            if hasattr(cls, func_name):
                method = getattr(cls, func_name)
                source_code = inspect.getsource(method)
    
    if not source_code:
        return
    
    dedented_source = textwrap.dedent(source_code)
    parsed_ast = ast.parse(dedented_source).body[0]

    mapping = defaultdict(list)
    create_ast_mapping(parsed_ast, mapping)
    return mapping


class SimpleTracer:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.call_stack = CallStack()
        self.function_to_mapping = {}
        self.function_to_deltas = defaultdict(lambda: defaultdict(list))

    def simple_tracer(self, frame, event: str, arg):
        current_file = os.path.abspath(frame.f_code.co_filename)

        if current_file.startswith(self.project_dir):
            self.process_events(frame, event, arg)

        return self.simple_tracer

    def process_events(self, event: str, frame, arg):
        file_path = frame.f_code.co_filename
        func_name = frame.f_code.co_name

        current_frame = self.call_stack.current_frame()

        if event == "line":
            line_no = frame.f_lineno
            func_name = frame.f_code.co_name
            file_path = frame.f_code.co_filename

            relative_line_no = line_no - frame.f_code.co_firstlineno

            prev_locals = current_frame.f_locals if current_frame else []
            curr_locals = frame.f_locals
            
            deltas = get_deltas(prev_locals, curr_locals)
            if deltas:
                self.function_to_deltas[(file_path, func_name)][relative_line_no] = deltas

            cursor = self.create_cursor(file_path, frame)
            self.call_stack.new_cursor_in_current_frame(cursor)

        if event == "call":
            file_path = frame.f_code.co_filename
            func_name = frame.f_code.co_name

            self.function_to_mapping[(file_path, func_name)] = get_function_assign_dep_mapping(frame)

            cursor = self.create_cursor(file_path, frame)
            self.call_stack.enter_frame(cursor)

        if event == "return":
            self.call_stack.exit_frame()

            cursor = self.create_cursor(file_path, frame)

    def create_cursor(self, file_path_under_cursor, frame):
        cursor = ExecutionCursor(file_path_under_cursor, frame.f_lineno, frame.f_code.co_name, frame.f_locals)
        return cursor
