"""Compile a Python subset to one expression, without dynamic code execution.

Statements become numbered continuations. A trampoline calls them iteratively,
so a long for/while loop does not consume the Python call stack.
This module is embedded in index.html by build.py and runs in Pyodide.
"""
import ast
import copy
import json


class Unsupported(ValueError):
    pass


class Scope:
    def __init__(self, compiler, body, parent=None, args=None):
        self.c, self.parent = compiler, parent
        self.env = compiler.fresh('env')
        self.locals, self.globals, self.nonlocals = set(), set(), set()
        scope = self
        class Bindings(ast.NodeVisitor):
            def visit_Name(self, n):
                if isinstance(n.ctx, (ast.Store, ast.Del)): scope.locals.add(n.id)
            def visit_FunctionDef(self, n): scope.locals.add(n.name)
            def visit_AsyncFunctionDef(self, n): scope.locals.add(n.name)
            def visit_ClassDef(self, n): scope.locals.add(n.name)
            def visit_Lambda(self, n): pass
            def visit_ListComp(self, n): pass
            visit_SetComp = visit_ListComp
            visit_DictComp = visit_ListComp
            visit_GeneratorExp = visit_ListComp
            def visit_Import(self, n):
                for a in n.names: scope.locals.add(a.asname or a.name.split('.')[0])
            def visit_ImportFrom(self, n):
                for a in n.names: scope.locals.add(a.asname or a.name)
            def visit_Global(self, n): scope.globals.update(n.names)
            def visit_Nonlocal(self, n): scope.nonlocals.update(n.names)
        visitor = Bindings()
        for n in body: visitor.visit(n)
        if args:
            self.locals.update(a.arg for a in args.posonlyargs + args.args + args.kwonlyargs)
            if args.vararg: self.locals.add(args.vararg.arg)
            if args.kwarg: self.locals.add(args.kwarg.arg)
        self.locals -= self.globals | self.nonlocals

    def owner(self, name):
        if name in self.globals or self.parent is None: return self.c.module
        if name in self.locals: return self
        return self.parent.owner(name)

    def load(self, name):
        owner = self.owner(name)
        error = 'UnboundLocalError' if owner is self and self.parent else 'NameError'
        fallback = f'{self.c.b}[{name!r}] if {name!r} in {self.c.b} else {self.c.throw}({self.c.b}["NameError"]({name!r}))'
        if owner is not self.c.module:
            fallback = f'{self.c.throw}({self.c.b}[{error!r}]({name!r}))'
        return f'({owner.env}[{name!r}] if {name!r} in {owner.env} else ({fallback}))'

    def store_env(self, name):
        return self.owner(name).env


class Compiler:
    def __init__(self, tree):
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
        self.prefix = '_one_'
        while any(n.startswith(self.prefix) for n in names): self.prefix += '_'
        self.serial = 0
        self.b, self.throw, self.run = [self.fresh(x) for x in ('builtins', 'throw', 'run')]
        self.module = Scope(self, tree.body)

    def fresh(self, label):
        self.serial += 1
        return self.prefix + label + str(self.serial)

    def fail(self, node, reason=None):
        raise Unsupported(f'Line {getattr(node, "lineno", "?")}: {reason or type(node).__name__ + " is not supported yet"}.')

    def expr(self, node, scope, native=frozenset()):
        c = self
        class Rewrite(ast.NodeTransformer):
            def __init__(self, bound): self.bound = set(bound)
            def visit_Name(self, n):
                if n.id in {'exec','eval','compile','globals','locals','vars','dir','__builtins__','__file__','__debug__','super','breakpoint'}:
                    c.fail(n, f'{n.id} is outside the supported subset (dynamic execution or scope introspection)')
                if isinstance(n.ctx, ast.Load) and n.id not in self.bound:
                    return ast.copy_location(ast.parse(scope.load(n.id), mode='eval').body, n)
                return n
            def visit_Attribute(self,n):
                if n.attr in {'exec','eval','compile','__code__','__globals__','__closure__','currentframe','_getframe','settrace','setprofile'}:
                    c.fail(n, 'Dynamic execution and frame/function introspection are not supported')
                return self.generic_visit(n)
            def visit_NamedExpr(self,n): c.fail(n, 'Assignment expressions (:=) are not supported yet')
            def visit_Yield(self,n): c.fail(n, 'Generator functions are not supported yet')
            visit_YieldFrom = visit_Yield
            def visit_Await(self,n): c.fail(n, 'Async code is not supported yet')
            def visit_Lambda(self,n):
                n.args.defaults = [self.visit(x) for x in n.args.defaults]
                n.args.kw_defaults = [self.visit(x) if x else None for x in n.args.kw_defaults]
                bound = {a.arg for a in n.args.posonlyargs+n.args.args+n.args.kwonlyargs}
                if n.args.vararg: bound.add(n.args.vararg.arg)
                if n.args.kwarg: bound.add(n.args.kwarg.arg)
                n.body = Rewrite(self.bound | bound).visit(n.body)
                return n
            def comprehension(self,n):
                inner = Rewrite(self.bound)
                for g in n.generators:
                    if g.is_async: c.fail(g, 'Async comprehensions are not supported')
                    g.iter = inner.visit(g.iter)
                    inner.bound.update(t.id for t in ast.walk(g.target) if isinstance(t,ast.Name))
                    g.ifs = [inner.visit(x) for x in g.ifs]
                if isinstance(n,ast.DictComp):
                    n.key,n.value = inner.visit(n.key),inner.visit(n.value)
                else: n.elt=inner.visit(n.elt)
                return n
            visit_ListComp = comprehension
            visit_SetComp = comprehension
            visit_DictComp = comprehension
            visit_GeneratorExp = comprehension
        result=ast.unparse(ast.fix_missing_locations(Rewrite(native).visit(ast.Name(id=node.id, ctx=ast.Load()) if isinstance(node,ast.Name) else copy.deepcopy(node))))
        return "(" + result + ")"

    def assign(self, target, value, scope):
        if isinstance(target,ast.Name):
            return f'{scope.store_env(target.id)}.__setitem__({target.id!r},{value})'
        if isinstance(target,ast.Attribute):
            return f'{self.b}["setattr"]({self.expr(target.value,scope)},{target.attr!r},{value})'
        if isinstance(target,ast.Subscript):
            key = self.slice(target.slice,scope)
            return f'({self.expr(target.value,scope)}).__setitem__({key},{value})'
        if isinstance(target,(ast.Tuple,ast.List)):
            actions=[]
            def unpack(t):
                if isinstance(t,(ast.Tuple,ast.List)):
                    return '['+','.join(unpack(x) for x in t.elts)+']'
                if isinstance(t,ast.Starred): return '*'+unpack(t.value)
                name=self.fresh('unpack')
                actions.append(self.assign(t,name,scope))
                return name
            pattern=unpack(target)
            return f'{self.b}["next"]((({",".join(actions)},None)[-1] for {pattern} in [{value}]))'
        self.fail(target,'Unsupported assignment target')

    def slice(self,n,scope):
        if isinstance(n,ast.Slice):
            parts=[self.expr(x,scope) if x else 'None' for x in (n.lower,n.upper,n.step)]
            return f'{self.b}["slice"]({",".join(parts)})'
        if isinstance(n,ast.Tuple): return '('+','.join(self.slice(x,scope) for x in n.elts)+',)'
        return self.expr(n,scope)

    #converts function to lambda expression
    def function(self,n,scope):
        if n.decorator_list or n.returns or getattr(n,'type_params',[]):
            self.fail(n,'Decorators, annotations, and type parameters are not supported yet')
        args=copy.deepcopy(n.args)
        all_args=args.posonlyargs+args.args+args.kwonlyargs+([args.vararg] if args.vararg else [])+([args.kwarg] if args.kwarg else [])
        if any(a.annotation for a in all_args): self.fail(n,'Function annotations are not supported yet')
        args.defaults=[ast.parse(self.expr(x,scope),mode='eval').body for x in args.defaults]
        args.kw_defaults=[ast.parse(self.expr(x,scope),mode='eval').body if x else None for x in args.kw_defaults]
        signature=ast.unparse(args)
        child=Scope(self,n.body,scope,args)
        init=f'{self.b}["dict"]([{",".join("("+repr(a.arg)+","+a.arg+")" for a in all_args)}])'
        value=f'(lambda {signature}:{self.program(n.body,child,init)})'
        fn=self.fresh('function')
        doc=ast.get_docstring(n,clean=False)
        return f'(lambda {fn}:({self.b}["setattr"]({fn},"__name__",{n.name!r}),{self.b}["setattr"]({fn},"__doc__",{doc!r}),{fn})[-1])({value})'
    
    
    #converts statements into lambda statemnts that return next step
    def program(self,body,scope,init):
        instructions=[]
        state=self.fresh('state')
        def add(expr):
            instructions.append(expr)
            return len(instructions)-1
        def seq(*values): return '('+','.join(values)+')[-1]'
        def block(stmts,after=None,br=None,co=None):
            k=after
            for n in reversed(stmts):
                nxt=repr(k)
                if isinstance(n,(ast.Pass,ast.Global,ast.Nonlocal)): continue
                if isinstance(n,ast.Expr): k=add(seq(self.expr(n.value,scope),nxt))
                elif isinstance(n,ast.Assign):
                    value=self.fresh('value')
                    actions=[self.assign(t,value,scope) for t in n.targets]
                    k=add(f'(lambda {value}:{seq(*actions,nxt)})({self.expr(n.value,scope)})')
                elif isinstance(n,ast.AugAssign):
                    if not isinstance(n.target,ast.Name): self.fail(n,'Augmented assignment currently requires a simple variable')
                    ops={ast.Add:'iadd',ast.Sub:'isub',ast.Mult:'imul',ast.Div:'itruediv',ast.FloorDiv:'ifloordiv',ast.Mod:'imod',ast.Pow:'ipow',ast.BitOr:'ior',ast.BitAnd:'iand',ast.BitXor:'ixor',ast.LShift:'ilshift',ast.RShift:'irshift',ast.MatMult:'imatmul'}
                    value=f'{self.b}["__import__"]("operator").{ops[type(n.op)]}({self.expr(n.target,scope)},{self.expr(n.value,scope)})'
                    k=add(seq(self.assign(n.target,value,scope),nxt))
                elif isinstance(n,ast.If):
                    yes,no=block(n.body,k,br,co),block(n.orelse,k,br,co)
                    k=add(f'({yes!r} if {self.expr(n.test,scope)} else {no!r})')
                elif isinstance(n,ast.While):
                    head=add('None')
                    yes=block(n.body,head,k,head)
                    no=block(n.orelse,k,br,co)
                    instructions[head]=f'({yes!r} if {self.expr(n.test,scope)} else {no!r})'
                    k=head
                elif isinstance(n,ast.For):
                    head=add('None')
                    it,end=self.fresh('iterator'),self.fresh('sentinel')
                    itref,endref=f'{scope.env}[{it!r}]',f'{scope.env}[{end!r}]'
                    yes=block(n.body,head,k,head)
                    tail=block(n.orelse,k,br,co)
                    no=add(seq(f'{scope.env}.pop({it!r})',f'{scope.env}.pop({end!r})',repr(tail)))
                    item=self.fresh('item')
                    instructions[head]=f'(lambda {item}:({no!r} if {item} is {endref} else {seq(self.assign(n.target,item,scope),repr(yes))}))({self.b}["next"]({itref},{endref}))'
                    k=add(seq(f'{scope.env}.__setitem__({it!r},{self.b}["iter"]({self.expr(n.iter,scope)}))',f'{scope.env}.__setitem__({end!r},{self.b}["object"]())',repr(head)))
                elif isinstance(n,ast.Break): k=br
                elif isinstance(n,ast.Continue): k=co
                elif isinstance(n,ast.Return):
                    value=self.expr(n.value,scope) if n.value else 'None'
                    k=add(seq(f'{state}.__setitem__(1,{value})','None'))
                elif isinstance(n,ast.FunctionDef): k=add(seq(self.assign(ast.Name(id=n.name),self.function(n,scope),scope),nxt))
                elif isinstance(n,ast.Import):
                    actions=[]
                    for a in n.names:
                        value=f'{self.b}["__import__"]({a.name!r},fromlist=["*"])' if a.asname else f'{self.b}["__import__"]({a.name!r})'
                        actions.append(self.assign(ast.Name(id=a.asname or a.name.split('.')[0]),value,scope))
                    k=add(seq(*actions,nxt))
                elif isinstance(n,ast.ImportFrom):
                    if n.level or n.module=='__future__' or any(a.name=='*' for a in n.names): self.fail(n,'Relative, future, and star imports are not supported')
                    if any(a.name in {'exec','eval','compile'} for a in n.names): self.fail(n,'Dynamic execution imports are not supported')
                    module=self.fresh('module')
                    actions=[self.assign(ast.Name(id=a.asname or a.name),f'{self.b}["getattr"]({module},{a.name!r})',scope) for a in n.names]
                    k=add(f'(lambda {module}:{seq(*actions,nxt)})({self.b}["__import__"]({n.module!r},fromlist={[a.name for a in n.names]!r}))')
                elif isinstance(n,ast.Raise):
                    if n.cause or not n.exc: self.fail(n,'Bare raise and raise-from are not supported')
                    k=add(f'{self.throw}({self.expr(n.exc,scope)})')
                elif isinstance(n,ast.Assert):
                    msg=self.expr(n.msg,scope) if n.msg else ''
                    k=add(f'({nxt} if {self.expr(n.test,scope)} else {self.throw}({self.b}["AssertionError"]({msg})))')
                else: self.fail(n)
            return k
        entry=block(body)
        code='['+','.join('(lambda:'+x+')' for x in instructions)+']'
        return f'(lambda {scope.env}:(lambda {state}:{self.run}({code},{state}))([{entry!r},None]))({init})'
    
    #combines everything into one expression with iterative runner
    def compile(self,tree):
        program=self.program(tree.body,self.module,f'{self.b}["dict"](__name__="__main__")')
        steps,state,unused=[self.fresh(x) for x in ('steps','state','unused')]
        runner=f'(lambda {steps},{state}:({self.b}["all"](({state}.__setitem__(0,{steps}[{state}[0]]()),True)[1] for {unused} in {self.b}["iter"](lambda:{state}[0],None)),{state}[1])[1])'
        error=self.fresh('error')
        thrower=f'(lambda {error}: (_ for _ in ()).throw({error}))'
        result=f'(lambda {self.b}:(lambda {self.throw},{self.run}:{program})({thrower},{runner}))(__import__("builtins").__dict__)'
        result=ast.unparse(ast.parse(result,mode='eval'))
        if '\n' in result or '\r' in result: raise Unsupported('This source cannot be rendered on one physical line.')
        return result

#Parses Python into a syntax tree
def reduce_python(source):
    try:
        tree=ast.parse(source)
        compile(tree,'<input>','exec')  # Syntax/context validation only; submitted code is never run.
        if not tree.body: raise Unsupported('Paste some Python code first.')
        result=Compiler(tree).compile(tree)
        return json.dumps({'ok':True,'code':result})
    except (SyntaxError,Unsupported,RecursionError,ValueError) as e:
        return json.dumps({'ok':False,'error':str(e)})
