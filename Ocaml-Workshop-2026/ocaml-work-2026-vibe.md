---
title: Running a Large OCaml Application in the Browser, Porting MOPSA to WebAssembly
author: Réda Boudrouss
date: \today
---

\maketitle

\begin{abstract}

WebAssembly has become a practical compilation target for OCaml programs,
yet most existing approaches assume that applications are either pure
OCaml or rely on only a small number of native stubs. Large OCaml
applications often depend on extensive C and C++ codebases connected
through the OCaml foreign function interface (FFI), making direct
compilation substantially more challenging.

This paper presents the port of MOPSA, a static analyzer for C and Python
written primarily in OCaml, to WebAssembly. Rather than translating only
the OCaml code, our approach compiles the complete native stack---the
OCaml bytecode runtime, C stubs, CamlIDL-generated bindings, LLVM/Clang,
and numerical libraries such as GMP, MPFR and Apron---into a single
WebAssembly module using Emscripten.

We describe the resulting architecture, discuss the modifications
required to preserve OCaml's runtime interface in a wasm32 environment,
and report on several issues uncovered during the port, including
subtle ABI assumptions inside the runtime itself. The resulting system
runs entirely client-side inside a web browser while preserving the
existing implementation of MOPSA with only limited source-level changes.

\end{abstract}

# Introduction

Running static analysis tools directly inside a web browser has several
practical advantages. Installation becomes unnecessary, analyses execute
entirely on the client machine, and source code never leaves the user's
computer. Such properties are particularly attractive for educational
platforms, interactive demonstrations, and lightweight development
environments.

Unfortunately, bringing an existing OCaml application to the browser is
not always straightforward. While projects such as
\texttt{js\_of\_ocaml}, \texttt{wasm\_of\_ocaml}, and more recently
\texttt{wasocaml}, provide compelling solutions for OCaml code itself,
they generally assume that native dependencies are either absent,
minimal, or can be replaced by JavaScript implementations.

MOPSA is almost the opposite of such an application. Although most of
its implementation is written in OCaml, its execution relies on a large
collection of native libraries connected through the OCaml foreign
function interface. These include numerical libraries (GMP, MPFR,
Apron), generated CamlIDL bindings, and a substantial C++ frontend based
on LLVM and Clang. Many of these components do more than merely expose C
functions to OCaml: they directly manipulate OCaml heap objects,
allocate values inside the garbage-collected heap, and therefore depend
on the exact representation of OCaml values in memory.

This extensive use of the FFI makes approaches based solely on compiling
the OCaml code insufficient. Replacing the native components with
JavaScript glue would require rewriting thousands of lines of existing C
and C++ code while preserving complex interactions with the OCaml
runtime.

Instead, we adopt a different strategy. Rather than translating only the
OCaml program, we compile the entire execution environment to
WebAssembly. The OCaml compiler produces bytecode, while the bytecode
interpreter, the OCaml runtime, every native dependency, and all FFI
stubs are compiled with Emscripten into a single statically linked wasm
module. The original application therefore executes almost unchanged,
inside an unmodified OCaml bytecode runtime running in the browser.

The contribution of this paper is not a new compiler or runtime.
Instead, it is an experience report describing how a large OCaml
application with more than a thousand native primitives can be executed
entirely client-side. We discuss the architectural choices behind this
approach, the adaptations required to support the OCaml runtime on
wasm32, and several unexpected issues encountered during the port,
including a previously unnoticed assumption in the OCaml runtime's
implementation of value headers.

The remainder of the paper is organized as follows. Section~2 presents
the architecture of MOPSA and motivates the compilation strategy.
Section~3 describes the construction of the WebAssembly runtime and the
native dependency stack. Section~4 discusses the main technical
challenges encountered during the port. Section~5 reports on the final
system and its current limitations before concluding.


# Architecture and Design Choices

## MOPSA as a Case Study

MOPSA is a static analyzer based on abstract interpretation capable of
analyzing both C and Python programs. Although most of its implementation
is written in OCaml, the analyzer relies on a substantial native software
stack.

Figure~\ref{fig:deps} summarizes the main components involved during
execution. Besides the OCaml code itself, MOPSA depends on GMP and MPFR
for arbitrary-precision arithmetic, Apron for numerical abstract
domains, CamlIDL-generated bindings between OCaml and C, and a C++
frontend built on LLVM and Clang to parse C programs.

![Dependency graph of the native components used by MOPSA.](mopsa_deps.pdf){#fig:deps width=90%}

Unlike many OCaml projects, these native components are not isolated
libraries invoked through a narrow API. Instead, they make extensive use
of the OCaml foreign function interface. Generated CamlIDL bindings,
Apron stubs, and MOPSA's own Clang frontend allocate OCaml objects,
inspect heap blocks, invoke OCaml callbacks, and manipulate runtime
values directly.

Consequently, these components are tightly coupled to the OCaml runtime
representation. They do not merely depend on the existence of exported C
functions such as \texttt{caml\_alloc}; they also assume a compatible
runtime layout, garbage collector, and value representation.

## Why Existing OCaml-to-WebAssembly Approaches Were Not Enough

Several projects already make it possible to execute OCaml programs
inside web browsers.

The most mature approaches, such as \texttt{js\_of\_ocaml} and
\texttt{wasm\_of\_ocaml}, focus on translating OCaml programs while
leaving native components outside the generated code. This design works
well for applications whose dependencies are either implemented entirely
in OCaml or whose native portions can be replaced by JavaScript
implementations.

For MOPSA, this assumption does not hold.

One possibility would have been to rewrite the native interface in
JavaScript, replacing the C++ frontend and the generated FFI stubs with
equivalent browser-side implementations. Besides representing a
substantial engineering effort, this would duplicate complex code already
maintained upstream and introduce a second implementation that would have
to remain synchronized with the original project.

Another possibility would have been to combine independently compiled
OCaml and Emscripten modules. However, this requires reconciling two
independent execution environments, each maintaining its own memory
representation, allocator, and runtime conventions. Every call crossing
the OCaml/C boundary would require additional glue code.

Our objective was instead to preserve the existing implementation as much
as possible. Ideally, every OCaml module, every C stub, and every C++
translation unit should be compiled without semantic modifications and
linked together into a single executable.

## Choosing the Bytecode Runtime

The key observation is that the OCaml bytecode runtime already provides
the execution environment expected by native FFI stubs.

When compiling OCaml to bytecode, calls to external primitives are not
resolved statically. Instead, the generated bytecode records the names of
required primitives, and the bytecode interpreter resolves them when the
program starts. Native stubs therefore expect to execute alongside a full
OCaml runtime providing functions such as
\texttt{caml\_alloc}, \texttt{caml\_callback}, and the garbage collector.

Rather than replacing this execution model, we preserve it.

Our compilation pipeline first produces ordinary OCaml bytecode using the
standard compiler. Independently, the OCaml bytecode runtime, every C
stub, and every native dependency are compiled to WebAssembly using
Emscripten. The final executable is therefore a conventional OCaml
bytecode interpreter whose implementation happens to target wasm32
instead of a native processor.

This architecture offers several advantages.

First, it preserves binary compatibility with existing FFI code. Native
libraries continue to interact with the runtime exactly as they do on
native platforms, without requiring additional marshaling layers.

Second, every native dependency becomes part of a single statically
linked WebAssembly module. No communication between independent wasm
instances or JavaScript wrappers is required.

Finally, because the original runtime remains responsible for memory
management and primitive dispatch, the port requires remarkably few
changes to the OCaml application itself. Most modifications are confined
to the build system and to a small number of runtime assumptions that do
not hold on WebAssembly.

The remainder of this paper describes the implementation of this
architecture and the challenges encountered while making it work.


# Static Linking of OCaml Primitives

The main challenge after choosing the bytecode runtime is linking the
native components together.

Unlike native OCaml executables, bytecode programs do not contain direct
calls to C functions. Instead, each `external` declaration is translated
into an index referring to a primitive table maintained by the runtime.
During program initialization, the runtime resolves primitive names into
function pointers, which are subsequently used by bytecode instructions
such as `C_CALL1`, `C_CALL2`, and `C_CALLN`.

On conventional Unix systems this resolution relies on dynamic loading.
The runtime opens shared libraries using `dlopen`, resolves primitive
symbols with `dlsym`, and populates the primitive table before execution
begins.

This mechanism is poorly suited to our setting. Although Emscripten
supports dynamic linking, doing so would require splitting the system
into multiple WebAssembly modules and preserving OCaml's dynamic loading
semantics inside the browser. Besides increasing complexity, such an
approach would defeat one of our design goals: producing a single,
self-contained WebAssembly application.

## Leveraging the Bytecode Runtime's Static Mode

Fortunately, the OCaml runtime already contains an alternative
mechanism.

Before consulting dynamically loaded libraries, the runtime first checks
a statically compiled table of built-in primitives. This mechanism is
normally used by `ocamlc -custom`, which generates a source file
(`prims.c`) containing every primitive required by the executable.

Our implementation reuses exactly this mechanism.

Rather than generating `prims.c` from the OCaml build system, we build a
single table containing every primitive exported by the runtime itself,
the standard library, CamlIDL-generated bindings, Apron, Zarith,
LLVM/Clang bindings, and MOPSA-specific native code.

The runtime therefore resolves every primitive from this static table,
and the dynamic loading path becomes unnecessary. The browser never
loads shared objects, because every native component is already present
inside the final WebAssembly module.

This approach requires no modification to the bytecode interpreter.
Primitive dispatch follows exactly the same execution path as a
conventional statically linked OCaml bytecode executable.

## Constructing the Primitive Table

Generating the primitive table is largely an engineering problem.

The final system contains more than 1400 exported primitives originating
from several independent projects. Rather than maintaining this list by
hand, we generate it automatically during the build.

A small extraction tool scans every source file and identifies functions
exported through the OCaml FFI. Unlike the standard
`gen_primitives.sh` script distributed with OCaml, which assumes a
particular declaration style, the extractor recognizes the conventions
used throughout MOPSA, Apron, and CamlIDL-generated code.

From the resulting list, the build system generates a single `prims.c`
file containing

- forward declarations of every primitive,
- the array of function pointers (`caml_builtin_cprim`), and
- the corresponding array of primitive names
  (`caml_names_of_builtin_cprim`).

The generated file is then compiled together with the bytecode runtime.

Although the primitives have heterogeneous signatures, this poses no
difficulty. The OCaml interpreter stores them uniformly as function
pointers and casts them to the appropriate calling convention when a
`C_CALLn` instruction is executed. Consequently, every primitive can be
declared using the same generic prototype.

## Advantages of a Fully Static Runtime

Using a statically generated primitive table has several practical
benefits.

First, linking becomes entirely deterministic. Every primitive required
by the bytecode must exist at link time, allowing Emscripten to report
missing symbols immediately instead of failing later at runtime with an
``unknown C primitive'' exception.

Second, all native code executes inside a single WebAssembly instance.
No cross-module communication or JavaScript bridge is required between
the OCaml runtime and native libraries.

Finally, this approach preserves the execution model expected by
existing OCaml software. Native libraries continue to interact with the
runtime exactly as they do on Unix systems, despite executing inside a
browser.

The resulting WebAssembly binary therefore behaves as a conventional
statically linked OCaml bytecode interpreter whose host architecture
happens to be `wasm32`.

# Implementation Challenges

Most native dependencies required only modest adaptations to compile
under Emscripten. In practice, the work naturally fell into four
categories, each requiring a different strategy.

## The OCaml Runtime

The OCaml bytecode runtime itself compiles almost unchanged with
Emscripten. Apart from disabling unsupported features such as native code
generation and system threads, the build process closely follows a
standard OCaml build.

One small exception concerns build tools executed during compilation.
Recent versions of OCaml generate part of the runtime using auxiliary
programs that are expected to run on the host machine. When compiled
with Emscripten, these tools become WebAssembly binaries and therefore
cannot execute during the build. We solved this by compiling the few
required utilities natively while compiling the runtime itself with
Emscripten.

Once built, the runtime provides the `<caml/*.h>` headers against which
every subsequent C stub is compiled, ensuring that all native
components agree on the exact runtime ABI.

## Numerical Libraries and FFI Bindings

Most numerical dependencies, including GMP, MPFR, and Apron, required
surprisingly few modifications.

For libraries using Autotools, compiling under Emscripten generally
consists of configuring the build with `emconfigure` followed by a
conventional compilation. A few platform-specific optimizations, such as
GMP's handwritten assembly routines, must be disabled because they are
not applicable to WebAssembly.

Bindings generated by CamlIDL fit naturally into this compilation model.
Since the generated stubs are ordinary C code using the standard OCaml
FFI, they can simply be compiled alongside the rest of the native
sources once the OCaml runtime headers are available.

Overall, the majority of the engineering effort did not lie in these
libraries themselves but rather in integrating them into a single
WebAssembly executable.

## LLVM and Clang

LLVM constitutes the largest native dependency.

Unlike the numerical libraries, LLVM cannot be cross-compiled directly
because part of the project is generated by host executables
(`llvm-tblgen` and `clang-tblgen`). These generators must first be built
natively before being reused during the WebAssembly build.

Once these tools are available, only a relatively small subset of LLVM
needs to be compiled. MOPSA requires Clang as a parser and semantic
analyzer but performs neither optimization nor code generation.
Consequently, only the frontend libraries and their supporting
infrastructure are included in the final executable.

The resulting WebAssembly module embeds a complete C parser while
remaining substantially smaller than a full LLVM distribution.

## Browser Integration

Producing a WebAssembly module is only part of the port.

MOPSA is fundamentally a command-line application expecting files,
command-line arguments, environment variables, and interactive standard
input. The browser provides none of these abstractions directly.

Our implementation relies on Emscripten's virtual filesystem to expose
both static resources (the bytecode executable, Clang resource headers,
configuration files) and user-provided source files. Each analysis is
executed inside a fresh WebAssembly instance, avoiding the need to reset
the OCaml runtime after program termination.

Interactive execution required a dedicated communication channel between
JavaScript and WebAssembly. We implemented this using
`SharedArrayBuffer` and `Atomics.wait`, allowing the worker running the
WebAssembly module to block synchronously while the browser remains
responsive. This mechanism supports both MOPSA's interactive REPL and
its Debug Adapter Protocol (DAP) implementation without modifying the
analyzer itself.

# Adapting the OCaml Runtime to WebAssembly

Most of the port consisted of engineering work: compiling existing
components, integrating build systems, and adapting the surrounding
runtime environment. Only a handful of changes were required to the
runtime itself.

The most significant issue concerned the representation of OCaml values
on `wasm32`.

## A Runtime Assumption Exposed by WebAssembly

OCaml heap values are represented by pointers to heap blocks preceded by
a header word containing the block's size, tag, and garbage collector
metadata. Runtime macros such as `Tag_val`, `Hd_val`, and `Wosize_val`
retrieve this information through pointer arithmetic.

Conceptually, obtaining the tag of a value amounts to reading the byte
immediately preceding the first word of the object.

In OCaml 4.14, this operation is implemented as

```c
#define Tag_val(v) (((unsigned char *)(v))[-sizeof(value)])
```

At first sight, this expression appears perfectly reasonable.
`sizeof(value)` evaluates to four bytes on `wasm32`, suggesting that the
macro simply accesses the byte located four bytes before the object.

However, `sizeof` has type `size_t`, which is unsigned. Consequently,
the expression `-sizeof(value)` does not produce the signed constant
`-4`, but the unsigned integer `0xFFFFFFFC`.

On conventional 32-bit architectures this distinction is invisible.
Pointer arithmetic is lowered to an integer addition whose result wraps
modulo \(2^{32}\), so adding `0xFFFFFFFC` happens to produce the same
effective address as subtracting four.

WebAssembly exposes a subtle difference.

When lowering the expression, LLVM folds the unsigned constant into the
immediate offset of the generated load instruction:

```wat
local.get 0
i32.load8_u offset=4294967292
```

Unlike an explicit `i32.add`, this offset does not wrap modulo
\(2^{32}\). Instead, the WebAssembly runtime performs its bounds check
using the large positive offset directly, producing an immediate
``out of bounds'' trap before the load can execute.

The crash therefore originates not from the OCaml runtime itself, but
from an optimization performed during code generation.

## Fixing the Runtime

Rather than relying on backend-specific code generation, we modified the
runtime to express the intended pointer arithmetic explicitly.

Instead of indexing a byte array with an unsigned negative offset, the
runtime now first moves to the previous header word using typed pointer
arithmetic before extracting the tag.

This guarantees that the generated code contains an explicit wrapping
address computation independently of compiler optimizations.

Only a few locations inside the runtime assumed that `Tag_val` could be
used as an l-value. These were rewritten through a small helper that
updates only the tag bits while preserving the remaining header fields.

The resulting implementation behaves identically on native platforms
while avoiding backend-dependent behavior on WebAssembly.

## Lessons Learned

This issue illustrates a broader point about porting low-level runtime
systems.

The OCaml runtime had behaved correctly for decades on conventional
architectures because native processors naturally masked the unsigned
wraparound produced by the original macro. Moving to WebAssembly did not
invalidate the runtime's logic, but it exposed an implicit assumption
about how compiler optimizations lower pointer arithmetic.

Experience reports often emphasize build-system complexity or missing
platform APIs. In our case, the most interesting difficulty lay instead
at the interface between the OCaml runtime, LLVM's optimizer, and the
WebAssembly execution model.



