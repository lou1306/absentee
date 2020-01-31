# A bare-bones C transformer

Absentee is a collection of common (and less so) source-to-source
transformations for C.
So far, it can:

* Rename function calls
* Change type decarations (e.g. change all `char`s to `int`s)
* Remove `typedefs`
* Replace operators (e.g., & -> &&)
* Add preprocessor directives
* Turn an array-based program in an array-free equivalent

## Basic usage

`absentee` takes as input a C program and a configuration file in the
[`toml` format](https://github.com/toml-lang/toml), which specifies
the transformations to be performed.

## Known limitations

Absentee is based on [pycparser](https://github.com/eliben/pycparser).
This means that:

* C extensions are unsupported.

* Absentee's input file must be preprocessed.
  As a consequence, `absentee`'s output will lack comments, preprocessor
  directives, etc. that were present in the original source code.
  One can preprocess a generic C file (with `gcc -E`, for instance) and feed
  the output to `absentee` like this:

~~~
gcc -E program.c | ./absentee.py - --conf <...>
~~~


## Similar software

Absentee shares some similarities with [Coccinelle](coccinelle.lip6.fr/).
Coccinelle aims at handling collateral evolution (such as API changes) and
automated bug finding/fixing.
Absentee's goal, on the other hand, is automated instrumentation of code for
analysis purposes.

[CIL](https://cil-project.github.io/cil/) is a subset of C for program analysis
and transformation.
