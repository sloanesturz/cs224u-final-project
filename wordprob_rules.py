# wordprob_rules.py
from num2words import num2words
from parsing import Rule

NUMBERS = [str(num2words(i)) for i in range(1000)]

def load_rules():
    rules = []

    def push_list(head, tail):
        return [head] + [tail]

    def varname(i):
        return "v%s" % i

    def to_int(sem):
        if isinstance(sem, tuple):
            return to_int(sem[0])
        else:
            try:
                return int(sem)
            except (ValueError, TypeError) as _:
                return 1

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
        Rule('$E', '$Expr', lambda sems: ('=', sems[0], varname(0))),

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
            Rule('$PreOperator', prefix + 'product of', '*'),
            Rule('$PreOperator', prefix + 'quotient of', '/'),
            Rule('$PreUnaryOperator', prefix + 'square root of', '^(1/2)'),
            Rule('$PreUnaryOperator', prefix + 'square of', '^2'),
            Rule('$PreUnaryOperator', prefix + 'cube of', '^3'),
        ])

    rules.append(Rule('$Expr', '$RevPreOperator $ExprList',
        lambda sems: (sems[0], tuple(reversed(sems[1])))));
    for prefix in ['', 'the ']:
        rules.extend([
            Rule('$RevPreOperator', prefix + 'difference of', '-'),
            Rule('$RevPreOperator', prefix + 'difference between', '-'),
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
        Rule('$ExprList', '$The ?$SetDescriptor ?$Integers',
            tuple(varname(i) for i in [0, 1])),
        Rule('$ExprList', '?$The ?$SetDescriptor $Two ?$Integers',
            tuple(varname(i) for i in [0, 1])),
        Rule('$ExprList', '$The ?$SetDescriptor ?$Integers',
            tuple(varname(i) for i in [0, 1, 2])),
        Rule('$ExprList', '?$The ?$SetDescriptor $Three ?$Integers',
            tuple(varname(i) for i in [0, 1, 2])),

        Rule('$The', 'the'),
        Rule('$Two', '2'),
        Rule('$Two', 'two'),
        Rule('$Three', '3'),
        Rule('$Three', 'three'),

        Rule('$SetDescriptor', 'same'),
        Rule('$SetDescriptor', 'all'),

        Rule('$ExprList', '?$The $EndDescriptor $Two $Integers',
            lambda sems: tuple(varname(i * sems[1]) for i in [0, 1])),
        Rule('$EndDescriptor', 'larger', -1),
        Rule('$EndDescriptor', 'largest', -1),
        Rule('$EndDescriptor', 'smaller', 0),
        Rule('$EndDescriptor', 'smallest', 0),

        # # Is this crazy?! Probably!
        # Rule('$ExprList', 'its digits',
        #     (('%', ('/', varname(0), 10), 10), ('%', varname(0), 10))),
        # Rule('$ExprList', 'the digits of a two-digit number',
        #     (('%', ('/', varname(0), 10), 10), ('%', varname(0), 10))),
        # Rule('$ExprList', 'the digits of a 2-digit number',
        #     (('%', ('/', varname(0), 10), 10), ('%', varname(0), 10))),
        # Rule('$ExprList', 'the digits',
        #     (('%', ('/', varname(0), 10), 10), ('%', varname(o), 10))),

        Rule('$ExprList', '$ExprList $PostMappingOperator',
            lambda sems: tuple((sems[1], item) for item in sems[0])),
        Rule('$PostMappingOperator', 'whose squares', '^2'),

        Rule('$ExprList', '$PreMappingOperator $ExprList',
            lambda sems: tuple((sems[0], item) for item in sems[1])),
        Rule('$PreMappingOperator', 'the squares of', '^2'),
        Rule('$PreMappingOperator', 'the roots of', '^(.5)'),
        Rule('$PreMappingOperator', 'the reciprocals of', '^(-1)'),

        Rule('$ExprList', '$Expr ?$Sign $Consecutive ?$Sign ?$Even ?$Sign $Integers ?$Parenthetical',
            lambda sems: tuple(varname(i) for i in range(to_int(sems[0])))),
        Rule('$Consecutive', 'consecutive'),
        Rule('$Even', 'even', True),
        Rule('$Even', 'odd', False),
        Rule('$Integers', 'integers'),
        Rule('$Integers', 'numbers'),
        Rule('$Sign', 'positive'),
        Rule('$Sign', 'negative'),

        Rule('$ExprList', '$Num $Consecutive $Multiples $Of $Num',
            lambda sems: tuple(varname(i) for i in range(sems[0]))),
        Rule('$Multiples', 'multiples'),

        Rule('$Parenthetical', '$Expr $Comma $Expr ?$Comma $And $Expr'),

        # MidOperator
        Rule('$Expr', '$Expr ?$Comma $MidOperator $Expr ?$Comma',
            lambda sems: (sems[2], sems[0], sems[3])),
    ])

    rules.extend([
        # Word
        Rule('$MidOperator', 'plus', '+'),
        Rule('$MidOperator', 'minus', '+'),
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
    ])

    rules.extend([
        Rule('$Expr', '$Expr ?$Comma $RevMidOperator $Expr ?$Comma',
            lambda sems: (sems[2], sems[3], sems[0])),
        Rule('$RevMidOperator', 'less than', '-'),
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
        Rule('$Expr', 'its square', ('^2', varname(0))),
        Rule('$Expr', 'its root', ('^1/2', varname(0))),

        # These examples make me uncomfortable a little.
        # Find two consecutive ints which add to 4 and 'whose product is X'
        # Can we fix coref?
        Rule('$Expr', '$Group $GroupOp', lambda sems: (sems[1], sems[0])),
        Rule('$Group', 'their_2', tuple(varname(i) for i in [0, 1])),
        Rule('$Group', 'their_3', tuple(varname(i) for i in [0, 1, 2])),
        Rule('$Group', 'whose_2', tuple(varname(i) for i in [0, 1])),
        Rule('$Group', 'whose_3', tuple(varname(i) for i in [0, 1, 2])),
        Rule('$Group', 'the_2', tuple(varname(i) for i in [0, 1])),
        Rule('$Group', 'the_3', tuple(varname(i) for i in [0, 1, 2])),

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

        Rule('$Var', 'x', varname(0)),
        Rule('$Var', 'y', varname(1)),
        Rule('$Var', 'z', varname(2)),

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

        Rule('$Var', '$PrimaryArticle ?$NumberDescriptor ?$Number', varname(0)),
        # Rule('$Var', '$PrimaryArticle ?$NumberDescriptor ?$Number', varname(1)),

        Rule('$NumberDescriptor', 'positive'),
        Rule('$NumberDescriptor', 'constant'),
        Rule('$NumberDescriptor', 'negative'),
        Rule('$NumberDescriptor', 'whole'),
        Rule('$NumberDescriptor', 'natural'),

        Rule('$Var', '$SecondaryArticle ?$NumberDescriptor ?$Number', varname(1)),
        # Rule('$Var', '$SecondaryArticle ?$NumberDescriptor ?$Number', varname(0)),
        Rule('$SecondaryArticle', 'another'),
        Rule('$SecondaryArticle', 'the other'),
        Rule('$SecondaryArticle', 'the larger'),
        Rule('$SecondaryArticle', 'the second'),
        Rule('$SecondaryArticle', 'a larger'),
        Rule('$SecondaryArticle', 'a second'),


        Rule('$Var', '$TertiaryArticle ?$NumberDescriptor ?$Number', varname(2)),
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
