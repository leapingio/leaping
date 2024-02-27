import dataclasses
from collections import defaultdict
from typing import Optional
from urllib.parse import unquote, urlparse, quote, urlunparse
from tree_sitter_languages import get_language
from tree_sitter import Parser
from backend.lsp import LspClientWrapper
import sys
from treelib import Node, Tree
import treelib
from pylspclient.lsp_structs import Position, Location
import os


seen_files = set()
visited_locations = set()  # TODO: move this into the class


@dataclasses.dataclass
class LeapingFunctionNode:
    name: str
    calling_func_line: int
    calling_func_col: int
    file_path: str
    source_code: str
    function_name: str
    start_line: int

    def __post_init__(self):
        seen_files.add(self.file_path)


@dataclasses.dataclass
class LocationCacheKey:
    uri: str
    line: int
    key: str

    def __init__(self, location: Location):
        self.uri = location.uri
        self.line = location.range.start.line
        self.key = f"{self.uri}:{self.line}"


@dataclasses.dataclass(frozen=True)
class VariableAssignment:
    variable_name: str
    line_no: int
    file_path: str

    def __gt__(self, other):
        return self.line_no > other.line_no


@dataclasses.dataclass(frozen=True)
class ClassBlueprint:
    declaration: str
    methods: Optional[list[str]]


class SourceCodeAnalyzer:
    def __init__(self, lsp_wrapper: LspClientWrapper = None):
        self.root_node = None
        self.parser = Parser()
        language = get_language("python")
        self.parser.set_language(language)
        self.call_stack = Tree()
        self.lsp_wrapper = lsp_wrapper
        # self.seen_files = set()

    def parse_file(self, file_path):
        with open(file_path, "rb") as file:
            source_code = file.read()
        return self.parser.parse(source_code)

    @staticmethod
    def find_function_containing_line(root_node, line_number):
        def find_node(node):
            if node.start_point[0] <= line_number <= node.end_point[0]:
                for child in node.children:
                    result = find_node(child)
                    if result is not None:
                        return result
                if node.type in ["function_definition", "method_definition"]:
                    return node
            return None

        return find_node(root_node)

    @staticmethod
    def find_nodes_at_line(root_node, line_number):
        target_line_index = line_number

        def find_node(node, parent=None):
            if node.start_point[0] <= target_line_index <= node.end_point[0]:
                for child in node.children:
                    result = find_node(child, node)
                    if result:
                        return result
                if node.start_point[0] == target_line_index:
                    return parent
            return None

        return find_node(root_node)

    def get_symbol_definition_at_line(
        self, file_path: str, line_number: int, symbol: str
    ):
        tree = self.parse_file(file_path)
        node = self.find_nodes_at_line(tree.root_node, line_number)
        for node in node.children:
            if not node.text.decode("utf-8").startswith(symbol):
                continue
            definition = self.lsp_wrapper.get_definition(
                file_path, Position(line_number, node.start_point[1])
            )
            if not definition:
                return None

            location: Location = definition[0]  # TODO: handle multiple definitions
            file_path = self.uri_to_file_path(location.uri)
            root_node = self.parse_file(file_path)
            node = self.find_nodes_at_line(
                root_node.root_node, location.range.start.line
            )

            return node.text.decode("utf-8")

    def find_all_children_of_type(self, node, type: str = "call"):
        call_nodes = []

        def recursive_search(current_node):
            if current_node.type == type:
                call_nodes.append(current_node)
            for child in current_node.children:
                recursive_search(child)

        recursive_search(node)
        return call_nodes

    @staticmethod
    def is_application_code(uri, project_root=None):
        if uri.startswith("file://"):
            file_path = uri[7:]
        else:
            print("URI is not a file URI. Please provide a file URI.")
            return False

        if project_root is None:
            project_root = os.path.dirname(os.path.abspath(__file__))

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

    @staticmethod
    def reset_caches():
        seen_files.clear()
        visited_locations.clear()

    @staticmethod
    def get_function_name_from_node(function_node):
        name_node = function_node.child_by_field_name("name")
        return name_node.text.decode("utf-8") if name_node else None

    @staticmethod
    def uri_to_file_path(uri):
        parsed_uri = urlparse(uri)
        if parsed_uri.scheme != "file":
            raise ValueError("URI does not use the file scheme")
        file_path = unquote(parsed_uri.path)
        if file_path.startswith("/") and len(file_path) > 2 and file_path[2] == ":":
            file_path = file_path[1:]
        return file_path

    @staticmethod
    def file_path_to_uri(file_path):
        if not os.path.isabs(file_path):
            raise ValueError("File path must be absolute")

        normalized_path = os.path.normpath(file_path)
        quoted_path = quote(normalized_path)

        uri = urlunparse(("file", "", quoted_path, "", "", ""))
        return uri

    def find_function_node_at_position(self, node, line, character, file_path=None):
        python = get_language("python")
        # should this also include method defs?
        query_string = """
                (function_definition) @function
                """
        query = python.query(query_string)
        captures = query.captures(node)
        for child, _ in captures:
            start_line, start_char = child.start_point
            end_line, end_char = child.end_point

            if (
                start_line >= line  # returning the first available function node
                or (start_line == line and start_char <= character)
                or (end_line == line and character <= end_char)
            ):
                return child

        return None

    def get_variable_name_from_assignment(self, assignment_node, file_path):
        identifier_node = next(
            (child for child in assignment_node.children if child.type == "identifier"),
            None,
        )
        if identifier_node:
            variable_name = identifier_node.text.decode("utf-8")
            line_number = identifier_node.end_point[0]
            return VariableAssignment(variable_name, line_number, file_path)
        return None

    @staticmethod
    def _list_files(directory):
        for root, dirs, files in os.walk(directory):
            for file in files:
                yield os.path.join(root, file)

    @staticmethod
    def does_node_belong_to_class(function_node):
        while function_node.parent:
            if function_node.parent.type == "class_definition":
                return True
            function_node = function_node.parent

        return function_node.type == "class_definition"

    def get_function_blueprint(self, function_node):
        declaration = ""
        for child in function_node.children:
            if child.type == "block":
                break

            child_text = child.text.decode("utf-8")
            declaration += child_text

            if child_text == "def" or child_text == "async":
                declaration += " "
        return declaration

    def get_class_blueprint(self, class_def_node):
        methods = []
        declaration = ""
        for child in class_def_node.children:
            if child.type == "block":
                break
            child_text = child.text.decode("utf-8")
            declaration += child_text
            if child_text == "class":
                declaration += " "

        for method in self.find_all_children_of_type(
            class_def_node, "function_definition"
        ):
            methods.append(self.get_function_blueprint(method))
        return ClassBlueprint(declaration, methods)

    def construct_repo_blueprint(self, root):
        repo_map = defaultdict(list)
        for file_path in self._list_files(root):
            root = self.parse_file(file_path)
            python = get_language("python")
            python_query = """
                (class_definition
              name: (identifier) @name.definition.class) @definition.class

            (function_definition
              name: (identifier) @name.definition.function) @definition.function 
                """

            classes_and_functions = python.query(python_query)
            for node, _ in classes_and_functions.captures(root.root_node):
                if node.type == "class_definition":
                    class_blueprint = self.get_class_blueprint(node)
                    repo_map[file_path].append(class_blueprint)
                if node.type == "function_definition":
                    if self.does_node_belong_to_class(node):
                        continue
                    function_name = self.get_function_blueprint(node)
                    repo_map[file_path].append(function_name)

        return repo_map

    def print_repo_blueprint(self, repo_blueprint):
        for file_path, class_and_functions in repo_blueprint.items():
            print(file_path)
            for child in class_and_functions:
                if isinstance(child, ClassBlueprint):
                    print(f"{child.declaration}")
                    for method in child.methods:
                        print(f"   |-- {method}")
                else:
                    print(f"|--- {child}")

    def traverse_function_calls(
        self,
        function_node: Node,
        file_path: str,
        parent_function_node: LeapingFunctionNode,
    ):
        if not function_node:
            return

        # Get all the variable assignments in the function

        function_name = self.get_function_name_from_node(function_node)
        function_source_code = function_node.text.decode("utf-8")
        if parent_function_node:
            parent_name = parent_function_node.name
        else:
            parent_name = None

        leaping_node_name = f"{function_name}"
        leaping_node = LeapingFunctionNode(
            leaping_node_name,
            0,
            0,
            file_path,
            function_source_code,
            function_name,
            function_node.start_point[0],
        )
        try:
            self.call_stack.create_node(
                tag=leaping_node_name,
                identifier=f"{function_name}",
                data=leaping_node,
                parent=parent_name,
            )
        except (
            treelib.exceptions.DuplicatedNodeIdError
        ):  # case where we've already tracked the fn
            pass

        call_nodes = self.find_all_children_of_type(function_node, "call")

        for call_node in call_nodes:
            line_no, character = call_node.start_point
            position = Position(line_no, character)

            locations = self.lsp_wrapper.get_definition(file_path, position)
            location = None
            if len(locations) > 0:
                location = locations[0]

            if location and self.is_application_code(location.uri):
                location_key = LocationCacheKey(location).key
                if location_key in visited_locations:
                    continue
                visited_locations.add(location_key)
                file_tree = self.parse_file(self.uri_to_file_path(location.uri))
                child_node = self.find_function_node_at_position(
                    file_tree.root_node,
                    location.range.start.line,
                    location.range.start.character,
                    location.uri,
                )
                self.traverse_function_calls(
                    child_node,
                    self.uri_to_file_path(location.uri),
                    leaping_node,
                )

    def get_statement_text_containing_line(self, file_path: str, line_no: int):
        tree_sitter_tree = self.parse_file(file_path)
        node = self.find_nodes_at_line(tree_sitter_tree.root_node, line_no)
        return (node.text.decode("utf-8"), node.start_point, node.end_point)

    def get_function_text_containing_line(self, file_path: str, line_no: int):
        tree_sitter_tree = self.parse_file(file_path)
        function_node = self.find_function_containing_line(
            tree_sitter_tree.root_node, line_no
        )
        return (
            function_node.text.decode("utf-8"),
            function_node.start_point,
            function_node.end_point,
        )

    def construct_function_tree(self, file_path, line_no):
        self.reset_caches()
        tree_sitter_tree = self.parse_file(file_path)
        self.root_node = tree_sitter_tree.root_node
        function_node = self.find_function_containing_line(
            tree_sitter_tree.root_node, line_no
        )

        self.traverse_function_calls(function_node, file_path, None)
        return self.call_stack

    def get_all_imports(self, filepath):
        return self.get_imports_for_file(filepath)

    def get_imports_for_file(self, file_path):
        tree_sitter_tree = self.parse_file(file_path)
        self.root_node = tree_sitter_tree.root_node
        python = get_language("python")

        regular_import_query = python.query("(import_statement) @import")
        import_from_query = python.query("(import_from_statement) @import")
        import_from_captures = import_from_query.captures(tree_sitter_tree.root_node)
        regular_import_captures = regular_import_query.captures(
            tree_sitter_tree.root_node
        )

        import_dict = {}

        # TODO: worry about aliased imports
        for node, _ in import_from_captures:
            import_string_found = False
            import_lhs = ""
            for child in node.children:
                if not import_string_found:
                    text = child.text.decode("utf-8")
                    import_lhs += f"{text} "
                elif child.type == "dotted_name":
                    import_rhs = child.text.decode("utf8")
                    import_dict[import_rhs] = f"{import_lhs}{import_rhs}"

                if child.type == "import":
                    import_string_found = True

        for node, _ in regular_import_captures:
            dotted_name = next(
                (child for child in node.children if child.type == "dotted_name"),
                None,
            )
            if dotted_name:
                import_dict[dotted_name.text.decode("utf-8")] = node.text.decode(
                    "utf-8"
                )

        return import_dict
