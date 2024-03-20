from leaping_models import ExecutionCursor, CallStack, ASTAssignment, RuntimeAssignment
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


def create_ast_mapping(parsed_ast, assign_mapping, call_mapping):
    def process_node(node):
        if isinstance(node, ast.arguments):
            for arg in node.args:
                assign_mapping[arg.lineno].append(ASTAssignment(name=arg.arg, deps=[]))

        elif isinstance(node, ast.Assign):
            assignee = node.targets[0]
            if isinstance(assignee, ast.Name):
                variables = [n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)]
                assign_mapping[node.lineno].append(ASTAssignment(name=assignee.id, deps=variables))

        elif isinstance(node, ast.AugAssign) or isinstance(node, ast.AnnAssign):
            assign_mapping[node.lineno].append(ASTAssignment(name=node.target.id, deps=[]))

        elif isinstance(node, ast.Return):
            variables = []
            if node.value:
                variables = [n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)]
            assign_mapping[node.lineno].append(ASTAssignment(name="return", deps=variables))

        elif isinstance(node, ast.Call):
            if hasattr(node.func, 'id'):  # Direct calls
                call_mapping[node.func.id].append(node.lineno)
            elif hasattr(node.func, 'attr'):  # Method calls
                call_mapping[node.func.attr].append(node.lineno)

    for node in ast.walk(parsed_ast):
        process_node(node)


def get_mapping_from_source(source):
    parsed_ast = ast.parse(source).body[0]

    assign_mapping = defaultdict(list)  # line number -> list of assigns
    call_mapping = defaultdict(list)  # function name -> list of line numbers
    create_ast_mapping(parsed_ast, assign_mapping, call_mapping)
    return assign_mapping, call_mapping


def get_function_source_from_frame(frame, method_to_class_source):
    func_name = frame.f_code.co_name
    source_code = None

    if func_name in frame.f_globals:
        source_code = inspect.getsource(frame.f_globals[func_name])
    else:  # deal with methods that are not part of global scope, so we have to look at instance methods of self, where self is in the local scope
        if 'self' in frame.f_locals:
            cls = frame.f_locals['self'].__class__
            if hasattr(cls, func_name):
                method = getattr(cls, func_name)
                source_code = inspect.getsource(method)
                method_to_class_source[(frame.f_code.co_filename, func_name)] = inspect.getsource(cls)

    if not source_code:
        return

    dedented_source = textwrap.dedent(source_code)
    return dedented_source


class SimpleTracer:
    def __init__(self):
        self.project_dir = ""
        self.call_stack = CallStack()
        self.test_name = None
        self.test_start = None
        self.test_duration = None
        self.function_to_assign_mapping = defaultdict(list)
        self.function_to_call_mapping = defaultdict(list)
        self.function_to_deltas = defaultdict(list)
        self.function_to_call_args = defaultdict(list)
        self.function_to_source = {}
        self.method_to_class_source = {}
        self.filename_to_path = {}
        self.error_message = ""
        self.error_type = ""
        self.traceback = None
        self.call_stack_history = []
        self.stack_size = 0
        self.scope = set()
        self.scope_list = []
        self.line_counter = defaultdict(int)
        self.monitoring_possible = False

    def simple_tracer(self, frame, event: str, arg):
        if frame.f_code.co_filename not in self.filename_to_path:
            self.filename_to_path[frame.f_code.co_filename] = os.path.abspath(frame.f_code.co_filename)
        current_file = self.filename_to_path[frame.f_code.co_filename]

        if frame.f_code.co_filename[0] == "<":
            return
        if current_file.endswith("plugin.py") or current_file.endswith("models.py") or current_file.endswith(
                "simpletracer.py"):  # todo: change conftest to be in a diff folder to filter out better
            return

        if (".pyenv" in current_file) or ("site-packages" in current_file):
            return

        if not self.monitoring_possible and self.scope and (current_file, frame.f_code.co_name) not in self.scope:
            return

        if not current_file.startswith(self.project_dir):
            return


        self.process_events(frame, event, arg)

        return self.simple_tracer

    def process_events(self, frame, event, arg):
        file_path = frame.f_code.co_filename
        func_name = frame.f_code.co_name

        if event == "line":
            line_no = frame.f_lineno

            key = (file_path, func_name, line_no)
            if self.line_counter[key] > 10:
                # heuristic to stop tracking deltas once we've hit a line more than 10 times
                # should clear this dictionary if the functions gets called again separately (clear cache in 'call' event)
                # todo: 10 is arbitrary, might be tricks to produce a better number
                return

            self.line_counter[key] += 1

            if (file_path, func_name) not in self.function_to_source.keys():  # if we haven't yet gotten the source/ast parsed the function
                
                source = get_function_source_from_frame(frame, self.method_to_class_source)

                if source:
                    self.function_to_source[(file_path, func_name)] = source

                    assign_mapping, call_mapping = get_mapping_from_source(
                        source)  # through the AST parsing of the source code, get map of assignments and calls by line number

                    if assign_mapping:  # dict of line_no -> list of ASTAssignment objects
                        self.function_to_assign_mapping[(file_path, func_name)] = assign_mapping
                    if call_mapping:  # dict of the name of a function being called -> list of line_no (since a function can be called at multiple lines within the same function)
                        self.function_to_call_mapping[(file_path, func_name)] = call_mapping

            relative_line_no = line_no - frame.f_code.co_firstlineno

            current_frame = self.call_stack.current_frame()

            prev_locals = current_frame.f_locals if current_frame else []
            curr_locals = frame.f_locals

            deltas: list[RuntimeAssignment] = get_deltas(prev_locals, curr_locals)

            delta_map = defaultdict(lambda: defaultdict(list))

            for delta in deltas:
                delta_map[delta.name][relative_line_no].append(delta.value)

            if self.function_to_deltas[(file_path, func_name)][-1] == "NEW":
                self.function_to_deltas[(file_path, func_name)][-1] = delta_map
            else:
                last_map = self.function_to_deltas[(file_path, func_name)][-1]
                for var_name, line_delta_list in delta_map.items():
                    if var_name not in last_map:
                        last_map[var_name] = line_delta_list
                    else:
                        for key, val in line_delta_list.items():
                            last_map[var_name][key].extend(val)

                self.function_to_deltas[(file_path, func_name)][-1] = last_map

            cursor = self.create_cursor(file_path, frame)
            self.call_stack.new_cursor_in_current_frame(cursor)

        if event == "call":
            if self.monitoring_possible:
                self.stack_size += 1
                self.call_stack_history.append((file_path, func_name, "CALL", self.stack_size))
            arg_deltas: list[RuntimeAssignment] = get_deltas([],
                                                             frame.f_locals)  # these deltas represent the parameters at the start of a function
            if arg_deltas:
                self.function_to_call_args[(file_path, func_name)].append(arg_deltas)

            cursor = self.create_cursor(file_path, frame)
            self.call_stack.enter_frame(cursor)

            self.function_to_deltas[(file_path, func_name)].append("NEW")

        if event == "return":
            self.stack_size -= 1
            if self.monitoring_possible:
                self.call_stack_history.append((file_path, func_name, "RETURN", self.stack_size))
            self.call_stack.exit_frame()

    def create_cursor(self, file_path, frame):
        cursor = ExecutionCursor(file_path, frame.f_lineno, frame.f_code.co_name, frame.f_locals)
        return cursor

    def get_variable_history(self, variable_name, file_path, func_name, first_line_no, max_depth=1, current_depth=0):
        if current_depth > max_depth:
            return ""

        history = ""
        # todo: change this once we actually use variable history
        for line_no, deltas in self.function_to_deltas.get((file_path, func_name), {}).items():
            for delta in deltas:
                if delta.name == variable_name:
                    line = None
                    with open(file_path) as f:
                        line = f.readlines()[first_line_no + line_no - 2].strip()

                    history += f"At line '{line}' in {func_name}, '{delta.name}' was set to {delta.value}"

                    if current_depth < max_depth:
                        for dep in self.get_variable_dependencies(variable_name, file_path, func_name):
                            history += self.get_variable_history(dep, file_path, func_name, max_depth,
                                                                 current_depth + 1)

        return history

    def get_variable_dependencies(self, variable_name, file_path, func_name):
        dependencies = []
        for _, mappings in self.function_to_assign_mapping.get((file_path, func_name), {}).items():
            for mapping in mappings:
                if mapping.name == variable_name:
                    dependencies.extend(mapping.deps)
        return dependencies
