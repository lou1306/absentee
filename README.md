# Absentee 👤

Absentee (A Bare-bones C iNstrumenter/Transformer)
is a collection of common (and less so) source-to-source
transformations for C.
So far, it can:

* Rename/remove function calls
* Change type declarations (e.g. change all `char`s to `int`s)
* Remove `typedef`s
* Replace arithmetic operators (e.g., & -> &&)
* Prepend/append custom code to the input program (e.g., preprocessor directives)
* Turn an array-based program in an array-free equivalent

## Basic usage

`absentee` takes as input a C program and a configuration file, which specifies
the transformations to be performed:

```bash
$ python3 -m absentee --conf path/to/conf path/to/file
```

The result is printed to standard output: use output redirection `>` to save
the result to a file.

You may check out further options with `-h` or `--help`:

```
$ python -m absentee --help
Usage: python - m absentee [OPTIONS] FILE

  absentee C transformation tool

Options:
  --conf PATH  The path to the configuration file.
  --show-ast   Show the syntax tree of FILE and exit.  [default: False]
  --version    Show the version and exit.
  -h, --help   Show this message and exit.
```

## Example configuration 

Configurations are in a simplified s-expression format. Here is an example:

```lisp
; Print code before the input program
(prepend "int pow2(int x) { return x * x; }")
; Change all char variables to int
(retype (char int))
; Remove the 2nd and 4th argument from all calls to function f
(removeArgs (f 1 3)) ; indices are 0-based
(renameCalls 
  (f g) ; Turn all calls to f into calls to g 
  (badfunction ()) ; Remove all calls to badfunction
)
```

## Known limitations

Absentee is based on [pycparser](https://github.com/eliben/pycparser).
This means that:

* C extensions are unsupported.

* Absentee's input file must be preprocessed.
  As a consequence, `absentee`'s output will lack comments, preprocessor
  directives, etc. that were present in the original source code.
  One can preprocess a generic C file (with `gcc -E`, for instance) and feed
  the output to `absentee` like this:

~~~bash
gcc -E program.c | ./absentee.py - --conf <...>
~~~

## Similar software

Absentee shares some similarities with [Coccinelle](http://coccinelle.lip6.fr/).
Coccinelle aims at handling collateral evolution (such as API changes) and
automated bug finding/fixing.
Absentee's goal, on the other hand, is to automate instrumentation of code for
analysis purposes.

[CIL](https://cil-project.github.io/cil/) is a subset of C for program analysis
and transformation, and a tool to reduce arbitrary C programs into said
subset. The tool, however, seems to be hardly maintained anymore.
