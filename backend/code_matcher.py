from dataclasses import dataclass
from functools import lru_cache
import rapidfuzz.fuzz as similarity_measure


@dataclass
class LineComparisonResult:
    start_line: int
    last_line: int
    similarity_score: float
    file_path: str


class CodeMatcher:
    def __init__(self, all_files: set[str]):
        self.all_files = all_files

    def find_best_match(self, source_text: str) -> LineComparisonResult:
        matches = []
        for file in self.all_files:
            file_matcher = CodeFileMatcher(file)
            match = file_matcher.locate_best_fit(source_text)
            matches.append(match)

        return sorted(matches, key=lambda x: x.similarity_score, reverse=True)[0]


class CodeFileMatcher:
    def __init__(self, file_path: str):
        with open(file_path, "r") as file:
            lines = file.readlines()
        self.file_path = file_path
        self.text_lines = lines

    # If matching one line and line appears multiple times, return the line more closely matching based on line number diff, what function it's in, maybe
    # also the context lines around it, and match the block instead to break ties

    @staticmethod
    @lru_cache(maxsize=None)
    def evaluate_line_similarity(source_line: str, comparison_line: str) -> float:
        if source_line == comparison_line:
            return 1
        if source_line.lstrip() == comparison_line.lstrip():
            difference_ratio = abs(len(source_line) - len(comparison_line)) / (
                len(source_line) + len(comparison_line)
            )
            return max(0.9 - difference_ratio, 0)
        if source_line.strip() == comparison_line.strip():
            difference_ratio = abs(len(source_line) - len(comparison_line)) / (
                len(source_line) + len(comparison_line)
            )
            return max(0.8 - difference_ratio, 0)
        line_similarity = similarity_measure.ratio(source_line, comparison_line)

        return max(0.85 * (line_similarity / 10000), 0)

    @staticmethod
    def check_if_ignorable(line: str) -> bool:
        cleaned_line = line.strip()
        return (
            not cleaned_line
            or cleaned_line.startswith("#")
            or cleaned_line.startswith("//")
        )

    @staticmethod
    def weight(index: int, total: int) -> float:
        mid_point = min(index, total - index)
        return 100 / (mid_point / 2 + 1)

    def compute_overall_similarity(
        self, source_lines: list[str], compared_lines: list[str]
    ) -> float:
        accumulated_scores = []
        ignored_lines_count = 0
        for index, each_line in enumerate(source_lines):
            for line in compared_lines:
                if self.check_if_ignorable(line):
                    ignored_lines_count += 1
                    continue
                weighted_score = self.weight(index, len(source_lines))
                accumulated_scores.append(
                    (self.evaluate_line_similarity(each_line, line), weighted_score)
                )

        total_score = sum(score * weight for score, weight in accumulated_scores)
        weighted_total = sum(weight for _, weight in accumulated_scores)
        overall_score = (total_score / weighted_total) if accumulated_scores else 0
        overall_score *= 1 - 0.05 * ignored_lines_count
        return overall_score

    def locate_best_fit(
        self,
        source_text: str,
    ) -> LineComparisonResult:
        source_text_lines = source_text.strip().split("\n")
        optimal_match = LineComparisonResult(-1, -1, 0, None)

        for start_idx in range(len(self.text_lines) - len(source_text_lines) + 1):
            end_idx = start_idx + len(source_text_lines)
            current_segment = self.text_lines[start_idx:end_idx]
            match_score = self.compute_overall_similarity(
                source_text_lines, current_segment
            )
            if match_score > optimal_match.similarity_score:
                optimal_match = LineComparisonResult(
                    start_idx, end_idx, match_score, self.file_path
                )
        return optimal_match
