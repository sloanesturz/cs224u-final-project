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

NUMBERS = [str(num2words(i)) for i in range(500)]

def str2tree(s):
    return Tree.fromstring(s)

def preprocess(question):
    # TODO: we could do a lot of good stuff here
    split = re.findall(r"[\w\-']+|[.,!?;]", question.lower())
    text = " ".join(split)
    print text
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
        solver = SympySolver()
        final_eqns = []
        if type(semantics[0]) is list:
            # case: we have more than one equation
            for semantic_rep in semantics[0]:
                eqn_as_string = convertSemanticsToEqn(semantic_rep)
                # add eqn to list of eqns
                final_eqns.append(eqn_as_string)

            print solver.our_evaluate(final_eqns, 2)

        elif type(semantics[0]) is tuple:
            # case: we only have one equation to solve
            eqn_as_string = convertSemanticsToEqn(semantics[0])
            final_eqns.append(eqn_as_string)

            # solve the equation
            print solver.our_evaluate(final_eqns, 1)

        return semantics

    def rules(self):
        rules = []

        def push_list(head, tail):
            return [head] + [tail]

        for i, w in enumerate(NUMBERS):
            rules.append(Rule('$Num', str(i), i))
            rules.append(Rule('$Num', w, i))

        rules.extend([
            # constraint setup
            Rule('$E', '$ConstraintList', lambda sems: sems),
            Rule('$ConstraintList', '$Constraint ?$EOL', lambda sems: sems[0]),
            Rule('$ConstraintList', '?$Command $Constraint ?$EOL $ConstraintList ?$Command', lambda sems: push_list(sems[1], sems[3])),

            # Generic constraint
            Rule('$Constraint', '$EBO $Expr', lambda sems: (sems[0][0], sems[0][1], sems[1])),
            Rule('$EBO', '$Expr $Compare', lambda sems: (sems[1], sems[0])),
            Rule('$EOL', '.'),
            Rule('$EOL', ','),

            # Constraints with leading Junk
            Rule('$JunkList', '$Junk ?$JunkList'),
            Rule('$Constraint', '$Find $JunkList $If $Constraint', lambda sems: sems[3]),
            Rule('$If', 'if'),
            Rule('$Find', 'find'),

            # Pre or postfix command sentence.
            Rule('$Command', '$Find $JunkList ?$EOL'),
        ])

        # PreOperator
        rules.append(Rule('$Expr', '$PreOperator $ExprList', lambda sems: (sems[0], sems[1])))
        for prefix in ['', 'the ']:
            rules.extend([
                Rule('$PreOperator', prefix + 'sum of', '+'),
                Rule('$PreOperator', prefix + 'difference of', '-'),
                Rule('$PreOperator', prefix + 'difference between', '-'),
                Rule('$PreOperator', prefix + 'product of', '*'),
                Rule('$PreOperator', prefix + 'quotient of', '/'),
            ])

        def consecutive_integers(n, is_even):
            # n -> number of Integers
            # is_even -> (True, False, None) == (even, odd, consec)
            try:
                count = int(n)
            except ValueError:
                count = NUMBERS.index(n)
            start = 1 if is_even == False else 0
            mult = 2 if is_even in (True, False) else 1
            return tuple('%s*k+%s' % (mult, mult * i + start) for i in range(count))

        rules.extend([
            # ExprList
            Rule('$ExprList', '$Expr $And $Expr', lambda sems: (sems[0], sems[2])),
            Rule('$And', 'and'),
            Rule('$ExprList', 'the numbers', ('x', 'y')),
            Rule('$ExprList', 'two numbers', ('x', 'y')),
            Rule('$ExprList', 'the numbers', ('x', 'y', 'z')),
            Rule('$ExprList', 'three numbers', ('x', 'y', 'z')),

            Rule('$ExprList', '$Expr $Consecutive ?$Even $Integers',
                lambda sems: consecutive_integers(sems[0], sems[2])),
            Rule('$Consecutive', 'consecutive'),
            Rule('$Even', 'even', True),
            Rule('$Even', 'odd', False),
            Rule('$Integers', 'integers'),
            Rule('$Integers', 'numbers'),

            # MidOperator
            Rule('$Expr', '$Expr $MidOperator $Expr', lambda sems: (sems[1], sems[2], sems[0])),
            Rule('$MidOperator', 'plus', '+'),
            Rule('$MidOperator', 'minus', '+'),
            Rule('$MidOperator', 'times', '*'),
            Rule('$MidOperator', 'divided by', '/'),
            Rule('$MidOperator', 'more than', '+'),
            Rule('$MidOperator', 'less than', '-'),
        ])

        rules.extend([
            # Comparisons
            Rule('$Compare', 'is', '='),
            Rule('$Compare', 'equals', '='),
            Rule('$Compare', 'is less than', '<'),
            Rule('$Compare', 'is less than or equal to', '<='),
            Rule('$Compare', 'is greater than', '>'),
            Rule('$Compare', 'is greater than or equal to', '>='),

            # SplitComparison
            Rule('$Constraint', '$Expr $SplitComparison $Expr $By $Expr', lambda sems: ('=', (sems[0], (sems[1], sems[2], sems[4])))),
            Rule('$SplitComparison', 'exceeds', '+'),
            Rule('$SplitComparison', 'is greater than', '+'),
            Rule('$SplitComparison', 'is less than', '-'),
            Rule('$By', 'by'),
        ])

        rules.extend([
            # Properties
            Rule('$Expr', 'its square', ('^2', 'x')),
            Rule('$Expr', 'its root', ('^1/2', 'x')),
            Rule('$Expr', 'their sum', ('+', ('x', 'y'))),
            Rule('$Expr', 'their sum', ('+', ('x', 'y', 'z'))),
            Rule('$Expr', 'their difference', ('-', ('x', 'y'))),
            Rule('$Expr', 'their difference', ('-', ('x', 'y', 'z'))),
        ])

        rules.extend([
            # Numbers and Variables
            Rule('$Expr', '$Num', lambda sems: (sems[0])),
            Rule('$Expr', '$Var', lambda sems: (sems[0])),

            Rule('$Var', 'an integer', 'x'),
            Rule('$Var', 'one integer', 'x'),
            Rule('$Var', 'a number', 'x'),
            Rule('$Var', 'one number', 'x'),

            Rule('$Var', 'another integer', 'y'),
            Rule('$Var', 'another number', 'y'),

            Rule('$Var', 'the smaller ?number', 'x'),
            Rule('$Var', 'the larger ?number', 'y'),
            Rule('$Var', 'the largest ?number', 'z'),
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

if __name__ == "__main__":
    domain = WordProbDomain()
    grammar = domain.grammar()

    input = " ".join(sys.argv[1:])
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

    # Running this is sad and will make you unhappy :(
    evaluate_dev_examples_for_domain(WordProbDomain())
