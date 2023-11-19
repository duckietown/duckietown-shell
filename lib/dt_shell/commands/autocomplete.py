import argparse
import os
from typing import Optional

from argcomplete import CompletionFinder, split_line


class ArgumentParserCompleter(CompletionFinder):

    def __init__(self, argument_parser: Optional[argparse.ArgumentParser] = None):
        super(ArgumentParserCompleter, self).__init__(argument_parser=argument_parser, append_space=True)

    def get_completions(self, line: str):
        """
        This method is a wrapper around the method _get_completions from the superclass
        """
        # reproduce the traditional BASH setup for autocomplete with COMP_LINE and COMP_POINT
        comp_line: str = line
        comp_point: int = os.environ.get("COMP_POINT", len(line))

        # NOTE: DEBUG only
        # print(
        #     "\nLINE: {!r}".format(comp_line),
        #     "\nPOINT: {!r}".format(comp_point),
        # )

        cword_prequote, cword_prefix, cword_suffix, comp_words, last_wordbreak_pos = \
            split_line(comp_line, comp_point)
        comp_words = comp_words[1:]

        if cword_prefix and cword_prefix[0] in self._parser.prefix_chars and "=" in cword_prefix:
            # special case for when the current word is "--optional=PARTIAL_VALUE". Give optional to parser.
            comp_words.append(cword_prefix.split("=", 1)[0])

        # NOTE: DEBUG only
        # print(
        #     "\nLINE: {!r}".format(comp_line),
        #     "\nPOINT: {!r}".format(comp_point),
        #     "\nPREQUOTE: {!r}".format(cword_prequote),
        #     "\nPREFIX: {!r}".format(cword_prefix),
        #     "\nSUFFIX: {!r}".format(cword_suffix),
        #     "\nWORDS:", comp_words,
        # )

        return self._get_completions(comp_words, cword_prefix, cword_prequote, last_wordbreak_pos)
