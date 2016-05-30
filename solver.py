import sys
sys.path.insert(0, '.\sympy')

import sympy
from sympy import Symbol, solveset, sympify, solve
from sympy.parsing.sympy_parser import parse_expr

# helper function that
def formattedString(eqn_as_string):
	index_of_equal_signs = eqn_as_string.find("==")
	final_form = eqn_as_string[0:index_of_equal_signs] + "-" + eqn_as_string[index_of_equal_signs + 2:]
	return final_form

# helper function that iterates over all the equations and converts them into
# the proper form as sympy expressions
def convertToSympyExprs(final_eqns):
	exprs = []
	for eqn in final_eqns:
		sympy_expr = sympify(formattedString(eqn))
		exprs.append(sympy_expr)
	if len(final_eqns) == 1:
		return exprs[0]
	else:
		return exprs

def createSymbols(num_variables):
	sympy_symbols = []

	possible_symbols = ['x', 'y', 'z']
	for i in range(0, num_variables):
		# create sympy symbol
		cur_symbol = Symbol(possible_symbols[i])
		sympy_symbols.append(cur_symbol)

	return sympy_symbols

class SympySolver():

	def our_evaluate(self, final_eqns, num_variables):
		sympy_exprs = convertToSympyExprs(final_eqns)
		print sympy_exprs
		symbols = createSymbols(num_variables)
		
		return solve(sympy_exprs, symbols)  # unpack symbols into parameters