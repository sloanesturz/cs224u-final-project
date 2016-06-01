# -*- coding: utf-8 -*-

import re
import json
import sys

from collections import defaultdict
from numbers import Number

from domain import Domain
from example import Example
from experiment import evaluate_for_domain, evaluate_dev_examples_for_domain, train_test, train_test_for_domain, interact, learn_lexical_semantics, generate
from metrics import DenotationAccuracyMetric
from parsing import Grammar, Rule, print_grammar, compute_semantics
from scoring import rule_features

from nltk.tree import Tree
from solver import SympySolver

from num2words import num2words

NUMBERS = [str(num2words(i)) for i in range(1000)]

def str2tree(s):
    return Tree.fromstring(s)

def preprocess(question):
    # TODO: we could do a lot of good stuff here
    split = re.findall(r"[\w\-']+|[.,!?;/]", question.lower())
    text = " ".join(split)
    return text

def make_examples(filename):
    examples = []
    with open(filename) as f:
        raw = json.load(f)
        for raw_example in raw:
            # TODO: support multiple anser
            examples.append(
                Example(input=preprocess(raw_example['text']),
                    denotation=raw_example['ans_simple'])
            )
    return examples

def convertSemanticsToEqn(semantics):
    if (type(semantics) is int) or len(semantics) == 1:
        # base case
        if semantics == "=":
            semantics = "=="
        return str(semantics)
    elif len(semantics) == 2:
        if len(semantics[1]) > 1:
            return convertSemanticsToEqn(semantics[1][0]) + str(semantics[0])  + convertSemanticsToEqn(semantics[1][1])
        else:
            return str(semantics[1]) + str(semantics[0])

    else:
        return convertSemanticsToEqn(semantics[1]) + convertSemanticsToEqn(semantics[0]) + convertSemanticsToEqn(semantics[2])

class WordProbDomain(Domain):

    # TODO: Segment examples into train/dev/test
    def train_examples(self):
        return make_examples('curated-data/non-yahoo-questions-dev.json')

    def test_examples(self):
        return make_examples('curated-data/non-yahoo-questions-test.json')

    def dev_examples(self):
        return make_examples('curated-data/small-dev-set.json')

    def features(self, parse):
        features = rule_features(parse)
        return features

    def execute(self, semantics):
        # return semantics # TODO: replace
        solver = SympySolver()
        answers = []
        final_eqns = []
        if type(semantics) is list:
            # case: we have more than one equation
            for semantic_rep in semantics:
                eqn_as_string = convertSemanticsToEqn(semantic_rep)
                # add eqn to list of eqns
                final_eqns.append(eqn_as_string)

            answers = solver.our_evaluate(final_eqns, 2)

        elif type(semantics) is tuple:
            # case: we only have one equation to solve
            eqn_as_string = convertSemanticsToEqn(semantics)
            final_eqns.append(eqn_as_string)

            # solve the equation
            answers = solver.our_evaluate(final_eqns, 1)

        # print answers
        return answers

    def rules(self):
        rules = []

        def push_list(head, tail):
            return [head] + [tail]

        for i, w in enumerate(NUMBERS):
            rules.append(Rule('$Num', str(i), i))
            rules.append(Rule('$Num', str(-i), -i))
            rules.append(Rule('$Num', w, i))

        rules.extend([
            # constraint setup
            Rule('$E', '$ConstraintList ?$Command', lambda sems: sems[0]),
            Rule('$E', '?$Command $ConstraintList', lambda sems: sems[1]),
            Rule('$ConstraintList', '$Constraint ?$EOL', lambda sems: sems[0]),
            Rule('$ConstraintList', '$Constraint ?$EOL ?$Joiner $ConstraintList',
                lambda sems: push_list(sems[0], sems[3])),

            Rule('$Joiner', 'and'),

            # Generic constraint
            Rule('$Constraint', '$EBO $Expr', lambda sems: (sems[0][0], sems[0][1], sems[1])),
            Rule('$EBO', '$Expr $Compare', lambda sems: (sems[1], sems[0])),
            Rule('$EOL', '.'),
            Rule('$EOL', ','),
            Rule('$EOL', '?'),

            # Constraints with leading or trailing Junk
            Rule('$JunkList', '$Junk ?$JunkList'),
            Rule('$Constraint', '$Find $JunkList $If $Constraint', lambda sems: sems[3]),
            Rule('$Constraint', '$If $Constraint ?$EOL $Find $JunkList', lambda sems: sems[1]),
            Rule('$If', 'if'),
            Rule('$If', 'such that'),
            Rule('$Find', 'find'),
            Rule('$Find', 'what'),

            # Pre or postfix command sentence.
            # TODO: extract a semantic meaning like ('find smallest') or ('find all')
            Rule('$Command', '$Find $JunkList ?$EOL'),
            Rule('$Command', '$What $Is $JunkList ?$EOL'),
            Rule('$What', 'what'),
            Rule('$Is', 'is'),
            Rule('$Is', 'are'),
        ])

        # PreOperator
        rules.append(Rule('$Expr', '$PreOperator $ExprList', lambda sems: (sems[0], sems[1])))
        rules.append(Rule('$Expr', '$PreUnaryOperator $Expr', lambda sems: (sems[0], sems[1])));
        for prefix in ['', 'the ']:
            rules.extend([
                Rule('$PreOperator', prefix + 'sum of', '+'),
                Rule('$PreOperator', prefix + 'difference of', '-'),
                Rule('$PreOperator', prefix + 'difference between', '-'),
                Rule('$PreOperator', prefix + 'product of', '*'),
                Rule('$PreOperator', prefix + 'quotient of', '/'),
                Rule('$PreUnaryOperator', prefix + 'square root of', '^(1/2)'),
                Rule('$PreUnaryOperator', prefix + 'square of', '^2'),
                Rule('$PreUnaryOperator', prefix + 'cube of', '^2'),
            ])

        rules.append(Rule('$Expr', '$Multiplier $Expr',
            lambda sems: ('*', (sems[0], sems[1]))))
        rules.extend([
            Rule('$Multiplier', 'twice', 2),
            Rule('$Multiplier', 'triple', 3),
            Rule('$Multiplier', 'quadruple', 4),
            Rule('$Multiplier', 'a quarter of', 1./4),
            Rule('$Multiplier', 'a third of', 1./3),
            Rule('$Multiplier', 'half', 1./2),
            Rule('$Multiplier', '$Expr $Of', lambda sems: sems[0]),
            Rule('$Of', 'of')
        ])

        def consecutive_integers(n, is_even):
            # n -> number of Integers
            # is_even -> (True, False, None) == (even, odd, consec)
            try:
                count = int(n)
            except (ValueError, TypeError) as e:
                try:
                    count = NUMBERS.index(n)
                except:
                    count = 2 # TODO: not this number
            start = 1 if is_even == False else 0
            mult = 2 if is_even in (True, False) else 1
            return tuple('%s*k+%s' % (mult, mult * i + start) for i in range(count))

        rules.extend([
            # ExprList
            Rule('$ExprList', '$Expr $And $Expr', lambda sems: (sems[0], sems[2])),
            Rule('$And', 'and'),
            Rule('$ExprList', '$The ?$SetDescriptor $Integers', ('x', 'y')),
            Rule('$ExprList', '?$The ?$SetDescriptor $Two $Integers', ('x', 'y')),
            Rule('$ExprList', '$The ?$SetDescriptor $Integers', ('x', 'y', 'z')),
            Rule('$ExprList', '?$The ?$SetDescriptor $Three $Integers', ('x', 'y', 'z')),

            Rule('$The', 'the'),
            Rule('$Two', '2'),
            Rule('$Two', 'two'),
            Rule('$Three', '3'),
            Rule('$Three', 'three'),

            Rule('$SetDescriptor', 'same'),

            Rule('$ExprList', '$MappingOperator $ExprList',
                lambda sems: tuple((sems[0], item) for item in sems[1])),
            Rule('$MappingOperator', 'the squares of', '^2'),
            Rule('$MappingOperator', 'the roots of', '^(.5)'),

            Rule('$ExprList', '$Expr ?$Sign $Consecutive ?$Even $Integers',
                lambda sems: consecutive_integers(sems[0], sems[3])),
            Rule('$Consecutive', 'consecutive'),
            Rule('$Even', 'even', True),
            Rule('$Even', 'odd', False),
            Rule('$Integers', 'integers'),
            Rule('$Integers', 'numbers'),
            Rule('$Sign', 'positive'),
            Rule('$Sign', 'negative'),

            # MidOperator
            Rule('$Expr', '$Expr $MidOperator $Expr', lambda sems: (sems[1], sems[0], sems[2])),
            # Word
            Rule('$MidOperator', 'plus', '+'),
            Rule('$MidOperator', 'minus', '+'),
            Rule('$MidOperator', 'times', '*'),
            Rule('$MidOperator', 'divided by', '/'),
            # Literal
            Rule('$MidOperator', '+', '+'),
            Rule('$MidOperator', '-', '+'),
            Rule('$MidOperator', '*', '*'),
            Rule('$MidOperator', '/', '/'),
            # Complex structure
            Rule('$MidOperator', 'more than', '+'),
            Rule('$MidOperator', 'less than', '-'),
        ])

        rules.extend([
            # Comparisons
            Rule('$Compare', 'is', '='),
            Rule('$Compare', 'equals', '='),
            Rule('$Compare', 'is equal to', '='),
            Rule('$Compare', 'is less than', '<'),
            Rule('$Compare', 'is less than or equal to', '<='),
            Rule('$Compare', 'is greater than', '>'),
            Rule('$Compare', 'is greater than or equal to', '>='),

            # SplitComparison
            # Type a. X exceeds Y by Z
            Rule('$Constraint', '$Expr $SplitComparison $Expr $By $Expr',
                lambda sems: ('=', (sems[0], (sems[1], sems[2], sems[4])))),
            # Type b: X is Z more than Y
            Rule('$Constraint', '$Expr $Is $Expr $SplitComparison $Expr',
                lambda sems: ('=', (sems[0], (sems[3], sems[4], sems[2])))),

            Rule('$SplitComparison', 'exceeds', '+'),
            Rule('$SplitComparison', 'is greater than', '+'),
            Rule('$SplitComparison', 'is less than', '-'),
            Rule('$SplitComparison', 'more than', '+'),
            Rule('$SplitComparison', 'less than', '-'),

            Rule('$By', 'by'),
            Rule('$Is', 'is'),
        ])

        rules.extend([
            # Properties
            Rule('$Expr', 'its square', ('^2', 'x')),
            Rule('$Expr', 'its root', ('^1/2', 'x')),

            # These examples make me uncomfortable a little.
            Rule('$Expr', 'their sum', ('+', ('x', 'y'))),
            Rule('$Expr', 'their sum', ('+', ('x', 'y', 'z'))),
            Rule('$Expr', 'their difference', ('-', ('x', 'y'))),
            Rule('$Expr', 'their difference', ('-', ('x', 'y', 'z'))),
            Rule('$Expr', 'whose sum', ('+', ('x', 'y'))),
            Rule('$Expr', 'whose sum', ('+', ('x', 'y', 'z'))),
            Rule('$Expr', 'whose difference', ('-', ('x', 'y'))),
            Rule('$Expr', 'whose difference', ('-', ('x', 'y', 'z'))),
        ])

        rules.extend([
            # Numbers and Variables
            Rule('$Expr', '$Num', lambda sems: (sems[0])),
            Rule('$Expr', '$Var', lambda sems: (sems[0])),

            Rule('$Var', 'x', 'x'),
            Rule('$Var', 'y', 'y'),
            Rule('$Var', 'z', 'z'),

            Rule('$Number', 'number'),
            Rule('$Number', 'no .'),
            Rule('$Number', 'integer'),
            Rule('$Number', 'one'), # 'the smaller one'

            Rule('$PrimaryArticle', 'a'),
            Rule('$PrimaryArticle', 'an'),
            Rule('$PrimaryArticle', 'one'),
            Rule('$PrimaryArticle', 'the'),
            Rule('$PrimaryArticle', 'the smallest'),
            Rule('$PrimaryArticle', 'the smaller'),
            Rule('$PrimaryArticle', 'the same'),

            Rule('$Var', '$PrimaryArticle ?$NumberDescriptor ?$Number', 'x'),

            Rule('$NumberDescriptor', 'positive'),
            Rule('$NumberDescriptor', 'constant'),
            Rule('$NumberDescriptor', 'negative'),

            Rule('$Var', '$SecondaryArticle ?$NumberDescriptor ?$Number', 'y'),
            Rule('$SecondaryArticle', 'another'),
            Rule('$SecondaryArticle', 'the other'),
            Rule('$SecondaryArticle', 'the larger'),
            Rule('$SecondaryArticle', 'the second'),
            Rule('$SecondaryArticle', 'a larger'),
            Rule('$SecondaryArticle', 'a second'),


            Rule('$Var', '$TertiaryArticle ?$NumberDescriptor ?$Number', 'z'),
            Rule('$TertiaryArticle', 'the largest'),
            Rule('$TertiaryArticle', 'the third'),
            Rule('$TertiaryArticle', 'a largest'),
            Rule('$TertiaryArticle', 'a third'),
        ])

        # Add in a class called '$Junk' for words that don't matter
        # Vocab.txt contains all the vocab used in grammar
        with open('vocab.txt') as f:
            for line in f:
                rules.append(Rule('$Junk', line.strip()))

        return rules

    def grammar(self):
        return Grammar(rules=self.rules(), start_symbol='$E')

    def training_metric(self):
        return DenotationAccuracyMetric()

def check_parses():
    with open('curated-data/non-yahoo-questions-dev.json') as f:
        examples = json.load(f)
        succ_parse = 0
        for example in examples:
            print example['text']
            if len(grammar.parse_input(preprocess(example['text']))) > 0:
                print u"✓"
                succ_parse += 1
            else:
                print u"✗"
        print "success", 100. * succ_parse / (len(examples))

if __name__ == "__main__":
    domain = WordProbDomain()
    grammar = domain.grammar()

    input = " ".join(sys.argv[1:])
    if '--check-parses' in sys.argv:
        check_parses()
    elif input:
        print input
        parses = grammar.parse_input(preprocess(input))

        print "Number of parses: {0}".format(len(parses))
        for _, v in {str(s): s for s in [p.semantics for p in parses]}.iteritems():
            print v
            print "Now trying to solve the parse"
            domain.execute(v)
        if len(parses) == 0:
            print 'no parses'
        # print str2tree(str(parses[0])).pprint()
    else:
        # Running this is sad and will make you unhappy :(
        evaluate_dev_examples_for_domain(WordProbDomain())
