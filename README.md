# One-line Python compiler

Open `index.html` in a modern browser. Paste Python or upload a UTF-8 `.py` file, then choose **Reduce to one line**. Copy the expression or download a `.oneline.py` file.

The HTML contains the compiler, UI, and runtime. It bundles the pinned Pyodide 314.0.7 runtime directly in the HTML, so no internet connection or local server is required. The self-contained file is approximately 19 MB. Local files compile on the main thread using inline runtime scripts, avoiding blocked workers and blob-module imports. HTTP pages use a worker when available and automatically fall back to the same no-worker mode on startup failure. Source is neither uploaded nor executed. Compatibility mode may briefly pause the page for larger inputs. The resulting Python expression has no Pyodide dependency.

## Transformation

Python's AST is translated to numbered continuations (small lambda functions). Each continuation returns the number of the next instruction. A trampoline executes them iteratively, keeping loops independent of Python's recursion limit. Function calls retain ordinary Python recursion limits. Lexical environment dictionaries implement variable bindings and closures.

The result is parsed as a single Python expression before delivery. It contains no generated `exec`, `eval`, bytecode-construction, or encoded-source wrapper, and no statement-block syntax. Lambda, dictionary, slice and formatting colons may appear. This reduces line count, not output size.

## Scope

Supports assignments (including unpacking and attribute/subscript writes), arithmetic and other expressions, comprehensions, lambdas, branches, loops with break/continue/else, function definitions and calls, defaults and keyword/variadic arguments, closures, global/nonlocal bindings, imports, return, assert, and explicit raise.

Rejects classes, decorators, annotations, async, generator functions, try/except/finally, with, match, del, walrus expressions, relative/star/future imports, bare raise and raise-from, and attribute/subscript augmented assignments. Unsupported syntax is rejected even when unreachable. There is no automatic wrapper fallback.

Not all Python semantics are preserved: function metadata and inspection, pickling functions, frame and module-global inspection, self-reading source, stack traces and object-finalization timing differ. Assertions remain active under `-O`. A `StopIteration` escaping a translated statement may become `RuntimeError` because the trampoline uses a generator. The source is treated as a standalone `__main__` program, not as code that mutates an existing external namespace. Files and dependencies still need to exist in the execution environment. Use Python 3.14 for syntax compatibility with the bundled parser.

## Development

- `compiler.py`: readable Python compiler.
- `index.template.html`: UI template.
- `runtime-loader.js`: worker and no-worker runtime initialization.
- `node test_runtime_loader.mjs`: loader fallback regression tests (requires Node).
- `python3 build.py`: embeds the compiler into `index.html`.
- `python3 -m unittest -v test_compiler`: execution-equivalence, output-syntax, rejection, and exception checks.

`index.html` is the only project file needed to use the app; the other files are for maintenance and testing.

## Bundled runtime

The unmodified runtime files in `vendor/pyodide/` were downloaded from `https://cdn.jsdelivr.net/pyodide/v314.0.7/full/`. Their hashes are recorded in `vendor/pyodide/manifest.json`. Pyodide is licensed under MPL-2.0; see the included `LICENSE`. Its corresponding source is available at https://github.com/pyodide/pyodide/tree/314.0.7. The HTML includes this notice and license.

Runtime requests inside the worker are resolved to bundled bytes rather than the network. The emitted Python code remains a lambda/continuation expression with no dynamic execution wrapper.
