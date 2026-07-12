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

Current OCaml-to-WebAssembly backends compile the OCaml code alone, leaving developers to port native dependencies by hand and to write JavaScript glue code. This paper reports on our experience porting MOPSA, a static analyzer that combines OCaml with LLVM/Clang, GMP, MPFR, Apron, and CamlIDL-generated bindings, to run entirely inside a web browser without any glue code. Instead of compiling only the OCaml code, we compile the OCaml bytecode runtime together with the complete native dependency stack into a single, statically linked WebAssembly module. Linking the runtime supplies the C primitives that the FFI stubs depend on, while the bytecode's external calls are bound through a static primitive table, the mechanism behind OCaml's statically linked (custom) executables, instead of the dynamic loading the runtime normally performs at startup. The fully working runtime is then carried to WebAssembly without any FFI/glue written.
\end{abstract}

\section{Introduction}

\indent Large OCaml applications rarely consist of OCaml code alone. They sit on native libraries reached through the foreign function interface (FFI), and those bindings allocate OCaml blocks, read their tags and fields, and call back into the runtime. Porter ce genre d'application dans le navigateur pose la question de comment préserver l'intéraction entre Ocaml et les dépendances.

Existing OCaml-to-wasm backends (\texttt{js\_of\_ocaml}, \texttt{wasm\_of\_ocaml}, \texttt{wasocaml}) compile the OCaml and leave the C/C++ behind, and the FFI stubs call runtime functions such as \texttt{caml\_alloc} and \texttt{caml\_callback} that doesn't exist on the produced wasms. Bridging a native component across the wasm boundary then means hand-writing JavaScript/wasm glue for it, an effort that grows with the number of bindings.

We contribute (i) a general, reproducible recipe to run FFI-heavy OCaml on wasm by compiling the bytecode runtime rather than the code, requiring no per-binding glue. (ii) Three runtime/ABI portability hazards it exposes at scale, the last of which reaches the analyzer's soundness guarantee. (iii) A performance comparison with \texttt{js\_of\_ocaml} that quantifies the cost of interpretation.

The project that we compiled is MOPSA, where a 100% client side live build can be found at \url{https://mopsawasm.rboud.com/}.


\section{The problem that we try to resolve}

\indent MOPSA is a static analyzer based on abstract interpretation for C and Python \cite{mopsa}, written mostly in OCaml. Underneath sit GMP, MPFR, Zarith, Apron for the numerical domains \cite{apron}, and LLVM/Clang to parse C, all bound through the FFI. Roughly 655 of the ~1435 primitives the analyzer needs are CamlIDL-generated stubs \cite{camlidl}. One internal file, \texttt{Clang\_to\_ml.cc} (~5000 lines), contains Clang headers and \texttt{<caml/*.h>} at once, and drives Clang to parse a file and allocates OCaml values from the resulting AST directly inside the GC heap, using the \texttt{CAMLparam}/\texttt{CAMLlocal}/\texttt{CAMLreturn} macros.

\begin{figure}[t]
  \centering
  \includegraphics[width=\linewidth]{mopsa_deps.pdf}
  \caption{MOPSA's native dependencies. Dashed boxes uses OCaml FFI in one way or another.}
  \label{fig:deps}
\end{figure}
<!-- asset: export ./mopsa_deps.svg to mopsa_deps.pdf (pandoc/LaTeX needs a raster or PDF, not SVG) -->

Existing solutions do not cover our use case. It is ideal for pure-OCaml code or code whose few native dependencies already have a JS reimplementation (e.g. \texttt{zarith\_stubs\_js}). But for our case, they do not expose FFI functions that we could link our wasm-compiled `Clang_to_ml.cc` against\footnote{these backends move OCaml values out of the linear-memory layout the FFI assumes (WasmGC) so a C stub that reads a value's fields or tag by pointer cannot reach them at all. Exposing these functions isn't a solution either.} and a full rewrite of our 5000 line `Clang_to_ml.cc` file in javascript and all the CamlIDL-generated stubs which is not viable.


\section{Compiling the bytecode runtime}

\indent The missing \texttt{caml\_*} symbols turn out to be provided by the OCaml runtime itself\footnote{We choose to compile Ocaml latest 4 version (4.14.2 when we started) since our target was wasm32 and Ocaml 5 dropped support for 32bit}. Once the runtime is in the picture, everything left to compile is C and C++, so we can lean on Emscripten alone and avoid stitching together modules produced by two compilers with two different memory models. The plan is therefore to compile the OCaml to bytecode, compile the runtime plus every native dependency to wasm with Emscripten, link that native bundle statically, and interpret the bytecode on top.

OCaml normally resolves the C code behind each \texttt{external} dynamically. At startup it \texttt{dlopen}s the native libraries and \texttt{dlsym}s each primitive by name to fill a table of function pointers. Emscripten can emulate dynamic module loading, but that splits the binary into several wasm modules and complicates the build. Instead there is a full static way.  
\indent Before searching \texttt{.so} files, \texttt{lookup\_primitive} first consults a built-in table (\texttt{caml\_builtin\_cprim[]} and \texttt{caml\_names\_of\_builtin\_cprim[]}) that \texttt{ocamlc -custom} generates as a \texttt{prims.c} file. We generate our own \texttt{prims.c} as a superset of every primitive the bytecode calls (the runtime core, \texttt{unix}, \texttt{str}, bigarray/int64, and the CamlIDL Apron/GMP stubs), disable the \texttt{dlopen} branch, and let \texttt{ERROR\_ON\_UNDEFINED\_SYMBOLS=1} turn a missing primitive into a link-time failure rather than an \texttt{unknown C primitive} trap in the browser.

\section{Portability hazards}

While testing, we encountered hazards that represent code that compiles and links correctly, yet is wrong because wasm (wasm32 particularly) is not the native target it was written for. 

\paragraph{A runtime macro that is unsound on wasm32.}
The first browser run trapped with ``index out of bounds'', traced to OCaml 4.14's \texttt{Tag\_val}, which reads the block header at offset \texttt{-sizeof(value)}. Since \texttt{sizeof} is unsigned, that offset is \texttt{0xFFFFFFFC}, not \texttt{-4}. On native ILP32 the address wraps in a 32-bit \texttt{add} and lands on \texttt{val-4}, which is why upstream gets away with it everywhere. On wasm32 the backend can fold the non-negative constant into a bounds-checked unsigned \texttt{i32.load} offset that does not wrap, so the access lands ~4\,GiB away and traps. The fold is itself backend-dependent, since \texttt{emcc}/clang~22 traps while \texttt{wasi-sdk} clang~18 does not.

\paragraph{Architecture-dependent ABI in the analyzed program.}
Unlike the previous one, this hazard is in the C that MOPSA analyzes. Porting the stack to wasm32 also retargeted MOPSA's embedded Clang from x86-64 to 32-bit, so the sources it parses are now typed for a 32-bit ABI. There \texttt{va\_list} is a scalar \texttt{void*} passed \emph{by reference} to \texttt{\_\_builtin\_va\_start}, so Clang hands MOPSA's type translator an \texttt{LValueReferenceType}, a case it lacked because on x86-64 \texttt{va\_list} is an array that decays to a pointer. That missing case broke the translation of CPython's C sources.

\paragraph{A wasm ABI limitation that reaches soundness.}
WebAssembly has no FPU rounding-mode control, so everything is round-to-nearest and \texttt{fesetround} is a no-op. It threatens soundness on two fronts. Apron's interval arithmetic relies on directed rounding, which we sidestep by compiling every domain with \texttt{NUM\_MPQ} (bounds computed exactly with GMP rationals) and faking the FPU probe, though a residual unsoundness remains where floats reach Apron's API before conversion to rationals. MOPSA's own float handling (\texttt{floats\_round.c}) depends on the same rounding-mode control, and there we still have no satisfying fix. Widening every interval to a safe over-approximation keeps the analysis sound but coarse. Unlike the first two, this is not a 32-bit quirk but a property of wasm itself, and it is the one that crosses from portability into verification.


\section{Discussion and conclusion}

<!-- TODO perf: fill the three \textbf{[FILL ...]} slots with real numbers from the wasm-vs-jsoo benchmark -->
The honest cost of this approach is speed. Interpreting bytecode on wasm is slower than running the compiled output of a pure-OCaml backend. We can measure this only where both approaches run, namely MOPSA's pure-OCaml configuration (VPL in place of Apron, no C or cross C/Python analysis), the only subset \texttt{js\_of\_ocaml} can build at all. Across \textbf{[FILL: N benchmarks, which languages]} our wasm build is \textbf{[FILL: A to B$\times$]} slower than the \texttt{js\_of\_ocaml} JavaScript, \textbf{[FILL: figures on Node and in the browser, noting any gap]}. That comparison is also the point. This pure-OCaml subset excludes precisely what MOPSA exists to do, the C/Apron FFI that \texttt{js\_of\_ocaml} cannot run at all, so on its real workload our approach is not slower, it is the only one that runs. We chose interpretation deliberately for a smaller, maintainable result (one static \texttt{.wasm}, no cross-compiler glue). The contribution is doing this at scale on a real, deeply FFI-coupled application, together with the hazards that only surface there.

None of this is specific to MOPSA. Any FFI-heavy OCaml application whose native stack is impractical to reimplement can be carried to the browser the same way, and will meet the same class of silent wasm-versus-native divergences. The question we would most like to open with the community is where this approach belongs. Is a bytecode runtime on wasm a stopgap the toolchain should support first-class, or a dead end next to making \texttt{wasm\_of\_ocaml} interoperate with Emscripten-compiled C, and what would OCaml~5 (domains, effects) change for a runtime brought onto wasm this way? We take these questions up live, running MOPSA entirely in the browser at \url{https://mopsawasm.rboud.com/}.

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

\bibitem{ocamlwasm} V. Chan. \emph{ocaml-wasm.} 2021.
\url{https://github.com/vincentdchan/ocaml}.

\bibitem{binji} binji. \emph{Building LLVM/Clang to WebAssembly.}
\url{https://gist.github.com/binji/b7541f9740c21d7c6dac95cbc9ea6fca}.

\bibitem{gmpso} Stack Overflow. \emph{Compiling GMP/MPFR with Emscripten.}
\url{https://stackoverflow.com/a/43583154}.

\end{thebibliography}
