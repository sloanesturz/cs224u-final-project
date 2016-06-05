import re
import json
import sys

from collections import defaultdict
from collections import Counter
import collections
from numbers import Number
from itertools import chain, product
import operator
from random import randint

from domain import Domain
from example import Example
from experiment import evaluate_for_domain, evaluate_dev_examples_for_domain, train_test, train_test_for_domain, interact, learn_lexical_semantics, generate
from metrics import DenotationAccuracyMetric
from parsing import Grammar, print_grammar, compute_semantics
from scoring import rule_features

from nltk.tree import Tree
from solver import SympySolver
import wordprob_rules


def str2tree(s):
    return Tree.fromstring(s)

def format_text(question):
    split = re.findall(r"[A-Za-z\-']+|[.,!?;/=+*]|-?\d+", question.lower())
    text = " ".join(split)
    text = text.replace('. .', '.')
    return text

def find_number_variables(text):
    split = text.split()
    consecutive, even, count = False, None, None
    for i, word in enumerate(split):
        if word in ["numbers", "integers"]:
            if i == 0 or split[i-1] == "the": continue
            for desc in split[max(0, i-4):i]:
                if desc == "consecutive":
                    consecutive = True
                elif desc == "even":
                    even = True
                elif desc == "odd":
                    even = False
                elif desc in ["2", "two"]:
                    count = 2
                elif desc in ["3", "three"]:
                    count = 3
                elif desc in ["4", "four"]:
                    count = 4
            if count is None:
                count = 1
            return consecutive, even, count
    if count == None:
        if 'another' in split:
            return False, None, 2
    return None, None, 1

def replace_ambiguity(text):
    prefix = ['their', 'whose']
    op = ['sum', 'difference', 'product']

    consecutive, even, count = find_number_variables(text)

    for p, o in product(prefix, op):
        q = "%s %s" % (p, o)
        if q in text:
            text = text.replace(q, "%s_%s %s" % (p, count, o))

    return text

def preprocess(question):
    text = format_text(question)
    text = replace_ambiguity(text)
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

def is_variable(varname):
    if not isinstance(varname, str):
        return False
    return bool(re.match(r'v-?\d+', varname))

def translate_variable(varname, numvars):
    if not is_variable(varname):
        raise ValueError('%s is not a variable' % varname)
    i = int(varname[1:])
    if i < 0:
        i = numvars - i
    return "v%s" % i

UNARY_OPS = set(['^2', '^3', '^(-1)', '^(1/2)'])
def convertSemanticsToEqn(semantics, numvars):
    if (type(semantics) is int) or \
            (type(semantics) is str) or \
            (type(semantics) is float):
        # base case
        if is_variable(semantics):
            return translate_variable(semantics, numvars)
        else:
            return str(semantics)
    elif len(semantics) == 1:
        # collapse nested tuples
        return convertSemanticsToEqn(semantics[0], numvars)

    # handle operators
    if semantics[0] in UNARY_OPS:
        return "(" + convertSemanticsToEqn(semantics[1], numvars) + semantics[0] + ")"
    else:
        if len(semantics) == 2:
            op = semantics[0]
            arguments = ["(" + convertSemanticsToEqn(s, numvars) + ")"
                        for s in semantics[1]]
            return "(" + op.join(arguments) + ")"
        else:
            op = semantics[0]
            arguments = ["(" + convertSemanticsToEqn(s, numvars) + ")"
                        for s in semantics[1:]]
            return "(" + op.join(arguments) + ")"

def getConsecutiveConstraints(count, consecutive, even):
    start, mult = 0, 1
    if even == False:
        start = 1
        mult = 2
    if even == True:
        mult = 2
    return ["v%s = %s * k + %s" % (i, mult, start + mult*i)
        for i in range(count)]


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

    def split_semantics(self, semantics):
        numvars, consecutive, even = None, None, None
        for i, s in enumerate(semantics):
            if len(s) != 2 or s[0] == '=':
                break
            if s[0] == 'numvars':
                numvars = int(s[1])
            if s[0] == 'consecutive':
                consecutive = s[1]
            if s[0] == 'even':
                even = s[1]

        return numvars, consecutive, even, semantics[i:]

    def execute(self, semantics):
        solver = SympySolver()
        answers = []
        semantics = self.flatten_list([semantics])
        count, consecutive, even, semantics = self.split_semantics(semantics)
        final_eqns = [convertSemanticsToEqn(semantic, count) for semantic in semantics]
        if consecutive:
            final_eqns.extend(getConsecutiveConstraints(count, consecutive, even))

        num_vars = solver.count_variables(final_eqns)
        answers = solver.our_evaluate(final_eqns, count, consecutive, "-")

        # print answers
        return answers

    def rules(self):
        return wordprob_rules.load_rules()

    def grammar(self):
        class WordProbGrammar(Grammar):
            def parse_input(self, input):
                parses = Grammar.parse_input(self, input)
                consecutive, even, count = find_number_variables(input)

                for parse in parses:
                    if isinstance(parse.semantics, tuple):
                        parse.semantics = [parse.semantics]
                    parse.semantics.insert(0, ('numvars', count))
                    if consecutive:
                        parse.semantics.insert(0, ('consecutive', True))
                    if even == True or even == False:
                        parse.semantics.insert(0, ('even', even))
                return parses
        return WordProbGrammar(rules=self.rules(), start_symbol='$E')

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

def answeredCorrectly(gold_list_of_answers, list_of_answers, strictness="loose"):
    for gold_answer_set in gold_list_of_answers:
        for our_answer_set in list_of_answers:
            if strictness == 'tight':
                # we need a direct match to count the answer as correct
                if gold_answer_set == our_answer_set:
                    return True
            else:
                # our answer can be a subset of the actual answers or vice-versa
                if gold_answer_set == our_answer_set or \
                        gold_answer_set.issubset(our_answer_set):
                    return True

    return False

def filterResultsToOneAnswer(gathered_answers, question):
    if len(gathered_answers) <= 1: 
        return formatOurAnswers(gathered_answers)

    stats = Counter([str(x) for x in gathered_answers if "/" not in str(x)])  # filter out answers with a '/' sign
    top_answers = [key for key,val in stats.iteritems() if val == max(stats.values())]

    our_answer_set = set()
    if len(top_answers) == 1:
        # we only have one answer: we can convert it to the right format
        our_final_answer = []
        [our_final_answer.append(x) for x in gathered_answers if str(x) in top_answers and x not in our_final_answer]
        our_answer_set = formatOurAnswers(our_final_answer)
    else:
        # we need to narrow down our answers
        our_final_answers = []
        # general metrics to filter results: if we see a '-' in an answer, we'don't include that answer
        [our_final_answers.append(x) for x in gathered_answers if str(x) in top_answers and "-" not in str(x) and x not in our_final_answers]
        if len(our_final_answers) > 1:
            # if we still have too many, we randomnly guess
            random_index = randint(0,len(our_final_answers) - 1)
            our_final_answers = our_final_answers[random_index]

        our_answer_set = formatOurAnswers(our_final_answers)

    return our_answer_set

def check_parses():
    with open('curated-data/non-yahoo-questions-dev-no-repetitions.json') as f:
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
                gathered_answers = []
                for _, v in {str(s): s for s in [p.semantics for p in parses]}.iteritems():
                    try:
                        answer = domain.execute(v)
                        # don't include empty answers in our list of gathered_answers
                        if len(answer) != 0: gathered_answers.append(answer)
                    except Exception as e:
                        print example['text']
                        import traceback; print traceback.format_exc()
                        raise e

                our_best_result = filterResultsToOneAnswer(gathered_answers, example["text"])

                print example["text"]
                print "\t", "Gold answer(s): " + str(gold_list_of_answers)
                print "\t", "We generated %s solutions" % len(gathered_answers)
                print "\t", "Our answer(s): " + str(gathered_answers)
                print "\t", "Our best answer: " + str(our_best_result)
                if answeredCorrectly(gold_list_of_answers, our_best_result):
                    print "\t", "Our best answer was correct!!!!!!!\n"
                    succ_solve += 1
                else:
                    print "\t", "We got the problem wrong :(\n"


        print "success parses", 100. * succ_parse / (len(examples))
        print "success solve", 100. * succ_solve / (len(examples))

if __name__ == "__main__":
    domain = WordProbDomain()
    grammar = domain.grammar()

    input = " ".join(sys.argv[1:])
    if '--check-parses' in sys.argv:
        check_parses()
    elif input:
        text = preprocess(input)
        print text
        parses = grammar.parse_input(text)

        print "Number of parses: {0}".format(len(parses))
        for _, v in {str(s): s for s in [p.semantics for p in parses]}.iteritems():
            print domain.execute(v)
        if len(parses) == 0:
            print 'no parses'
    else:
        # Running this is sad and will make you unhappy :(
        evaluate_dev_examples_for_domain(WordProbDomain())
