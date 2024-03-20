import collections
from copy import copy

allowed_types = [int, str, float, dict, type(None), bool]


def can_trace_type(variable):
    current_type = type(variable)
    if current_type in allowed_types:
        return True

    return False

class ExecutionCursor:
    function_name: str
    file: str
    line: int
    f_locals: list

    def __init__(self, file: str, line: int, function_name: str, f_locals):
        self.function_name = function_name
        self.file = file
        self.line = line
        self.f_locals = f_locals


class StackFrame:
    # parent: StackFrame
    def __init__(self, parent, file, line: int, function_name: str, f_locals: list):
        self.parent = parent
        self.file = file
        self.line = line
        self.function_name = function_name
        self.f_locals = f_locals

    @classmethod
    def new(cls, parent, execution_cursor: ExecutionCursor):
        return StackFrame(parent, execution_cursor.file, execution_cursor.line, execution_cursor.function_name, execution_cursor.f_locals)

    @classmethod
    def clone(cls, origin):
        if not origin:
            return StackFrame.empty()
        return StackFrame(origin.parent, origin.file, origin.line, origin.function_name, origin.f_locals)

    @classmethod
    def empty(cls):
        return StackFrame(None, None, None, None, None)


class CallStack:
    def __init__(self):
        self.stack = collections.deque()

    def enter_frame(self, execution_cursor: ExecutionCursor):
        parent_frame = self.get_parent_frame()
        frame = StackFrame.new(parent_frame, execution_cursor)
        self.stack.append(frame)

    def get_parent_frame(self):
        if len(self.stack) > 0:
            return self.stack[-1]
        return None

    def new_cursor_in_current_frame(self, new_cursor: ExecutionCursor):
        stack_frame: StackFrame = self.top_level_frame_as_clone()
        stack_frame.line = new_cursor.line
        stack_frame.file = new_cursor.file
        stack_frame.function_name = new_cursor.function_name
        stack_frame.f_locals = copy(new_cursor.f_locals)

        # line event. Pop top of stack if available and replace with new frame
        if len(self.stack) > 0:
            self.stack.pop()
            self.stack.append(stack_frame)
        else:
            self.stack.append(stack_frame)

    def exit_frame(self):
        self.stack.pop()

    def top_level_frame_as_clone(self):
        current: StackFrame = self.current_frame()
        return StackFrame.clone(current)

    def current_frame(self):
        frame = self.get_parent_frame()
        return frame
    

# name and dependencies of variable assignment derived from AST parsing
class ASTAssignment:
    def __init__(self, name, deps):
        self.name = name
        self.deps = deps

# variable update from sys.settrace
class RuntimeAssignment:
    def __init__(self, name, value, path):
        self.name = name
        self.value = value
        self.path = path # path inside python object


class VariableAssignmentNode:
    def __init__(self, var_name, value, context_line):  # todo: deal with object paths
        self.var_name = var_name
        self.value = value
        self.context_line = context_line


class FunctionCallNode:
    def __init__(self, file_name, func_name, call_args):
        self.file_name = file_name
        self.func_name = func_name
        self.call_args = call_args
        self.children = []
