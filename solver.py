import sys
sys.path.insert(0, '.\sympy')

import sympy
from sympy import Symbol, solveset, sympify, solve
from sympy.parsing.sympy_parser import parse_expr
from sympy.core.sympify import SympifyError
from sympy.printing.pretty.pretty import pretty_print

import re

# helper function that
def formattedString(eqn_as_string, op):
	index_of_equal_signs = eqn_as_string.find("=")
	final_form = eqn_as_string[0:index_of_equal_signs] + op + "(" + eqn_as_string[index_of_equal_signs + 1:] + ")"
	return final_form

# helper function that iterates over all the equations and converts them into
# the proper form as sympy expressions
def convertToSympyExprs(final_eqns, op):
	exprs = []
	for eqn in final_eqns:
		try:
			sympy_expr = sympify(formattedString(eqn, op))
			exprs.append(sympy_expr)
		except (SympifyError) as e:
			print e
			return "Error thrown"

	if len(final_eqns) == 1:
		return exprs[0]  # only one equation to solve
	else:
		return exprs  # set of equations to solve

def dealWithConsecutives(answers_for_k, final_eqn_as_string):
	term_answers = []
	# case: final_eqn is in the form (2*x+1) + (2*x+3) + (2*x+5')
	# extract out the final terms we need to solve for (i.e. (2*x+1))
	terms = re.findall('\([\d|*|\-|+|\/|\w]*\)', str(final_eqn_as_string), flags=re.I)
	for answer_for_k in answers_for_k:
		# if we have more than one answer for k, we want to solve
		# for the terms for each answer of k
		temp = []
		for term in terms:
			sympy_expr = sympify(term)  # turn term into a sympy expression
			term_answer = sympy_expr.subs(Symbol('k'), answer_for_k)  # subsitute answer for x into term
			temp.append(term_answer)

		# each answer_for_k generates its own list of answers, we then store
		# all lists of answers in the list of term_answers
		term_answers.append(temp)

	return term_answers

def createSymbols(num_variables, is_consecutive):
	symbols = [Symbol('v%s' % i) for i in range(num_variables)]
	if is_consecutive:
		symbols = [Symbol('k')] + symbols
	return symbols

class SympySolver():

	def our_evaluate(self, final_eqns, num_variables, is_consecutive, op):
		sympy_exprs = convertToSympyExprs(final_eqns, op)
		if sympy_exprs == "Error thrown" or ">" in str(sympy_exprs) or "<" in str(sympy_exprs):
			# we can't yet handle questions that contain less than or greater than
			return []

		symbols = createSymbols(num_variables, is_consecutive)
		answers = solve(sympy_exprs, symbols)  # unpack symbols into parameters

		if isinstance(answers, dict):
			try:
				return sorted([v for k, v in answers.iteritems() if k.name[0] == 'v'])
			except:
				# Impossible to know for sure, but this probably means we didn't find an answer
				return []
		elif isinstance(answers, list):
			return []

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
