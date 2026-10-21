import ast
import contextlib
import io
import json
import unittest
from compiler import reduce_python

CASES = {
'factorial': '''def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
for i in range(1, 7):
    print(factorial(i))
''',
'long_loops': '''total = 0
for i in range(10000):
    total += i
j = 0
while j < 10000:
    j += 1
print(total, j)
''',
'break_continue_else': '''for i in range(6):
    if i == 2:
        continue
    if i == 4:
        break
    print(i)
else:
    print('bad')
for j in []:
    print('bad')
else:
    print('empty')
i=0
while i < 4:
    i+=1
    if i==2:
        continue
    print(i)
else:
    print('done')
''',
'closures': '''x = 100
def outer(x):
    def inner(y=2):
        nonlocal x
        x += y
        return x
    return inner
f = outer(4)
print(f(), f(3), x)
def change():
    global x
    x = 9
change()
print(x)
''',
'args': '''def f(a, /, b=2, *args, c=4, **kwargs):
    return a,b,args,c,kwargs
print(f(1,3,5,6,c=7,d=8))
''',
'comprehensions': '''x=10
print([x*x for x in range(5) if x%2==0], x)
print({i: j for i in range(2) for j in range(i+1)})
print(sum(i for i in range(10)))
f=lambda x: x+1
print(f(2))
''',
'imports_unicode': '''import math
from collections import Counter
print(math.sqrt(9), Counter('café 🐍'))
''',
'unpack': '''a, *b, c = range(5)
print(a,b,c)
for i, (x,y) in enumerate([(1,2),(3,4)]):
    print(i,x,y)
a=[0,1,2,3]
a[1:3]=[8,9]
print(a)
''',
'mutation': '''x=[]
y=x
x += [1,2]
print(y, x is y)
a=b=[]
a.append('a')
print(a is b,b)
''',
'early_return': '''def f(n):
    for i in range(n):
        if i==3:
            return i
    return -1
print(f(10), f(2))
''',
'default_time': '''x=[]
def f(a=x):
    a.append(1)
    return a
x=[3]
print(f(),f(),x)
''',
'nested_loops': '''for i in range(3):
    for j in range(3):
        if j==1:
            break
        print(i,j)
    else:
        print('bad')
print('end')
''',
'name_collision': '''_one_builtins1 = 7
all = 2
iter = 3
next = 4
print(_one_builtins1, all, iter, next)
''',
'false_values': '''def f(x):
    if x:
        return False
    return 0
print(f(True), f(False))
''',
'strings': '''s = """a
b: ' c"""
print(s, {'key': s}["key"])
''',
}

class Tests(unittest.TestCase):
    def transform(self,source):
        data=json.loads(reduce_python(source))
        self.assertTrue(data['ok'],data.get('error'))
        output=data['code']
        self.assertNotIn('\n',output)
        self.assertNotIn('\r',output)
        tree=ast.parse(output,mode='eval')
        for n in ast.walk(tree):
            self.assertFalse(isinstance(n,ast.stmt))
            if isinstance(n,ast.Name): self.assertNotIn(n.id,{'exec','eval','compile'})
        return output
    def run_code(self,code):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream): exec(code,{'__name__':'__main__'})
        return stream.getvalue()
    def test_equivalence(self):
        for name,source in CASES.items():
            with self.subTest(name=name):
                self.assertEqual(self.run_code(source),self.run_code(self.transform(source)))
    def test_failures(self):
        for source in ['class A: pass','try:\n    pass\nexcept: pass','async def f(): pass','exec("print(1)")','x := 2','return 1','def f():\n    yield 1','from builtins import eval as e']:
            with self.subTest(source=source): self.assertFalse(json.loads(reduce_python(source))['ok'])
    def test_exception_types(self):
        for source,kind in [('print(missing)',NameError),('x=3\ndef f():\n    print(x)\n    x=1\nf()',UnboundLocalError),('assert False, "test"',AssertionError),('raise ValueError("hi")',ValueError)]:
            with self.subTest(source=source):
                with self.assertRaises(kind): self.run_code(self.transform(source))

if __name__=='__main__': unittest.main()
