import sys
sys.path.insert(0, '.\sympy')

import sympy
from sympy import Symbol, solveset, sympify, solve
from sympy.parsing.sympy_parser import parse_expr
from sympy.core.sympify import SympifyError
from sympy.printing.pretty.pretty import pretty_print

import re

# helper function that
def formattedString(eqn_as_string):
	index_of_equal_signs = eqn_as_string.find("=")
	final_form = eqn_as_string[0:index_of_equal_signs] + "-" + "(" + eqn_as_string[index_of_equal_signs + 1:] + ")"
	return final_form

# helper function that iterates over all the equations and converts them into
# the proper form as sympy expressions
def convertToSympyExprs(final_eqns):
	exprs = []
	for eqn in final_eqns:
		try:
			sympy_expr = sympify(formattedString(eqn))
			exprs.append(sympy_expr)
		except (SympifyError) as e:
			return "Error thrown"

	if len(final_eqns) == 1:
		return exprs[0]  # only one equation to solve
	else:
		return exprs  # set of equations to solve

def dealWithConsecutives(answer_for_k, final_eqn_as_string):
	term_answers = []
	# case: final_eqn is in the form (2*x+1) + (2*x+3) + (2*x+5')
	# extract out the final terms we need to solve for (i.e. (2*x+1))
	terms = re.findall('\([\d|*|\-|+|\/|\w]*\)', str(final_eqn_as_string), flags=re.I)
	for term in terms:
		sympy_expr = sympify(term)  # turn term into a sympy expression
		term_answer = sympy_expr.subs(Symbol('k'), answer_for_k)  # subsitute answer for x into term
		term_answers.append(term_answer)

	return term_answers

def createSymbols(num_variables, is_consecutive):
	if is_consecutive:
		return Symbol('k')
	sympy_symbols = []

	possible_symbols = ['x', 'y', 'z']
	for i in range(0, num_variables):
		# create sympy symbol
		cur_symbol = Symbol(possible_symbols[i])
		sympy_symbols.append(cur_symbol)

	return sympy_symbols

class SympySolver():

	def our_evaluate(self, final_eqns, num_variables, is_consecutive):
		sympy_exprs = convertToSympyExprs(final_eqns)
		if sympy_exprs == "Error thrown":
			return []
		
		symbols = createSymbols(num_variables, is_consecutive)

		answers = solve(sympy_exprs, symbols)  # unpack symbols into parameters
		if is_consecutive:
			# dealing with a "consecutive" type of problem with only one equation
			# we need to return answers for all terms! Not the answer for x
			answers = dealWithConsecutives(answers[0], final_eqns)

		# we need to get the output into a format that we can compare with
		# the answers in the json file
		answer_array = []
		if type(answers) is dict:
			for variable, answer in answers.iteritems():
				answer_array.append(answer)
		else:
			# case: answers is a list with the right answers
			answer_array = answers

		return answer_array


	def count_variables(self, eqns):
		observed_vars = set()
		for eqn in eqns:
			observed_vars.update(self.count_variables_helper(eqn))
		return len(observed_vars)

	def count_variables_helper(self, fragment):
		observed_vars = set()
		for t in fragment:
			if type(t) == tuple:
				observed_vars.update(self.count_variables_helper(t))
			if type(t) == str:
				if t in ['x', 'y', 'z', 'k']:
					observed_vars.add(t)
		return observed_vars
