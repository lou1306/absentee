
# bzip2.i

This file was generated from a single-file version of `bzip2`, found at
[S. McCamant's personal website](https://people.csail.mit.edu/smcc/projects/single-file-programs/),
with the following call to the GCC9 preprocessor:


```bash
gcc -nostdinc -U__GNUC__  -D'__attribute__='  -D'__inline__='  -E -I{path/to}/pycparser/utils/fake_libc_include examples/bzip2.c > examples/bzip2.i
```

Let us explain these arguments:

* `-nostdinc`: do not look for headers in the default paths
* `-U__GNUC__`: un-define the `__GNUC__` name, so as to avoid stuff such as
  `noreturn`
* `-D__attribute__=`, `-D__inline__`: defines `__attribute__` and `__inline__`
  to be the empty string, so they will not appear in the processed file
* `-E`: quit GCC after running the preprocessor
* `-I...`:  add the `pycparser` fake stdlib headers ([more info here](https://eli.thegreenplace.net/2015/on-parsing-c-type-declarations-and-fake-headers)). Notice that you have to provide the actual path

