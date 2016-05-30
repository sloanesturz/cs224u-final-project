from collections import defaultdict
from numbers import Number

from domain import Domain
from example import Example
from experiment import evaluate_for_domain, evaluate_dev_examples_for_domain, train_test, train_test_for_domain, interact, learn_lexical_semantics, generate
from metrics import DenotationAccuracyMetric
from parsing import Grammar, Rule, print_grammar, compute_semantics
from scoring import rule_features

from nltk.tree import Tree

def str2tree(s):
    return Tree.fromstring(s)

class WordProbDomain(Domain):

    def train_examples(self):
        return [
            Example(input="the sum of an integer and its square is 72", semantics=('+', 1, 1), denotation=8),
            # x + x^2 = 72`
            # (equals (Expr (Plus ((Expr x) (Expr (squared x))))) (Expr 72))

        ]

    def test_examples(self):
        return [
        ]

    def dev_examples(self):
        return self.train_examples()

    def rules(self):
        rules = []
        for i in range(-100, 100):
            rules.append(Rule('$Num', str(i), i))


        rules.extend([
            Rule('$E', '$ConstraintList', lambda sems: sems),
            Rule('$ConstraintList', '$Constraint', lambda sems: sems),
            Rule('$ConstraintList', '$Constraint $ConstraintList', lambda sems: sems[0] + sems[1]), # ? wut
            Rule('$Constraint', '$EBO $Expr', lambda sems: (sems[0][0], sems[0][1], sems[1])),
            Rule('$EBO', '$Expr $Equals', lambda sems: (sems[1], sems[0])),
            Rule('$Expr', '$Combo $ExprList', lambda sems: (sems[0], sems[1])),
            Rule('$ExprList', '$Expr $And $Expr', lambda sems: (sems[0], sems[2])),
            Rule('$ExprList', 'two numbers', ('x', 'y')),
            Rule('$And', 'and'),
            Rule('$Combo', 'sum of', 'sum'),
            Rule('$Combo', 'difference of', 'diff'),
            # Rule('$Combo', 'product of', 'times'),
            Rule('$Expr', '$Num', lambda sems: (sems[0])),
            Rule('$Var', 'an integer', 'x'),
            Rule('$Expr', '$Var', lambda sems: (sems[0])),
            Rule('$Expr', 'its square', ('square', 'x')),
            Rule('$Equals', 'is', '='),
        ])

        # return [Rule('$E', 'foo')]

        return rules

    def operator_precedence_features(self, parse):
        """
        Traverses the arithmetic expression tree which forms the semantics of
        the given parse and adds a feature (op1, op2) whenever op1 appears
        lower in the tree than (i.e. with higher precedence than) than op2.
        """
        def collect_features(semantics, features):
            if isinstance(semantics, tuple):
                for child in semantics[1:]:
                    collect_features(child, features)
                    if isinstance(child, tuple) and child[0] != semantics[0]:
                        features[(child[0], semantics[0])] += 1.0
        features = defaultdict(float)
        collect_features(parse.semantics, features)
        return features

    def features(self, parse):
        features = rule_features(parse)
        features.update(self.operator_precedence_features(parse))
        return features

    def weights(self):
        weights = defaultdict(float)
        weights[('*', '+')] = 1.0
        weights[('*', '-')] = 1.0
        weights[('~', '+')] = 1.0
        weights[('~', '-')] = 1.0
        weights[('+', '*')] = -1.0
        weights[('-', '*')] = -1.0
        weights[('+', '~')] = -1.0
        weights[('-', '~')] = -1.0
        return weights

    def grammar(self):
        return Grammar(rules=self.rules(), start_symbol='$E')

    ops = {
        '~': lambda x: -x,
        '+': lambda x, y: x + y,
        '-': lambda x, y: x - y,
        '*': lambda x, y: x * y,
    }

    def execute(self, semantics):
        if isinstance(semantics, tuple):
            op = self.ops[semantics[0]]
            args = [self.execute(arg) for arg in semantics[1:]]
            return op(*args)
        else:
            return semantics

    def training_metric(self):
        return DenotationAccuracyMetric()


domain = WordProbDomain()
grammar = domain.grammar()
parses = grammar.parse_input('sum of two numbers is 72')
# parses = grammar.parse_input('difference of two numbers is 18 sum of two numbers is 72')
if len(parses) == 0:
    print 'no parses'
else:
    for p in parses:
        str2tree(str(p)).pprint()
        print "-"
        print compute_semantics(p)
# print_grammar(grammar)
# print grammar.parse_input('foo')
