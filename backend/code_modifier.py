import dataclasses
import difflib
from collections import OrderedDict
from typing import Optional

from backend.editor_socket_wrapper import EditorSocketWrapper


@dataclasses.dataclass
class CodeSnippet:
    start_line: int
    end_line: int
    new_lines: list[str]
    indented_lines: Optional[list[str]] = None

    @property
    def length(self):
        return len(self.new_lines)


@dataclasses.dataclass
class EditorOperation:
    code_snippet: CodeSnippet
    type: str


@dataclasses.dataclass
class LineOperation:
    line_number: int
    line: str

    def __gt__(self, other):
        return self.line_number > other.line_number


@dataclasses.dataclass
class SnippetOperations:
    additions: list[LineOperation]
    deletions: list[EditorOperation]


class FileModifier:
    _instances = {}

    def __new__(cls, filepath, headless=False, socket_wrapper=None):
        """
        Singleton to ensure that the there's at most one instance of the FileModifier for each file
        """
        if filepath not in cls._instances.keys():
            cls._instances[filepath] = super(FileModifier, cls).__new__(cls)
        return cls._instances[filepath]

    def __init__(self, filepath, headless=False, socket_wrapper=None):
        if not hasattr(self, "initialized"):
            self.filepath = filepath
            self.current_lines = self._read_file()
            self.history = OrderedDict()
            self.headless = headless
            self.socket_wrapper: EditorSocketWrapper = socket_wrapper
            self.initialized = True

    def _read_file(self):
        try:
            with open(self.filepath, "r") as file:
                return file.readlines()
        except FileNotFoundError:
            return []

    def _write_file(self, step):
        current_lines = self.current_lines
        self.history[step] = current_lines
        with open(self.filepath, "w") as file:
            file.writelines(self.current_lines)

    def _get_indentation(self, line):
        return line[: len(line) - len(line.lstrip())]

    def _indent_lines(self, code_snippet):
        start_line = code_snippet.start_line

        if self.current_lines:
            while self.current_lines[start_line].strip() == "":
                start_line -= 1
            first_line_indentation = self._get_indentation(
                self.current_lines[start_line]
            )
        else:
            first_line_indentation = ""
        # Prepare new lines with the detected indentation
        indented_new_lines = [
            first_line_indentation + line
            if not line.startswith(first_line_indentation)
            else line
            for line in code_snippet.new_lines
        ]
        code_snippet.indented_lines = indented_new_lines
        return indented_new_lines

    def _sanitize_line(self, line):
        if "&gt;" in line:
            line = line.replace("&gt;", ">")
        return line

    def _insert_lines(
        self,
        additions: list[LineOperation],
        indented_new_lines,
        code_snippet: CodeSnippet,
        step,
    ):
        for idx, addition in enumerate(additions):
            line_number = code_snippet.start_line + addition.line_number
            indented_line = indented_new_lines[addition.line_number]
            if not self.headless and self.socket_wrapper:
                self.socket_wrapper.notify_frontend_of_insert(
                    line_number, indented_line, step, idx == len(additions) - 1
                )
            self._sanitize_line(indented_line)
            self.current_lines.insert(
                line_number,
                indented_line + "\n"
                if not indented_line.endswith("\n")
                else indented_line,
            )

    def _delete_lines(
        self, sorted_deletions: list[LineOperation], prev_snippet: CodeSnippet, step
    ):
        for deletion in sorted_deletions:
            line_number = prev_snippet.start_line + deletion.line_number
            if not self.headless and self.socket_wrapper:
                self.socket_wrapper.notify_frontend_of_delete(line_number, step)
            del self.current_lines[line_number]

    def compare_snippets(
        self, snippet_1: CodeSnippet, snippet_2: CodeSnippet
    ) -> SnippetOperations:
        d = difflib.Differ()
        diffs = list(d.compare(snippet_1.new_lines, snippet_2.new_lines))

        additions = []
        removals = []
        snippet1_line_number = 0
        snippet2_line_number = 0

        for line in diffs:
            code = line[:2]
            if code == "  ":
                snippet1_line_number += 1
                snippet2_line_number += 1
            elif code == "+ ":
                additions.append(LineOperation(snippet2_line_number, line[2:].strip()))
                snippet2_line_number += 1
            elif code == "- ":
                removals.append(LineOperation(snippet1_line_number, line[2:].strip()))
                snippet1_line_number += 1

        return SnippetOperations(additions, removals)

    def delete_and_insert(
        self, prev_snippet: CodeSnippet, new_snippet: CodeSnippet, step: int
    ):
        diffs = self.compare_snippets(prev_snippet, new_snippet)

        indented_new_lines = self._indent_lines(new_snippet)
        # removals have the original line numbers, additions have the line number from the new snippet
        sorted_deletions = sorted(diffs.deletions, reverse=True)

        sorted_additions = sorted(diffs.additions)
        if sorted_deletions:
            self._delete_lines(sorted_deletions, prev_snippet, step)

        if sorted_additions:
            self._insert_lines(sorted_additions, indented_new_lines, new_snippet, step)

        self._write_file(step)

    def save(self, filepath=None):
        if not filepath:
            filepath = self.filepath

        with open(filepath, "w") as file:
            file.writelines(self.current_lines)

    def undo(self):
        if not len(self.history) > 1:
            return
        step, lines = self.history.popitem(last=True)

        self.current_lines = lines
        self._write_file()
