import sys
sys.path.insert(0, '.\sympy')

import sympy
from sympy import Symbol, solveset, sympify
from sympy.parsing.sympy_parser import parse_expr

def _convertToRightForm(eqn_as_string):
	index_of_equal_signs = eqn_as_string.find("==")
	final_form = eqn_as_string[0:index_of_equal_signs] + "-" + eqn_as_string[index_of_equal_signs + 2:]
	return final_form

class SympySolver():

	def our_evaluate(self, eqn_as_string):
		converted_eqn_as_string = _convertToRightForm(eqn_as_string)
		eqn = sympify(converted_eqn_as_string)
		print eqn
		x = Symbol('x')
		print solveset(eqn, x)