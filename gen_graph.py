from matplotlib import pyplot as plt
from collections import Counter

from wordprob_rules import load_rules

# count rules and sort value
rules = load_rules()
counter = Counter(r.lhs for r in rules)
s = sorted([(k, v) for v, k in counter.iteritems()])

# plottable values
x = range(len(s))
counts, name = zip(*s)

# make the graph
plt.xticks(x, name, rotation='vertical')
plt.semilogy(x, counts)
plt.tight_layout()
plt.show() # save from GUI
