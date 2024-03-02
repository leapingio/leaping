
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
                deltas.append(RuntimeAssignment(name=local, value=str(change), path=path))

        if local not in prev_locals:
            deltas.append(RuntimeAssignment(name=local, value=str(val), path=""))
    
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

            if type(assignee) == ast.Attribute:
                pass
            elif type(assignee) == ast.Subscript:
                pass
            elif type(assignee) == ast.Name:
                variables = get_variables_in_assign(node.value)

                # todo: What if lineno and end_lineno are different?
                mapping[node.lineno].append(ASTAssignment(name=assignee.id, deps=variables))

        elif type(node) == ast.Return:
            variables = get_variables_in_assign(node.value)
            mapping[node.lineno].append(ASTAssignment(name="return", deps=variables))


def get_mapping_from_source(source):
    parsed_ast = ast.parse(source).body[0]

    mapping = defaultdict(list)
    create_ast_mapping(parsed_ast, mapping)
    return mapping


def get_function_source_from_frame(frame):
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
    return dedented_source


class SimpleTracer:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.call_stack = CallStack()
        self.function_to_mapping = {}
        self.function_to_deltas = defaultdict(lambda: defaultdict(list))
        self.filename_to_path = {}

    def simple_tracer(self, frame, event: str, arg):
        if frame.f_code.co_filename not in self.filename_to_path:
            self.filename_to_path[frame.f_code.co_filename] = os.path.abspath(frame.f_code.co_filename)

        current_file = self.filename_to_path[frame.f_code.co_filename]

        if frame.f_code.co_filename[0] == "<":
            return

        if current_file.endswith("conftest.py"): # todo: change conftest to be in a diff folder to filter out better
            return

        if not current_file.startswith(self.project_dir):
            return
        
        self.process_events(frame, event, arg)

        return self.simple_tracer

    def process_events(self, frame, event, arg):
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

            source = get_function_source_from_frame(frame)
            mapping = get_mapping_from_source(source)

            if mapping:
                self.function_to_mapping[(file_path, func_name)] = mapping

            cursor = self.create_cursor(file_path, frame)
            self.call_stack.enter_frame(cursor)

        if event == "return":
            self.call_stack.exit_frame()

            cursor = self.create_cursor(file_path, frame)

    def create_cursor(self, file_path, frame):
        cursor = ExecutionCursor(file_path, frame.f_lineno, frame.f_code.co_name, frame.f_locals)
        return cursor
    
    def get_variable_history(self, variable_name, file_path, func_name, first_line_no, max_depth=1, current_depth=0):
        if current_depth > max_depth:
            return ""

        history = ""

        for line_no, deltas in self.function_to_deltas.get((file_path, func_name), {}).items():
            for delta in deltas:
                if delta.name == variable_name:
                    line = None
                    with open(file_path) as f:
                        line = f.readlines()[first_line_no + line_no - 2].strip()
                        
                    history += f"At line '{line}' in {func_name}, '{delta.name}' was set to {delta.value}"

                    if current_depth < max_depth:
                        for dep in self.get_variable_dependencies(variable_name, file_path, func_name):
                            history += self.get_variable_history(dep, file_path, func_name, max_depth, current_depth + 1)
                            
        return history

    def get_variable_dependencies(self, variable_name, file_path, func_name):
        dependencies = []
        for _, mappings in self.function_to_mapping.get((file_path, func_name), {}).items():
            for mapping in mappings:
                if mapping.name == variable_name:
                    dependencies.extend(mapping.deps)
        return dependencies
