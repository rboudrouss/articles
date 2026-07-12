---
fontsize: 10pt
geometry: margin=4cm
indent: true
header-includes:
  - \usepackage{graphicx}
  - \setlength{\parskip}{6pt plus 2pt minus 1pt}
  - \interfootnotelinepenalty=10000
---

\title{Preserving the OCaml FFI on WebAssembly}
\author{Reda Boudrouss \\
	Sorbonne University \\
	contact@rboud.com \\
	}

\date{\today}

\maketitle


\begin{abstract}
Many large OCaml applications do not consist of OCaml code alone. They depend on native C and C++ libraries accessed through the OCaml foreign function interface (FFI), where bindings often manipulate OCaml values directly and rely on the runtime's data representation, calling conventions, and memory model. This tight coupling to the runtime is precisely what makes such applications hard to bring to the browser. How to port them together with their entire native dependency stack remains largely unexplored.

Current OCaml-to-WebAssembly backends compile the OCaml code alone, leaving developers to port native dependencies by hand and to write JavaScript glue code. This paper reports on our experience porting MOPSA, a static analyzer that combines OCaml with LLVM/Clang, GMP, MPFR, Apron, and CamlIDL-generated bindings, to run entirely inside a web browser without any glue code. Instead of compiling only the OCaml code, we compile the OCaml bytecode runtime together with the complete native dependency stack into a single, statically linked WebAssembly module using Emscripten. Linking the runtime supplies the C primitives that the FFI stubs depend on, while the bytecode's external calls are bound through a static primitive table, the mechanism behind OCaml's statically linked (custom) executables, instead of the dynamic loading the runtime normally performs at startup. The fully working runtime is then carried to WebAssembly with no hand-written FFI or glue code.
\end{abstract}

\section{Introduction}

\indent Large OCaml applications rarely consist of OCaml code alone. They rest on native libraries reached through the foreign function interface (FFI), and those bindings allocate OCaml blocks, read their tags and fields, and call back into the runtime. Porting an application of this kind to the browser raises the question of how to preserve the interaction between OCaml and its dependencies.

Existing OCaml-to-wasm backends (\texttt{js\_of\_ocaml}, \texttt{wasm\_of\_ocaml}, \texttt{wasocaml}) compile the OCaml code and leave the C and C++ behind, so the FFI stubs call runtime functions such as \texttt{caml\_alloc} and \texttt{caml\_callback} that do not exist in the resulting Wasm module. Bridging a native component across the wasm boundary then means hand-writing JavaScript/wasm glue for it, an effort that grows with the number of bindings.

We contribute (i) a general, reproducible recipe to run FFI-heavy OCaml on wasm by compiling the bytecode runtime rather than the code, requiring no per-binding glue. (ii) Three runtime/ABI portability hazards we encountered. (iii) A performance comparison against native MOPSA and \texttt{js\_of\_ocaml} that quantifies the cost of interpretation and finds the wasm build competitive with \texttt{js\_of\_ocaml} where both can run.

The project we compiled is MOPSA. A fully client-side live build is available at \url{https://mopsawasm.rboud.com/}.


\section{The problem we address}

\indent MOPSA is a static analyzer based on abstract interpretation for C and Python \cite{mopsa}, written mostly in OCaml. Beneath it sit GMP, MPFR, Zarith, and Apron for the numerical domains \cite{apron}, together with LLVM/Clang to parse C, all bound through the FFI. Roughly 655 of the ~1435 primitives the analyzer needs are CamlIDL-generated stubs \cite{camlidl}. One internal file, \texttt{Clang\_to\_ml.cc} (~5000 lines), includes the Clang headers and \texttt{<caml/*.h>} at the same time. It drives Clang to parse a source file and then allocates OCaml values from the resulting AST directly inside the GC heap, using the \texttt{CAMLparam}/\texttt{CAMLlocal}/\texttt{CAMLreturn} macros.

<!-- \begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{mopsa_deps.pdf}
  \caption{MOPSA's native dependencies. Dashed boxes use the OCaml FFI in one way or another.}
  \label{fig:deps}
\end{figure} -->

Existing solutions do not cover our use case. They are well suited to pure-OCaml code, or to code whose few native dependencies already have a JavaScript reimplementation (e.g. \texttt{zarith\_stubs\_js}). In our case they do not expose FFI functions that we could link our wasm-compiled \texttt{Clang\_to\_ml.cc} against\footnote{these backends move OCaml values out of the linear-memory layout the FFI assumes (WasmGC), so a C stub that reads a value's fields or tag by pointer cannot reach them at all. Exposing these functions is not a solution either.}, and rewriting the entire 5000-line \texttt{Clang\_to\_ml.cc} file, along with all the CamlIDL-generated stubs, in JavaScript is not viable.


\section{Compiling the bytecode runtime}

\indent The missing \texttt{caml\_*} symbols turn out to be provided by the OCaml runtime itself\footnote{We chose to compile the latest OCaml 4 release (4.14.2 when we started), since our target was wasm32 and OCaml 5 dropped support for 32-bit. We have not tested the approach with OCaml 5.}. Once the runtime is included, everything left to compile is C and C++, so we can rely on Emscripten alone \cite{emscripten} and avoid stitching together modules produced by two compilers with two different memory models. The plan is therefore to compile the OCaml to bytecode, compile the runtime plus every native dependency to wasm with Emscripten, link that native bundle statically, and interpret the bytecode on top.

OCaml normally resolves the C code behind each \texttt{external} dynamically. At startup it \texttt{dlopen}s the native libraries and \texttt{dlsym}s each primitive by name to fill a table of function pointers. Emscripten can emulate dynamic module loading, but that splits the binary into several wasm modules and complicates the build. A fully static approach is available instead.  
\indent Before searching \texttt{.so} files, \texttt{lookup\_primitive} first consults a built-in table (\texttt{caml\_builtin\_cprim[]} and \texttt{caml\_names\_of\_builtin\_cprim[]}) that \texttt{ocamlc -custom} generates as a \texttt{prims.c} file. We generate our own \texttt{prims.c} as a superset of every primitive the bytecode calls (the runtime core, \texttt{unix}, \texttt{str}, bigarray/int64, and the CamlIDL Apron/GMP stubs), disable the \texttt{dlopen} branch, and let \texttt{ERROR\_ON\_UNDEFINED\_SYMBOLS=1} turn a missing primitive into a link-time failure rather than an \texttt{unknown C primitive} trap in the browser.

\section{Portability hazards}

While testing, we encountered hazards where code compiles and links correctly yet is wrong, because wasm (wasm32 in particular) is not the native target it was written for. 

\paragraph{A runtime macro that is unsound on wasm32.}
The first browser run trapped with ``index out of bounds'', traced to OCaml 4.14's \texttt{Tag\_val}, which reads the block header at offset \texttt{-sizeof(value)}. Since \texttt{sizeof} is unsigned, that offset is \texttt{0xFFFFFFFC}, not \texttt{-4}. On native ILP32 the address wraps in a 32-bit \texttt{add} and lands on \texttt{val-4}, which is why the issue never surfaces upstream on native targets. On wasm32 the backend can fold the non-negative constant into a bounds-checked unsigned \texttt{i32.load} offset that does not wrap, so the access lands ~4\,GiB away and traps. The fold is itself backend-dependent, since \texttt{emcc}/clang~22 traps while \texttt{wasi-sdk} clang~18 does not.

\paragraph{Architecture-dependent ABI in the analyzed program.}
Porting the stack to wasm32 also retargeted MOPSA's embedded Clang from x86-64 to 32-bit, so the sources it parses are now typed for a 32-bit ABI. There \texttt{va\_list} is a scalar \texttt{void*} passed \emph{by reference} to \texttt{\_\_builtin\_va\_start}, so Clang hands MOPSA's type translator an \texttt{LValueReferenceType}, a case it lacked because on x86-64 \texttt{va\_list} is an array that decays to a pointer. That missing case broke the translation of CPython's C sources.

\paragraph{A wasm ABI limitation that reaches soundness.}
WebAssembly has no FPU rounding-mode control, so everything is round-to-nearest and \texttt{fesetround} is a no-op. It threatens soundness on two fronts. Apron's interval arithmetic relies on directed rounding, which we sidestep by compiling every domain with \texttt{NUM\_MPQ} (bounds computed exactly with GMP rationals) and stubbing out the FPU probe, though a residual unsoundness remains where floats reach Apron's API before conversion to rationals. MOPSA's own float handling (\texttt{floats\_round.c}) depends on the same rounding-mode control, and there we still have no satisfying fix. Widening every interval to a safe over-approximation keeps the analysis sound but coarse. Unlike the first two, this is not a 32-bit quirk but a property of wasm itself, and it is the one that crosses from portability into verification.


\section{Performance}

We compared the wasm build with native MOPSA and with \texttt{js\_of\_ocaml} on a corpus of fourteen C, Python, and universal files, over 100 repetitions in both Node and a headless browser. Interpreted bytecode on wasm is, as expected, slower than native compiled code. In steady state, once V8 has tiered the module up, analysis runs about 10 times slower than native on the C files and about 13 times slower on Python. Compared to the \texttt{js\_of\_ocaml} build on the universal and Python benchmarks both can run, the wasm build is competitive. The two are close on a cold run, but a fresh analysis needs a fresh OCaml state, and \texttt{js\_of\_ocaml} keeps state and code together in one JavaScript realm, so getting a clean state means a cold realm again. WebAssembly instead re-instantiates a shared module that V8 has already tiered up, so on repeated analyses the wasm build pulls ahead, by roughly 1.3 times on Python under Node and 3.4 times in the browser. It also instantiates about 6 times faster, 63 ms against 359 ms under Node, since there is no 22 MB JavaScript bundle to parse. This holds only for the pure-OCaml configuration (VPL, no C) that \texttt{js\_of\_ocaml} can build. On the full C and Apron workload it does not run at all.

\section{Discussion}

None of this is specific to MOPSA. Any FFI-heavy OCaml application whose native stack is impractical to reimplement can be carried to the browser the same way, and will meet the same class of silent wasm-versus-native divergences.

Most of the recipe is mechanical, and we believe much of it could be automated. Emscripten's build tooling has matured to the point where several of our native dependencies compiled with no patch at all, and the primitive-table generation and static-linking steps are systematic. One can imagine a dedicated build target, for instance in dune, that compiles a whole OCaml project together with its native stack to wasm from sources alone, given an opam switch with sources, leaving only genuinely native components such as LLVM/Clang to case-by-case work. Whether such a reusable path is worth building as a shared effort, at least until a WasmGC backend such as \texttt{wasm\_of\_ocaml} can interoperate with Emscripten-compiled C, is the question we would most like to open with the community. How far the approach carries to OCaml~5 is a further open question, and an early experiment is encouraging, since the \texttt{Tag\_val} issue is already fixed in the latest 5.x and the remaining wasm-hostile behavior appears possible to disable.

\paragraph{Availability.}
The port targets OCaml 4.14 (LLVM/Clang 9, GMP 6.1.2, MPFR 4.2.2) and runs
entirely client-side. Sources are at \url{https://github.com/rboudrouss/mopsa-wasm}.


\section{Acknowledgements}

We thank Antoine Miné for guiding us through the MOPSA codebase and supporting this work throughout, and Raphaël Monat for Try-MOPSA \cite{trymopsa}, an all-\texttt{js\_of\_ocaml} build of MOPSA. Try-MOPSA produced the \texttt{js\_of\_ocaml}/VPL configuration we compare against and was invaluable in getting our interactive mode working in the browser. The port also builds on Vincent Chan's \texttt{ocaml-wasm} \cite{ocamlwasm}, which supplied the original Emscripten tweaks, on binji's LLVM-to-wasm fork \cite{binji}, and on a Stack Overflow answer \cite{gmpso} that identified Emscripten-compatible GMP and MPFR versions.



\begin{thebibliography}{9}

\bibitem{mopsa} M. Journault, A. Miné, R. Monat, and A. Ouadjaout.
\emph{Combinations of Reusable Abstract Domains for a Multilingual Static
Analyzer.} VSTTE 2019.

\bibitem{trymopsa} R. Monat. \emph{Try-Mopsa: Relational Static Analysis in Your
Pocket.} arXiv:2509.13128, 2025. \url{https://arxiv.org/abs/2509.13128}.

\bibitem{apron} B. Jeannet and A. Miné. \emph{Apron: A Library of Numerical
Abstract Domains for Static Analysis.} CAV 2009, LNCS 5643.

\bibitem{camlidl} X. Leroy. \emph{CamlIDL User's Manual.}
\url{https://github.com/xavierleroy/camlidl}.

\bibitem{jsoo} J. Vouillon and V. Balat. \emph{From bytecode to JavaScript: the
Js\_of\_ocaml compiler.} Software: Practice and Experience, 44(8), 2014.

\bibitem{emscripten} A. Zakai. \emph{Emscripten: an LLVM-to-JavaScript Compiler.}
OOPSLA 2011 (companion), ACM.

\bibitem{ocamlwasm} V. Chan. \emph{ocaml-wasm.} 2021.
\url{https://github.com/vincentdchan/ocaml}.

\bibitem{binji} binji. \emph{Building LLVM/Clang to WebAssembly.}
\url{https://gist.github.com/binji/b7541f9740c21d7c6dac95cbc9ea6fca}.

\bibitem{gmpso} Stack Overflow. \emph{Compiling GMP/MPFR with Emscripten.}
\url{https://stackoverflow.com/a/43583154}.

\end{thebibliography}
