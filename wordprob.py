import re
import json
import sys

from collections import defaultdict
import collections
from numbers import Number
from itertools import chain

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
    split = re.findall(r"[A-Za-z\-']+|[.,!?;/=+*]|-?\d+", question.lower())
    text = " ".join(split)
    text = text.replace('. .', '.') # TODO: make more general?
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
    if (type(semantics) is int) or \
            (type(semantics) is str) or \
            (type(semantics) is float) or \
            len(semantics) == 1:
        # base case
        return str(semantics)
    elif len(semantics) == 2:
        if type(semantics[1]) is int:
            return str(semantics[1]) + str(semantics[0])
        elif len(semantics[1]) == 3:
            # "consecutive" type questions where semantics are in the form:
            # ('+', ('2*x+1', '2*x+3', '2*x+5'))
            return "((" + convertSemanticsToEqn(semantics[1][0]) + ")" + \
                convertSemanticsToEqn(semantics[0]) +  \
                "(" + convertSemanticsToEqn(semantics[1][1]) + ")" + \
                convertSemanticsToEqn(semantics[0]) + \
                "(" + convertSemanticsToEqn(semantics[1][2]) + "))" \

        elif len(semantics[1]) > 1:
            if "^" in semantics[0]:
                # cases where semantics are in the form:
                # ('^2', ('+', ('1*x+0', '1*x+1')))
                return "(" + convertSemanticsToEqn(semantics[1]) + ")" + str(semantics[0])
            elif semantics[0] == "abs":
                return "Abs(%s)" % convertSemanticsToEqn(semantics[1])
            else:
                return "((" + convertSemanticsToEqn(semantics[1][0]) + ")" + str(semantics[0])  +  "(" + convertSemanticsToEqn(semantics[1][1]) + "))"
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

    def flatten_list(self, l):
        total = []
        if type(l) is list:
            for x in l:
                total = total + self.flatten_list(x)
            return total
        return [l]

    def execute(self, semantics):
        is_consecutive = False
        if "k" in str(semantics):
            is_consecutive = True

        # return semantics # TODO: replace
        solver = SympySolver()
        answers = []
        final_eqns = []
        semantics = self.flatten_list([semantics])
        for semantic_rep in semantics:
            eqn_as_string = convertSemanticsToEqn(semantic_rep)
            # add eqn to list of eqns
            final_eqns.append(eqn_as_string)

        print final_eqns

        num_vars = solver.count_variables(final_eqns)
        answers = solver.our_evaluate(final_eqns, num_vars, is_consecutive, "-")
        answers += solver.our_evaluate(final_eqns, num_vars, is_consecutive, "+")

        # print answers
        return answers

    def rules(self):
        rules = []

        def push_list(head, tail):
            return [head] + [tail]

        for i, w in enumerate(NUMBERS):
            rules.append(Rule('$Num', str(i), i))
            rules.append(Rule('$Num', "- %s" % i, -i))
            rules.append(Rule('$Num', w, i))
            rules.append(Rule('$Num', "negative %s" % w, -i))
            if '-' in w:
                rules.append(Rule('$Num', w.replace('-', ' '), i))
            if ' and ' in w:
                rules.append(Rule('$Num', w.replace(' and ', ' '), i))

        rules.extend([
            # Odd type of problem: 'four plus four' -> x = 4 + 4
            Rule('$E', '$Expr', lambda sems: ('=', sems[0], 'x')),

            # Usual types of problem strucutre
            Rule('$E', '?$Command $ConstraintList ?$Command', lambda sems: sems[1]),
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
            Rule('$Comma', ','),

            # Constraints with leading or trailing Junk
            Rule('$JunkList', '$Junk ?$JunkList'),
            Rule('$Constraint', '$Find $Constraint', lambda sems: sems[1]),
            Rule('$Constraint', '$Find $JunkList $If $Constraint', lambda sems: sems[3]),
            Rule('$Constraint', '$If $Constraint ?$EOL $Find $JunkList', lambda sems: sems[1]),
            Rule('$If', 'if'),
            Rule('$If', 'such that'),
            Rule('$Find', 'find'),
            Rule('$Find', 'what'),

            # Pre or postfix command sentence.
            # TODO: extract a semantic meaning like ('find smallest') or ('find all')
            Rule('$Command', '$Find $JunkList ?$EOL'),
            Rule('$Command', '$What $WordIs $JunkList ?$EOL'),
            Rule('$Command', '$I $Have $JunkList ?$EOL'),
            Rule('$Command', '$Given $JunkList ?$EOL'),
            Rule('$What', 'what'),
            Rule('$WordIs', 'is'),
            Rule('$WordIs', 'are'),
            Rule('$Have', 'have'),
            Rule('$I', 'i'),
            Rule('$Given', 'given'),
        ])

        # Complex constraint: 'When x is added to y the result is z'
        rules.extend([
            Rule('$Constraint', '$Occasion $Expr $OccasionOpRtoL $Expr ?$EOL $ResultsIn $Expr',
                lambda sems: ('=', (sems[2], sems[1], sems[3]), sems[6])),
            Rule('$Occasion', 'when'),
            Rule('$Occasion', 'if'),
            Rule('$OccasionOpRtoL', 'is added to', '+'),
            Rule('$OccasionOpRtoL', 'is multiplied by', '*'),
            Rule('$OccasionOpRtoL', 'is divided by', '/'),

            Rule('$Constraint', '$Occasion $Expr $OccasionOpLtoR $Expr ?$EOL $ResultsIn $Expr',
                lambda sems: ('=', (sems[2], sems[3], sems[1]), sems[6])),
            Rule('$OccasionOpLtoR', 'is subtracted from', '-'),

            Rule('$ResultsIn', 'the result is'),
        ])

        # Non-standard constraint OperateAndEquality
        rules.extend([
            Rule('$Constraint', '?$Question $ExprList $OperatorAndEquality $Expr',
                lambda sems: ('=', (sems[2], sems[1]), sems[3])),
            Rule('$OperatorAndEquality', 'total to', '+'),
            Rule('$OperatorAndEquality', 'sum to', '+'),
            Rule('$OperatorAndEquality', 'total', '+'),
            Rule('$OperatorAndEquality', 'sum', '+'),
            Rule('$OperatorAndEquality', 'add up to', '+'),
            Rule('$OperatorAndEquality', 'have a sum of', '+'),
            Rule('$OperatorAndEquality', 'have a total of', '+'),
            Rule('$OperatorAndEquality', 'have a difference of', '-'),
            Rule('$OperatorAndEquality', 'have the sum of', '+'),
            Rule('$OperatorAndEquality', 'have the total of', '+'),
            Rule('$OperatorAndEquality', 'have the difference of', '-'),
            Rule('$OperatorAndEquality', 'differ by', '-'),
            Rule('$Question', 'which'),
            Rule('$Question', 'what'),
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
                Rule('$PreUnaryOperator', prefix + 'cube of', '^3'),
            ])

        rules.append(Rule('$Expr', '$Multiplier $Expr',
            lambda sems: ('*', (sems[0], sems[1]))))

        rules.extend([
            Rule('$Multiplier', 'twice', 2),
            Rule('$Multiplier', 'triple', 3),
            Rule('$Multiplier', 'quadruple', 4),
            Rule('$Multiplier', 'half', 1./2),

            # two times the first plus 'a fourth the second'
            Rule('$Multiplier', '?$A $Fraction ?$Of', lambda sems: sems[1]),
            # two times the first plus ' fourth of the second'
            Rule('$Multiplier', '$Expr $Of', lambda sems: sems[0]),
            # two times the first plus '3/4 of the second'
            Rule('$Multiplier', '$Num $Div $Num',
                lambda sems: 1. * sems[0] / sems[2]),
            Rule('$Of', 'of'),
            Rule('$A', 'one'),
            Rule('$A', 'a'),
            Rule('$Div', '/')
        ])

        for prefix in ['', 'one-']:
            rules.extend([
                Rule('$Fraction', prefix + 'fifth', 1./5),
                Rule('$Fraction', prefix + 'fourth', 1./4),
                Rule('$Fraction', prefix + 'third', 1./3),
                Rule('$Fraction', prefix + 'third', 1./3),
                Rule('$Fraction', prefix + 'half', 1./2),
            ])


        def consecutive_integers(n, is_even, mult=None):
            # n -> number of Integers
            # is_even -> (True, False, None) == (even, odd, consec)
            try:
                count = int(n)
            except (ValueError, TypeError) as e:
                try:
                    count = NUMBERS.index(n)
                except:
                    count = 2 # TODO: not this number
            start = -1 if is_even == False else 0
            if mult is None:
                mult = 2 if is_even in (True, False) else 1
            return tuple('%s*k+%s' % (mult, mult * i + start) for i in range(count))

        rules.extend([
            # ExprList
            Rule('$ExprList', '$Expr $And $Expr', lambda sems: (sems[0], sems[2])),
            Rule('$And', 'and'),
            Rule('$ExprList', '$The ?$SetDescriptor ?$Integers', ('x', 'y')),
            Rule('$ExprList', '?$The ?$SetDescriptor $Two ?$Integers', ('x', 'y')),
            Rule('$ExprList', '$The ?$SetDescriptor ?$Integers', ('x', 'y', 'z')),
            Rule('$ExprList', '?$The ?$SetDescriptor $Three ?$Integers', ('x', 'y', 'z')),

            Rule('$The', 'the'),
            Rule('$Two', '2'),
            Rule('$Two', 'two'),
            Rule('$Three', '3'),
            Rule('$Three', 'three'),

            Rule('$SetDescriptor', 'same'),
            Rule('$SetDescriptor', 'all'),

            Rule('$ExprList', '?$The $EndDescriptor $Two $Integers',
                lambda sems: ('x', 'y', 'z')[sems[1][0]:sems[1][1]]),
            Rule('$EndDescriptor', 'larger', (1, 3)),
            Rule('$EndDescriptor', 'largest', (1, 3)),
            Rule('$EndDescriptor', 'smaller', (0, 2)),
            Rule('$EndDescriptor', 'smallest', (0, 2)),

            # # Is this crazy?! Probably!
            Rule('$ExprList', 'its digits',
                (('%', ('/', 'x', 10), 10), ('%', 'x', 10))),
            Rule('$ExprList', 'the digits of a two-digit number',
                (('%', ('/', 'x', 10), 10), ('%', 'x', 10))),
            Rule('$ExprList', 'the digits of a 2-digit number',
                (('%', ('/', 'x', 10), 10), ('%', 'x', 10))),
            Rule('$ExprList', 'the digits',
                (('%', ('/', 'x', 10), 10), ('%', 'x', 10))),

            Rule('$ExprList', '$ExprList $PostMappingOperator',
                lambda sems: tuple((sems[1], item) for item in sems[0])),
            Rule('$PostMappingOperator', 'whose squares', '^2'),

            Rule('$ExprList', '$PreMappingOperator $ExprList',
                lambda sems: tuple((sems[0], item) for item in sems[1])),
            Rule('$PreMappingOperator', 'the squares of', '^2'),
            Rule('$PreMappingOperator', 'the roots of', '^(.5)'),
            Rule('$PreMappingOperator', 'the reciprocals of', '^(-1)'),

            Rule('$ExprList', '$Expr ?$Sign $Consecutive ?$Sign ?$Even ?$Sign $Integers ?$Parenthetical',
                lambda sems: consecutive_integers(sems[0], sems[4])),
            Rule('$Consecutive', 'consecutive'),
            Rule('$Even', 'even', True),
            Rule('$Even', 'odd', False),
            Rule('$Integers', 'integers'),
            Rule('$Integers', 'numbers'),
            Rule('$Sign', 'positive'),
            Rule('$Sign', 'negative'),

            Rule('$ExprList', '$Num $Consecutive $Multiples $Of $Num',
                lambda sems: consecutive_integers(sems[0], None, sems[4])),
            Rule('$Multiples', 'multiples'),

            Rule('$Parenthetical', '$Expr $Comma $Expr ?$Comma $And $Expr'),

            # MidOperator
            Rule('$Expr', '$Expr ?$Comma $MidOperator $Expr ?$Comma',
                lambda sems: (sems[2], sems[0], sems[3])),
        ])

        rules.extend([
            # Word
            Rule('$MidOperator', 'plus', '+'),
            Rule('$MidOperator', 'minus', '-'),
            Rule('$MidOperator', 'times', '*'),
            Rule('$MidOperator', 'time', '*'),
            Rule('$MidOperator', 'modulo', '%'),
        ])

        for prefix in ['', 'when ']:
            rules.extend([
                Rule('$MidOperator', prefix + 'added to', '+'),
                Rule('$MidOperator', prefix + 'multiplied by', '+'),
                Rule('$MidOperator', prefix + 'divided by', '/'),
                Rule('$MidOperator', prefix + 'decreased by', '-'),
            ])

        rules.extend([
            # Literal
            Rule('$MidOperator', '+', '+'),
            Rule('$MidOperator', '-', '-'),
            Rule('$MidOperator', '*', '*'),
            Rule('$MidOperator', '/', '/'),
            Rule('$MidOperator', '%', '%'),
            # Complex structure
            Rule('$MidOperator', 'more than', '+'),
            Rule('$MidOperator', 'less than', '-'),
        ])

        rules.extend([
            # Comparisons
            Rule('$Compare', 'is', '='),
            Rule('$Compare', 'equals', '='),
            Rule('$Compare', '=', '='),
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
            # Find two consecutive ints which add to 4 and 'whose product is X'
            # Can we fix coref?
            Rule('$Expr', '$Group $GroupOp', lambda sems: (sems[1], sems[0])),
            Rule('$Group', 'their', ('x', 'y')),
            Rule('$Group', 'their', ('x', 'y', 'z')),
            Rule('$Group', 'whose', ('x', 'y')),
            Rule('$Group', 'whose', ('x', 'y', 'z')),
            Rule('$Group', 'the', ('x', 'y')),
            Rule('$Group', 'the', ('x', 'y', 'z')),

            Rule('$GroupOp', 'sum', '+'),
            Rule('$GroupOp', 'sums', '+'),
            Rule('$GroupOp', 'difference', '-'),
            Rule('$GroupOp', 'differences', '-'),
            Rule('$GroupOp', 'product', '*'),
            Rule('$GroupOp', 'products', '*'),

            # This one feels safe: 'two consecutive ints whose sum is 7'
            Rule('$Expr', '$ExprList $Group $GroupOp', lambda sems: (sems[2], sems[0])),
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
            Rule('$PrimaryArticle', 'the least'),
            Rule('$PrimaryArticle', 'the same'),
            Rule('$PrimaryArticle', 'that'),
            Rule('$PrimaryArticle', 'the first'),

            Rule('$Var', '$PrimaryArticle ?$NumberDescriptor ?$Number', 'x'),

            Rule('$NumberDescriptor', 'positive'),
            Rule('$NumberDescriptor', 'constant'),
            Rule('$NumberDescriptor', 'negative'),
            Rule('$NumberDescriptor', 'whole'),
            Rule('$NumberDescriptor', 'natural'),

            Rule('$Var', '$SecondaryArticle ?$NumberDescriptor ?$Number', 'y'),
            Rule('$SecondaryArticle', 'another'),
            Rule('$SecondaryArticle', 'the other'),
            Rule('$SecondaryArticle', 'the larger'),
            Rule('$SecondaryArticle', 'the second'),
            Rule('$SecondaryArticle', 'a larger'),
            Rule('$SecondaryArticle', 'a second'),


            Rule('$Var', '$TertiaryArticle ?$NumberDescriptor ?$Number', 'z'),
            Rule('$TertiaryArticle', 'the largest'),
            Rule('$TertiaryArticle', 'the greatest'),
            Rule('$TertiaryArticle', 'the third'),
            Rule('$TertiaryArticle', 'a largest'),
            Rule('$TertiaryArticle', 'a third'),

            Rule('$Expr', '$Selector $ExprList', lambda sems: sems[1][sems[0]]),
            Rule('$Selector', 'the smallest of', 0),
            Rule('$Selector', 'the largest of', -1),
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

# returns an array where the elements are sets of gold answers
# [set('-1'), set('13.33')]
def formatGoldAnswers(nice_answers):
    gold_list_of_answers = []
    for item in nice_answers:
        gold_answer_set = set()
        if isinstance(item, collections.Iterable):
            for gold_ans in item:
                gold_answer_set.add(str(gold_ans))

        # add set of answers to list of answers
        gold_list_of_answers.append(gold_answer_set)

    return gold_list_of_answers

def formatOurAnswers(our_answers):
    list_of_answers = []
    our_answer_set = set()
    for index in xrange(0, len(our_answers)):
        answer = our_answers[index]
        if isinstance(answer, collections.Iterable):
            if(index != 0):
                list_of_answers.append(our_answer_set)
                our_answer_set = set()

            for ans in answer:
                our_answer_set.add(str(ans))
        else:
            our_answer_set.add(str(answer))

    list_of_answers.append(our_answer_set)

    return list_of_answers

def answeredCorrectly(gold_list_of_answers, list_of_answers, strictness):
    for gold_answer_set in gold_list_of_answers:
        for our_answer_set in list_of_answers:
            if strictness == 'tight':
                # we need a direct match to count the answer as correct
                if gold_answer_set == our_answer_set:
                    return True
            else:
                # our answer can be a subset of the actual answers or vice-versa
                if gold_answer_set == our_answer_set or gold_answer_set.issubset(our_answer_set) or our_answer_set.issubset(gold_answer_set):
                    return True

    return False

def check_parses():
    with open('curated-data/non-yahoo-questions-dev-simplified.json') as f:
        examples = json.load(f)
        succ_parse = 0
        succ_solve = 0
        right_answers = 0
        for example in examples:
            parses = grammar.parse_input(preprocess(example['text']))
            gold_list_of_answers = formatGoldAnswers(example["nice_answers"])
            if len(parses) > 0:
                succ_parse += 1
                empty_answer = True
                right_answer_check = False
                for _, v in {str(s): s for s in [p.semantics for p in parses]}.iteritems():
                    try:
                        answer = domain.execute(v)
                        print "Our answer(s): " + str(answer)
                        print "Gold answer(s): " + str(example["nice_answers"])
                        if answeredCorrectly(gold_list_of_answers, formatOurAnswers(answer), 'loose'):
                            right_answer_check = True
                    except Exception as e:
                        print example['text']
                        raise e
                    if len(answer) != 0:
                        empty_answer = False
                if empty_answer == False:
                    succ_solve += 1
                    if right_answer_check == True:
                        print "The question: " + example["text"]
                        print "Got this question right!\n"
                        right_answers += 1
                    else:
                        print "The question: " + example["text"]
                        print "Got this question wrong :(\n"

        print "success parses", 100. * succ_parse / (len(examples))
        print "success solve", 100. * succ_solve / (len(examples))
        print "right answers", 100. * right_answers / (len(examples))

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
            print "answer: " + str(domain.execute(v))
        if len(parses) == 0:
            print 'no parses'
    else:
        # Running this is sad and will make you unhappy :(
        evaluate_dev_examples_for_domain(WordProbDomain())
